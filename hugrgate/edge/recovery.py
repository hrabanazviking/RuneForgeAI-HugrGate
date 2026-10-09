"""Intermittent-power recovery via checkpoint journal. Slice 193.

Edge nodes lose power mid-write. :class:`CheckpointJournal` makes
"what was I doing?" answerable after the lights come back:

- :meth:`checkpoint` atomically persists a CRC32-protected JSON
  record (temp file → fsync → ``os.replace``); a torn write from a
  power cut fails CRC validation and is *skipped*, never trusted;
- :meth:`latest` returns the newest *valid* checkpoint, scanning
  past corrupt ones toward the previous good record;
- :meth:`mark_complete` removes a checkpoint once its work finished,
  turning at-least-once resume into at-most-once handoff;
- only the newest ``keep`` checkpoints are retained, so the journal
  cannot grow without bound on a node that checkpoints often.

The journal is deliberately dependency-free (no
:class:`WearAwareStore`): recovery must work at the earliest boot
stage, before heavier subsystems exist.
"""

from __future__ import annotations

import json
import os
import threading
import zlib
from pathlib import Path
from typing import Any

from hugrgate.errors import HugrGateError

__all__ = [
    "Checkpoint",
    "CheckpointJournal",
    "RecoveryError",
]

#: Journal file magic + version, guarding against alien files.
_MAGIC = "HGCK0001"


class RecoveryError(HugrGateError):
    """A checkpoint could not be written or recovered."""


class Checkpoint:
    """One validated checkpoint record."""

    def __init__(self, seq: int, state_id: str, payload: dict[str, Any]):
        self.seq = seq
        self.state_id = state_id
        self.payload = payload

    def to_dict(self) -> dict[str, Any]:
        return {"seq": self.seq, "state_id": self.state_id,
                "payload": self.payload}

    def __repr__(self) -> str:
        return f"Checkpoint(seq={self.seq}, state_id={self.state_id!r})"


class CheckpointJournal:
    """CRC-protected, atomic, bounded checkpoint journal."""

    def __init__(self, directory: str | Path, keep: int = 3):
        if keep < 1:
            raise RecoveryError("keep must be >= 1")
        self._dir = Path(directory)
        self._keep = int(keep)
        self._lock = threading.RLock()
        self._seq = 0

    @classmethod
    def open(cls, directory: str | Path, **kwargs: Any) -> CheckpointJournal:
        journal = cls(directory, **kwargs)
        journal._dir.mkdir(parents=True, exist_ok=True)
        journal._seq = journal._max_seq()
        return journal

    # -- paths ---------------------------------------------------------------------

    def _path(self, seq: int, state_id: str) -> Path:
        safe = "".join(c if c.isalnum() or c in "-_." else "_"
                       for c in state_id)[:64] or "state"
        return self._dir / f"chk_{seq:08d}_{safe}.json"

    def _max_seq(self) -> int:
        best = 0
        for path in self._dir.glob("chk_*.json"):
            try:
                seq = int(path.name.split("_")[1])
            except (IndexError, ValueError):
                continue
            best = max(best, seq)
        return best

    # -- writing ----------------------------------------------------------------------

    def checkpoint(self, state_id: str, payload: dict[str, Any]) -> Checkpoint:
        """Atomically persist a checkpoint; returns the record."""
        if not state_id or not state_id.strip():
            raise RecoveryError("state_id must be non-empty")
        try:
            json.dumps(payload)
        except (TypeError, ValueError) as e:
            raise RecoveryError(f"payload is not JSON-serializable: {e}"
                                ) from e
        with self._lock:
            self._seq += 1
            seq = self._seq
            body = {"magic": _MAGIC, "seq": seq, "state_id": state_id,
                    "payload": payload}
            blob = json.dumps(body, sort_keys=True).encode("utf-8")
            crc = zlib.crc32(blob)
            record = json.dumps({"body": body, "crc32": crc},
                                sort_keys=True).encode("utf-8")
            path = self._path(seq, state_id)
            tmp = path.with_suffix(".json.tmp")
            with open(tmp, "wb") as fh:
                fh.write(record)
                fh.flush()
                os.fsync(fh.fileno())
            os.replace(tmp, path)
            self._prune()
            return Checkpoint(seq, state_id, payload)

    def _prune(self) -> None:
        paths = sorted(self._dir.glob("chk_*.json"),
                       key=lambda p: p.name)
        for stale in paths[:-self._keep]:
            try:
                stale.unlink()
            except OSError:
                pass

    # -- reading -------------------------------------------------------------------------

    @staticmethod
    def _read_one(path: Path) -> Checkpoint | None:
        """Return the checkpoint, or None when corrupt/torn/alien."""
        try:
            with open(path, "rb") as fh:
                record = json.loads(fh.read().decode("utf-8"))
            body, crc = record["body"], record["crc32"]
            if body.get("magic") != _MAGIC:
                return None
            blob = json.dumps(body, sort_keys=True).encode("utf-8")
            if zlib.crc32(blob) != crc:
                return None
            return Checkpoint(int(body["seq"]), str(body["state_id"]),
                              dict(body["payload"]))
        except (OSError, ValueError, KeyError, TypeError):
            return None

    def checkpoints(self) -> list[Checkpoint]:
        """All *valid* checkpoints, newest first."""
        with self._lock:
            found = []
            for path in sorted(self._dir.glob("chk_*.json"),
                               key=lambda p: p.name, reverse=True):
                cp = self._read_one(path)
                if cp is not None:
                    found.append(cp)
            return found

    def latest(self) -> Checkpoint | None:
        """Newest valid checkpoint, or None when the journal is empty."""
        cps = self.checkpoints()
        return cps[0] if cps else None

    def recover(self) -> dict[str, Any] | None:
        """Payload to resume from, or None when nothing valid exists."""
        cp = self.latest()
        return dict(cp.payload) if cp else None

    def mark_complete(self, state_id: str) -> int:
        """Remove checkpoints for ``state_id``; returns removals."""
        removed = 0
        with self._lock:
            for cp in self.checkpoints():
                if cp.state_id == state_id:
                    try:
                        self._path(cp.seq, cp.state_id).unlink()
                        removed += 1
                    except OSError:
                        pass
        return removed

    def stats(self) -> dict[str, Any]:
        with self._lock:
            cps = self.checkpoints()
            return {"keep": self._keep,
                    "valid_checkpoints": len(cps),
                    "latest_seq": cps[0].seq if cps else 0,
                    "directory": str(self._dir)}
