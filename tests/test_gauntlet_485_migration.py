"""Slice 485 — upgrade/migration gauntlet.

``hugrgate/memory/io.py`` hard-rejected any export envelope whose
version was not current — old backups died on format bumps. This
slice adds the generic migration machinery
(``hugrgate/gauntlet/store_migrate.py``), a new ``MigrationError``
in the error taxonomy, and wires the memory import path to
migrate old envelopes forward when a path is registered.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

import hugrgate.memory.io as mem_io
from hugrgate.errors import MemoryError, MigrationError
from hugrgate.gauntlet.store_migrate import (
    Migration,
    MigrationRegistry,
    migrate_envelope_file,
)
from hugrgate.memory import DecisionHistory, export_jsonl, import_jsonl
from hugrgate.provenance import DecisionRecord


def _registry() -> MigrationRegistry:
    return MigrationRegistry()


# --- framework -------------------------------------------------------------


def test_single_hop_migration():
    reg = _registry()
    reg.register(Migration("s", 1, 2, lambda p: {**p, "b": p["a"] * 2}))
    out = reg.migrate("s", {"a": 21}, 1, 2)
    assert out["b"] == 42
    assert out["_migration_history"] == [{"schema": "s", "from": 1, "to": 2}]


def test_multi_hop_plans_shortest_path():
    reg = _registry()
    reg.register(Migration("s", 1, 2, lambda p: {**p, "v": 2}))
    reg.register(Migration("s", 2, 3, lambda p: {**p, "v": 3}))
    reg.register(Migration("s", 1, 3, lambda p: {**p, "v": 99}))
    out = reg.migrate("s", {}, 1, 3)
    assert out["v"] == 99  # direct hop wins over 1->2->3
    assert len(out["_migration_history"]) == 1


def test_multi_hop_chain_applies_in_order():
    reg = _registry()
    order: list[str] = []
    reg.register(Migration("s", 1, 2,
                           lambda p: (order.append("1-2"), {**p, "x": 1})[1]))
    reg.register(Migration("s", 2, 3,
                           lambda p: (order.append("2-3"), {**p, "x": 2})[1]))
    out = reg.migrate("s", {}, 1, 3)
    assert order == ["1-2", "2-3"]
    assert out["x"] == 2


def test_already_current_is_noop():
    reg = _registry()
    out = reg.migrate("s", {"a": 1}, 2, 2)
    assert out == {"a": 1, "_migration_history": []}


def test_no_path_raises_migration_error():
    reg = _registry()
    with pytest.raises(MigrationError) as exc_info:
        reg.migrate("s", {}, 1, 5)
    assert "no migration path" in str(exc_info.value)


def test_duplicate_step_rejected():
    reg = _registry()
    reg.register(Migration("s", 1, 2, lambda p: p))
    with pytest.raises(MigrationError):
        reg.register(Migration("s", 1, 2, lambda p: p))


def test_noop_step_rejected():
    with pytest.raises(MigrationError):
        Migration("s", 1, 1, lambda p: p)


def test_non_callable_rejected():
    with pytest.raises(MigrationError):
        Migration("s", 1, 2, "not-a-function")  # type: ignore[arg-type]


def test_failing_step_wrapped():
    def _boom(payload):
        raise RuntimeError("kaput")

    reg = _registry()
    reg.register(Migration("s", 1, 2, _boom))
    with pytest.raises(MigrationError) as exc_info:
        reg.migrate("s", {}, 1, 2)
    assert "kaput" in str(exc_info.value)


def test_non_dict_result_rejected():
    reg = _registry()
    reg.register(Migration("s", 1, 2, lambda p: ["not", "a", "dict"]))
    with pytest.raises(MigrationError):
        reg.migrate("s", {}, 1, 2)


# --- whole-file envelopes --------------------------------------------------


def _write_envelope(path: Path, schema: str, version: int,
                    payload: dict) -> None:
    path.write_text(json.dumps({"schema": schema, "version": version,
                                "payload": payload}), encoding="utf-8")


def test_envelope_file_migrates_with_backup(tmp_path):
    path = tmp_path / "store.json"
    _write_envelope(path, "s", 1, {"a": 1})
    reg = _registry()
    reg.register(Migration("s", 1, 2, lambda p: {**p, "b": 2}))
    report = migrate_envelope_file(path, reg, 2)
    assert report["migrated"] is True
    assert report["from_version"] == 1
    assert (tmp_path / "store.json.bak").is_file()
    envelope = json.loads(path.read_text(encoding="utf-8"))
    assert envelope["version"] == 2
    assert envelope["payload"]["b"] == 2


def test_envelope_file_idempotent(tmp_path):
    path = tmp_path / "store.json"
    _write_envelope(path, "s", 2, {"a": 1})
    report = migrate_envelope_file(path, _registry(), 2)
    assert report["migrated"] is False
    assert not (tmp_path / "store.json.bak").exists()


def test_envelope_file_rejects_garbage(tmp_path):
    path = tmp_path / "store.json"
    path.write_text("not json", encoding="utf-8")
    with pytest.raises(MigrationError):
        migrate_envelope_file(path, _registry(), 2)


def test_envelope_file_rejects_non_object_payload(tmp_path):
    path = tmp_path / "store.json"
    _write_envelope(path, "s", 1, ["nope"])  # type: ignore[arg-type]
    with pytest.raises(MigrationError):
        migrate_envelope_file(path, _registry(), 2)


# --- memory import wiring --------------------------------------------------


def _record() -> DecisionRecord:
    return DecisionRecord(request_hash="h" * 16, spec={"type": "binary"},
                          backend="local", model="m1", value=True,
                          probability=0.8)


def test_old_memory_backup_migrates_instead_of_rejected(tmp_path, monkeypatch):
    schema = "hugrgate.memory/episode"
    monkeypatch.setattr(mem_io, "MEMORY_MIGRATIONS", MigrationRegistry())
    # v0 used "val" where v1 uses "value" inside the record payload.
    mem_io.register_memory_migration(
        schema, 0, 1,
        lambda p: {**p, "record": {**p["record"], "value": p["record"].pop("val")}},
    )
    hist = DecisionHistory()
    hist.record(_record())
    exported = tmp_path / "export.jsonl"
    export_jsonl(hist, exported)
    lines = exported.read_text(encoding="utf-8").splitlines()
    envelope = json.loads(lines[0])
    assert envelope["version"] == 1
    # Rewind the envelope to the "old" format.
    envelope["version"] = 0
    envelope["payload"]["record"]["val"] = \
        envelope["payload"]["record"].pop("value")
    old_path = tmp_path / "old.jsonl"
    old_path.write_text(json.dumps(envelope) + "\n", encoding="utf-8")

    restored = DecisionHistory()
    report = import_jsonl(restored, old_path, skip_bad_lines=False)
    assert report.imported == 1
    assert restored.count() == 1


def test_unmigratable_version_still_rejected(tmp_path, monkeypatch):
    monkeypatch.setattr(mem_io, "MEMORY_MIGRATIONS", MigrationRegistry())
    hist = DecisionHistory()
    hist.record(_record())
    exported = tmp_path / "export.jsonl"
    export_jsonl(hist, exported)
    envelope = json.loads(exported.read_text(encoding="utf-8").splitlines()[0])
    envelope["version"] = 99
    bad_path = tmp_path / "bad.jsonl"
    bad_path.write_text(json.dumps(envelope) + "\n", encoding="utf-8")
    with pytest.raises(MemoryError) as exc_info:
        import_jsonl(DecisionHistory(), bad_path, skip_bad_lines=False)
    assert "unsupported version" in str(exc_info.value)


# --- error taxonomy --------------------------------------------------------


def test_migration_error_taxonomy():
    assert MigrationError.code == "migration_error"
    assert MigrationError.recoverable is False
    assert "MigrationError" in __import__("hugrgate.errors", fromlist=["x"]).__all__
