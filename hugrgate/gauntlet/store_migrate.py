"""Upgrade/migration gauntlet for on-disk state (slice 485).

``hugrgate/contracts/migration.py`` migrates spec *dicts*; nothing
migrated on-disk *store files* — ``hugrgate/memory/io.py`` hard
rejected any export whose version was not current, turning old
backups into garbage after a format bump. This module is the
generic machinery:

- :class:`Migration`: one ``from_version -> to_version`` step for a
  named schema, carrying a pure ``payload -> payload`` function.
- :class:`MigrationRegistry`: ``register()`` steps;
  :meth:`plan` finds the shortest path with BFS (multi-hop
  ``1 -> 2 -> 3`` works without registering ``1 -> 3``);
  :meth:`migrate` applies the chain and records history.
- :func:`migrate_envelope_file`: whole-file JSON envelopes
  (``{"schema", "version", "payload"}``) migrated in place with a
  ``.bak`` backup; idempotent — files already at the target are
  left untouched.

Failures raise :class:`hugrgate.errors.MigrationError` (not
recoverable: the registry or the bytes must change).

The memory export path wires this in: see
:func:`hugrgate.memory.io.register_memory_migration`.
"""

from __future__ import annotations

import json
from collections import deque
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from hugrgate.errors import MigrationError

__all__ = [
    "Migration",
    "MigrationRegistry",
    "migrate_envelope_file",
]


@dataclass(frozen=True)
class Migration:
    """One version step for a named schema."""

    schema: str
    from_version: Any
    to_version: Any
    migrate: Any  # Callable[[dict], dict]; typed loosely for py3.10 compat

    def __post_init__(self) -> None:
        if self.from_version == self.to_version:
            raise MigrationError(
                f"no-op migration {self.schema} "
                f"{self.from_version!r} -> {self.to_version!r}"
            )
        if not callable(self.migrate):
            raise MigrationError(
                f"migration {self.schema} {self.from_version!r} -> "
                f"{self.to_version!r} is not callable"
            )


class MigrationRegistry:
    """Version-step registry with shortest-path planning."""

    def __init__(self) -> None:
        self._steps: dict[tuple[str, Any, Any], Migration] = {}

    def register(self, migration: Migration) -> Migration:
        """Register one step; duplicate (schema, from, to) is an error."""
        key = (migration.schema, migration.from_version, migration.to_version)
        if key in self._steps:
            raise MigrationError(f"duplicate migration step {key}")
        self._steps[key] = migration
        return migration

    def step(self, schema: str, from_version: Any,
             to_version: Any) -> Migration | None:
        return self._steps.get((schema, from_version, to_version))

    def plan(self, schema: str, from_version: Any,
             to_version: Any) -> tuple[Migration, ...]:
        """Shortest migration path; empty tuple when already current.

        Raises :class:`MigrationError` when no path exists.
        """
        if from_version == to_version:
            return ()
        # BFS over the version graph for this schema.
        edges: dict[Any, list[tuple[Any, Migration]]] = {}
        for (s, f, _t), migration in self._steps.items():
            if s == schema:
                edges.setdefault(f, []).append((_t, migration))
        queue: deque[tuple[Any, tuple[Migration, ...]]] = deque(
            [(from_version, ())]
        )
        seen = {from_version}
        while queue:
            current, path = queue.popleft()
            for target, migration in sorted(
                edges.get(current, []), key=lambda e: str(e[0])
            ):
                if target in seen:
                    continue
                new_path = (*path, migration)
                if target == to_version:
                    return new_path
                seen.add(target)
                queue.append((target, new_path))
        known = sorted(
            {f"{s}:{f!r}->{t!r}" for (s, f, t) in self._steps if s == schema}
        )
        raise MigrationError(
            f"no migration path for {schema!r} "
            f"{from_version!r} -> {to_version!r}; known: {known}"
        )

    def migrate(self, schema: str, payload: dict[str, Any],
                from_version: Any, to_version: Any) -> dict[str, Any]:
        """Apply the planned chain; each step's output feeds the next.

        The returned payload carries ``_migration_history`` listing
        the applied steps. A raising step aborts with
        :class:`MigrationError` naming the step.
        """
        result = dict(payload)
        history: list[dict[str, Any]] = list(
            result.pop("_migration_history", [])
        )
        for migration in self.plan(schema, from_version, to_version):
            try:
                result = migration.migrate(result)
            except MigrationError:
                raise
            except Exception as exc:
                raise MigrationError(
                    f"migration {schema!r} "
                    f"{migration.from_version!r} -> "
                    f"{migration.to_version!r} failed: {exc}"
                ) from exc
            if not isinstance(result, dict):
                raise MigrationError(
                    f"migration {schema!r} "
                    f"{migration.from_version!r} -> "
                    f"{migration.to_version!r} did not return a dict"
                )
            history.append({
                "schema": schema,
                "from": migration.from_version,
                "to": migration.to_version,
            })
        result["_migration_history"] = history
        return result


def migrate_envelope_file(
    path: str | Path,
    registry: MigrationRegistry,
    target_version: Any,
    *,
    backup: bool = True,
) -> dict[str, Any]:
    """Migrate a whole-file JSON envelope to ``target_version``.

    The file must hold ``{"schema", "version", "payload"}``. Files
    already at the target are returned untouched (idempotent). On
    migration a ``.bak`` copy of the original is kept when
    ``backup=True``. Returns a report dict.
    """
    path = Path(path)
    try:
        envelope = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise MigrationError(f"cannot read envelope {path}: {exc}") from exc
    if not isinstance(envelope, dict):
        raise MigrationError(f"envelope {path} is not an object")
    schema = envelope.get("schema")
    version = envelope.get("version")
    payload = envelope.get("payload")
    if not isinstance(schema, str) or not schema:
        raise MigrationError(f"envelope {path}: schema must be a string")
    if not isinstance(payload, dict):
        raise MigrationError(f"envelope {path}: payload must be an object")
    if version == target_version:
        return {"path": str(path), "migrated": False,
                "version": version, "steps": []}
    new_payload = registry.migrate(schema, payload, version, target_version)
    if backup:
        path.with_suffix(path.suffix + ".bak").write_bytes(
            path.read_bytes()
        )
    envelope = {"schema": schema, "version": target_version,
                "payload": new_payload}
    path.write_text(json.dumps(envelope, sort_keys=True, default=str)
                    + "\n", encoding="utf-8")
    history = new_payload.get("_migration_history", [])
    return {"path": str(path), "migrated": True,
            "from_version": version, "to_version": target_version,
            "steps": history}
