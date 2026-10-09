"""Memory export/import. Slice 318.

JSONL backup and restore for decision memory. Each line is a
self-describing envelope::

    {"schema": "hugrgate.memory/episode", "version": 1, "payload": {...}}
    {"schema": "hugrgate.memory/compaction-summary", "version": 1, ...}

:func:`export_jsonl` writes episodes (in chronological order) and, by
default, compaction summaries. :func:`import_jsonl` rebuilds them:
episodes keep their original ids (duplicates are skipped and
reported, never overwritten); malformed lines are skipped with a
report when ``skip_bad_lines=True`` (the default) or raise
:class:`MemoryError` in strict mode. Unknown schemas or versions are
never silently accepted.

Export is an owner-grade operation: the file contains every privacy
class verbatim, including ``forbidden``. Treat exports like database
dumps — encrypt at rest, restrict access.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from hugrgate.errors import HugrGateError, MemoryError, MigrationError
from hugrgate.gauntlet.store_migrate import Migration, MigrationRegistry
from hugrgate.memory.compaction import CompactionSummary
from hugrgate.memory.history import Episode
from hugrgate.memory.query import MemoryQuery
from hugrgate.memory.types import HistoryLike

__all__ = [
    "MEMORY_EXPORT_VERSION",
    "MEMORY_MIGRATIONS",
    "ExportReport",
    "ImportReport",
    "export_jsonl",
    "import_jsonl",
    "register_memory_migration",
]

#: Current export schema version. Bump when the envelope changes.
MEMORY_EXPORT_VERSION = 1

_EPISODE_SCHEMA = "hugrgate.memory/episode"
_SUMMARY_SCHEMA = "hugrgate.memory/compaction-summary"

#: Migration steps for memory export envelopes, keyed by schema.
#: Slice 485: old backups migrate forward instead of being rejected.
MEMORY_MIGRATIONS = MigrationRegistry()


def register_memory_migration(schema: str, from_version: Any,
                              to_version: Any,
                              func: Any) -> Migration:
    """Register one memory-export migration step (slice 485).

    ``func`` maps the old payload dict to the new payload dict.
    """
    return MEMORY_MIGRATIONS.register(
        Migration(schema, from_version, to_version, func)
    )


@dataclass(frozen=True)
class ExportReport:
    """What :func:`export_jsonl` wrote."""

    path: str
    episodes: int
    summaries: int
    bytes: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "path": self.path,
            "episodes": self.episodes,
            "summaries": self.summaries,
            "bytes": self.bytes,
        }


@dataclass
class ImportReport:
    """What :func:`import_jsonl` did."""

    imported: int = 0
    summaries_imported: int = 0
    skipped_bad: int = 0
    skipped_duplicates: int = 0
    errors: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "imported": self.imported,
            "summaries_imported": self.summaries_imported,
            "skipped_bad": self.skipped_bad,
            "skipped_duplicates": self.skipped_duplicates,
            "errors": list(self.errors),
        }


def _envelope(schema: str, payload: dict[str, Any]) -> str:
    return json.dumps({"schema": schema, "version": MEMORY_EXPORT_VERSION,
                       "payload": payload}, sort_keys=True, default=str)


def export_jsonl(history: HistoryLike, path: str | Path, *,
                 include_summaries: bool = True) -> ExportReport:
    """Write history episodes (chronological) + summaries as JSONL."""
    target = Path(path)
    episodes = history.find(
        MemoryQuery(sort_by="recorded_at", descending=False))
    lines = [_envelope(_EPISODE_SCHEMA, e.to_dict()) for e in episodes]
    summaries: list[CompactionSummary] = []
    get_summaries = getattr(history, "compaction_summaries", None)
    if include_summaries and callable(get_summaries):
        summaries = get_summaries()
        lines.extend(_envelope(_SUMMARY_SCHEMA, s.to_dict())
                     for s in summaries)
    text = "".join(line + "\n" for line in lines)
    target.write_text(text, encoding="utf-8")
    return ExportReport(path=str(target), episodes=len(episodes),
                        summaries=len(summaries),
                        bytes=len(text.encode("utf-8")))


def _parse_line(line: str, lineno: int) -> tuple[str, dict[str, Any]]:
    try:
        envelope = json.loads(line)
    except json.JSONDecodeError as exc:
        raise MemoryError(f"line {lineno}: invalid JSON: {exc}",
                          lineno=lineno) from exc
    if not isinstance(envelope, dict):
        raise MemoryError(f"line {lineno}: envelope must be an object",
                          lineno=lineno)
    schema = envelope.get("schema")
    version = envelope.get("version")
    if schema not in (_EPISODE_SCHEMA, _SUMMARY_SCHEMA):
        raise MemoryError(f"line {lineno}: unknown schema {schema!r}",
                          lineno=lineno, schema=schema)
    if version != MEMORY_EXPORT_VERSION:
        # Slice 485: migrate old envelopes forward when a path is
        # registered instead of rejecting the whole backup.
        payload = envelope.get("payload")
        if not isinstance(payload, dict):
            raise MemoryError(f"line {lineno}: payload must be an object",
                              lineno=lineno)
        try:
            migrated = MEMORY_MIGRATIONS.migrate(
                schema, payload, version, MEMORY_EXPORT_VERSION)
        except MigrationError as exc:
            raise MemoryError(
                f"line {lineno}: unsupported version {version!r} "
                f"(expected {MEMORY_EXPORT_VERSION}): {exc}",
                lineno=lineno, version=version) from exc
        envelope = {"schema": schema, "version": MEMORY_EXPORT_VERSION,
                    "payload": migrated}
    payload = envelope.get("payload")
    if not isinstance(payload, dict):
        raise MemoryError(f"line {lineno}: payload must be an object",
                          lineno=lineno)
    return schema, payload


def import_jsonl(history: HistoryLike, path: str | Path, *,
                 skip_bad_lines: bool = True) -> ImportReport:
    """Restore a history from :func:`export_jsonl` output."""
    target = Path(path)
    try:
        text = target.read_text(encoding="utf-8")
    except OSError as exc:
        raise MemoryError(f"cannot read {target}: {exc}") from exc
    report = ImportReport()
    add_summary = getattr(history, "add_compaction_summary", None)
    for lineno, line in enumerate(text.splitlines(), 1):
        if not line.strip():
            continue
        try:
            schema, payload = _parse_line(line, lineno)
            if schema == _EPISODE_SCHEMA:
                episode = Episode.from_dict(payload)
                history.import_episode(episode)
                report.imported += 1
            else:
                if callable(add_summary):
                    add_summary(CompactionSummary.from_dict(payload))
                    report.summaries_imported += 1
                else:
                    report.skipped_bad += 1
                    report.errors.append(
                        f"line {lineno}: history cannot store summaries")
        except MemoryError as exc:
            if exc.message.startswith("duplicate episode_id"):
                report.skipped_duplicates += 1
            elif skip_bad_lines:
                report.skipped_bad += 1
                report.errors.append(str(exc.message))
            else:
                raise
        except (ValueError, TypeError, HugrGateError) as exc:
            if skip_bad_lines:
                report.skipped_bad += 1
                report.errors.append(f"line {lineno}: {exc}")
            else:
                raise MemoryError(
                    f"line {lineno}: bad payload: {exc}",
                    lineno=lineno) from exc
    return report
