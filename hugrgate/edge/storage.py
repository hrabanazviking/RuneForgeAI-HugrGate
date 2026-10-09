"""Flash-wear-aware storage for edge devices. Slice 191.

SD cards and eMMC die from write amplification: many small writes
cost far more erase cycles than their payload. :class:`WearAwareStore`
is a small persistent key/value store that treats flash as a finite
resource:

- **write budget**: a lifetime byte budget; every flushed byte
  decrements it, and writes beyond the budget raise instead of
  silently killing the card;
- **coalescing buffer**: puts accumulate in RAM and flush as one
  sequential append (one erase-cycle hit instead of dozens);
- **atomic flush**: buffer → temp file → ``os.replace`` → fsync, so
  a power cut (slice 193) can never leave a torn tail;
- **wear telemetry**: bytes written, flush count, and an
  amplification estimate (``bytes_written / payload_bytes``).
- **disk-full mapping** (slice 259): ``ENOSPC``/``EDQUOT`` during
  flush surface as :class:`StorageError` (buffer retained for retry),
  never a raw ``OSError``.

Reads are served from an in-RAM index rebuilt from the log at open;
``compact()`` rewrites only live keys when the log grows stale-heavy.
"""

from __future__ import annotations

import contextlib
import errno
import os
import struct
import threading
from pathlib import Path
from typing import Any

from hugrgate.errors import StorageError

__all__ = [
    "DEFAULT_BUFFER_BYTES",
    "DEFAULT_MAX_VALUE_BYTES",
    "StorageError",
    "WearAwareStore",
]

#: Default coalescing buffer size: flush at 64 KiB of pending puts.
DEFAULT_BUFFER_BYTES = 64 * 1024
#: Largest single value accepted (16 MiB).
DEFAULT_MAX_VALUE_BYTES = 16 * 1024 * 1024

_HEADER = struct.Struct("<I I")  # key_len, value_len; value_len=0xFFFF_FFFF → tombstone
_TOMBSTONE = 0xFFFFFFFF
_MAGIC = b"HGWS0001"


class WearAwareStore:
    """A flash-respecting persistent key/value store."""

    def __init__(self, directory: str | Path, *,
                 write_budget_bytes: int,
                 buffer_bytes: int = DEFAULT_BUFFER_BYTES,
                 max_value_bytes: int = DEFAULT_MAX_VALUE_BYTES):
        if write_budget_bytes <= 0:
            raise StorageError("write_budget_bytes must be > 0")
        if buffer_bytes <= 0:
            raise StorageError("buffer_bytes must be > 0")
        if max_value_bytes <= 0:
            raise StorageError("max_value_bytes must be > 0")
        self._dir = Path(directory)
        self._budget = int(write_budget_bytes)
        self._buffer_bytes = int(buffer_bytes)
        self._max_value = int(max_value_bytes)
        self._lock = threading.RLock()
        self._log_path = self._dir / "data.log"
        self._buffer: list[tuple[str, bytes | None]] = []
        self._buffered_bytes = 0
        self._index: dict[str, bytes] = {}
        self._bytes_written = 0      # physical bytes flushed
        self._payload_bytes = 0      # logical value bytes stored
        self._flush_count = 0
        self._closed = False

    # -- lifecycle ------------------------------------------------------------

    @classmethod
    def open(cls, directory: str | Path, **kwargs: Any) -> WearAwareStore:
        """Create/open a store, rebuilding the index from the log."""
        store = cls(directory, **kwargs)
        store._dir.mkdir(parents=True, exist_ok=True)
        store._replay()
        return store

    def _replay(self) -> None:
        if not self._log_path.exists():
            return
        with open(self._log_path, "rb") as fh:
            data = fh.read()
        # The existing log already cost this wear in a previous session.
        self._bytes_written = len(data)
        off = 0
        if data[:8] != _MAGIC:
            raise StorageError(f"{self._log_path} is not a HugrGate wear store")
        off = 8
        while off < len(data):
            if len(data) - off < _HEADER.size:
                raise StorageError("truncated record header in log")
            key_len, value_len = _HEADER.unpack_from(data, off)
            off += _HEADER.size
            if len(data) - off < key_len + (0 if value_len == _TOMBSTONE else value_len):
                raise StorageError("truncated record body in log")
            key = data[off:off + key_len].decode("utf-8")
            off += key_len
            if value_len == _TOMBSTONE:
                self._index.pop(key, None)
            else:
                value = data[off:off + value_len]
                off += value_len
                self._index[key] = value
                self._payload_bytes += len(value)

    def close(self) -> None:
        """Flush pending writes. Idempotent."""
        with self._lock:
            if not self._closed:
                self.flush()
                self._closed = True

    def __enter__(self) -> WearAwareStore:
        return self

    def __exit__(self, *exc: Any) -> None:
        self.close()

    # -- writes ------------------------------------------------------------------

    @staticmethod
    def _check_key(key: str) -> None:
        if not isinstance(key, str) or not key:
            raise StorageError("key must be a non-empty string")
        if len(key.encode("utf-8")) > 1024:
            raise StorageError("key too long (max 1024 UTF-8 bytes)")

    def put(self, key: str, value: bytes) -> None:
        """Buffer a put; auto-flushes when the buffer fills."""
        self._check_key(key)
        if not isinstance(value, (bytes, bytearray)):
            raise StorageError("value must be bytes")
        if len(value) > self._max_value:
            raise StorageError(
                f"value {len(value)} bytes exceeds max {self._max_value}")
        with self._lock:
            self._ensure_open()
            record = _HEADER.size + len(key.encode("utf-8")) + len(value)
            self._buffer.append((key, bytes(value)))
            self._buffered_bytes += record
            if self._buffered_bytes >= self._buffer_bytes:
                self.flush()

    def delete(self, key: str) -> None:
        """Buffer a tombstone."""
        self._check_key(key)
        with self._lock:
            self._ensure_open()
            self._buffer.append((key, None))
            self._buffered_bytes += _HEADER.size + len(key.encode("utf-8"))
            if self._buffered_bytes >= self._buffer_bytes:
                self.flush()

    def _ensure_open(self) -> None:
        if self._closed:
            raise StorageError("store is closed")

    def flush(self) -> int:
        """Atomically append the buffer to the log. Returns bytes written."""
        with self._lock:
            self._ensure_open()
            if not self._buffer:
                return 0
            payload = bytearray()
            if not self._log_path.exists():
                payload += _MAGIC
            for key, value in self._buffer:
                key_b = key.encode("utf-8")
                if value is None:
                    payload += _HEADER.pack(len(key_b), _TOMBSTONE)
                    payload += key_b
                else:
                    payload += _HEADER.pack(len(key_b), len(value))
                    payload += key_b + value
            blob = bytes(payload)
            if self._bytes_written + len(blob) > self._budget:
                raise StorageError(
                    f"write budget exhausted: {self._bytes_written} + "
                    f"{len(blob)} > {self._budget} bytes; refusing to "
                    f"wear the flash further")
            existing = b""
            if self._log_path.exists():
                with open(self._log_path, "rb") as fh:
                    existing = fh.read()
            tmp = self._log_path.with_suffix(".log.tmp")
            try:
                with open(tmp, "wb") as fh:
                    fh.write(existing + blob)
                    fh.flush()
                    os.fsync(fh.fileno())
                os.replace(tmp, self._log_path)
            except OSError as e:
                # A full (or failed) disk must surface as the taxonomy's
                # StorageError, never a raw OSError — and the torn temp
                # file must not be left behind. The buffer is retained
                # so the write can be retried after space is freed.
                with contextlib.suppress(OSError):
                    tmp.unlink(missing_ok=True)
                if e.errno in (errno.ENOSPC, errno.EDQUOT):
                    raise StorageError(
                        f"disk full while flushing {len(blob)} bytes "
                        f"to {self._log_path}: {e.strerror or e}; "
                        f"buffer retained, retry after freeing space"
                    ) from e
                raise StorageError(
                    f"flush to {self._log_path} failed: "
                    f"{e.strerror or e}") from e
            for key, value in self._buffer:
                if value is None:
                    self._index.pop(key, None)
                else:
                    self._index[key] = value
                    self._payload_bytes += len(value)
            self._bytes_written += len(blob)
            self._flush_count += 1
            self._buffer.clear()
            self._buffered_bytes = 0
            return len(blob)

    # -- reads ---------------------------------------------------------------------

    def get(self, key: str) -> bytes | None:
        """Read-mostly path: RAM index first, then buffered (unflushed) puts."""
        self._check_key(key)
        with self._lock:
            for k, v in reversed(self._buffer):
                if k == key:
                    return v
            return self._index.get(key)

    def __contains__(self, key: object) -> bool:
        return isinstance(key, str) and self.get(key) is not None

    def __len__(self) -> int:
        with self._lock:
            keys = set(self._index)
            for k, v in self._buffer:
                if v is None:
                    keys.discard(k)
                else:
                    keys.add(k)
            return len(keys)

    # -- maintenance -------------------------------------------------------------------

    def compact(self) -> int:
        """Rewrite the log with only live keys. Returns bytes written."""
        with self._lock:
            self._ensure_open()
            self.flush()  # drain the buffer first so the index is complete
            live = dict(self._index)
            payload = bytearray(_MAGIC)
            for key, value in live.items():
                key_b = key.encode("utf-8")
                payload += _HEADER.pack(len(key_b), len(value))
                payload += key_b + value
            blob = bytes(payload)
            if self._bytes_written + len(blob) > self._budget:
                raise StorageError(
                    "write budget exhausted; cannot compact")
            tmp = self._log_path.with_suffix(".log.tmp")
            with open(tmp, "wb") as fh:
                fh.write(blob)
                fh.flush()
                os.fsync(fh.fileno())
            os.replace(tmp, self._log_path)
            self._bytes_written += len(blob)
            self._flush_count += 1
            return len(blob)

    # -- telemetry -------------------------------------------------------------------------

    def wear_stats(self) -> dict[str, Any]:
        """Wear telemetry; JSON-serializable."""
        with self._lock:
            amplification = (self._bytes_written / self._payload_bytes
                             if self._payload_bytes else 0.0)
            return {
                "bytes_written": self._bytes_written,
                "payload_bytes": self._payload_bytes,
                "write_amplification": amplification,
                "flush_count": self._flush_count,
                "budget_bytes": self._budget,
                "budget_remaining": self._budget - self._bytes_written,
                "buffered_bytes": self._buffered_bytes,
                "keys": len(self),
            }

    def to_dict(self) -> dict[str, Any]:
        stats = self.wear_stats()
        stats["directory"] = str(self._dir)
        return stats
