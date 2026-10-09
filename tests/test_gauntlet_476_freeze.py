"""Slice 476 — feature freeze enforcement.

The 1.0 freeze is machinery (``hugrgate/gauntlet/freeze.py`` +
``release/freeze.toml``), not a sign on the door: every proposed
change is classified and gated, and public-API growth is detected
by diffing.
"""

from __future__ import annotations

import pytest

from hugrgate.gauntlet.freeze import (
    ChangeRequest,
    FreezeManifest,
    Waiver,
    check_public_api_growth,
    evaluate,
    load_manifest,
)


def _manifest() -> FreezeManifest:
    return load_manifest()


# --- manifest loading ------------------------------------------------------


def test_manifest_loads_from_repo():
    m = _manifest()
    assert m.version == "1.0.0rc1"
    assert m.frozen_at == "2026-10-09"
    assert {"bugfix", "security", "docs", "tests"} <= m.allowed_kinds


def test_manifest_rejects_missing_file(tmp_path):
    with pytest.raises((OSError, ValueError)):
        load_manifest(tmp_path / "nope.toml")


def test_manifest_rejects_corrupt_file(tmp_path):
    bad = tmp_path / "freeze.toml"
    bad.write_text("[freeze]\nversion = 42\n", encoding="utf-8")
    with pytest.raises(ValueError):
        load_manifest(bad)


def test_manifest_rejects_waiver_missing_field(tmp_path):
    bad = tmp_path / "freeze.toml"
    bad.write_text(
        "[freeze]\nversion = \"1.0.0rc1\"\nfrozen_at = \"2026-10-09\"\n"
        "allowed_kinds = [\"bugfix\"]\n[[waivers]]\nid = \"W-1\"\n",
        encoding="utf-8",
    )
    with pytest.raises(ValueError):
        load_manifest(bad)


def test_manifest_accepts_recorded_waiver(tmp_path):
    ok = tmp_path / "freeze.toml"
    ok.write_text(
        "[freeze]\nversion = \"1.0.0rc1\"\nfrozen_at = \"2026-10-09\"\n"
        "allowed_kinds = [\"bugfix\", \"feature\"]\n"
        "[[waivers]]\nid = \"W-1\"\nchange = \"x\"\nreason = \"y\"\napproved_by = \"Volmarr\"\n",
        encoding="utf-8",
    )
    m = load_manifest(ok)
    assert m.waiver_ids() == {"W-1"}


# --- evaluation ------------------------------------------------------------


def test_bugfix_is_allowed():
    v = evaluate(ChangeRequest(kind="bugfix", description="fix race"), _manifest())
    assert v.verdict == "allow"


def test_kind_is_case_insensitive():
    v = evaluate(ChangeRequest(kind="Security", description="cve fix"), _manifest())
    assert v.verdict == "allow"


def test_feature_needs_waiver():
    v = evaluate(ChangeRequest(kind="feature", description="new widget"), _manifest())
    assert v.verdict == "waiver-required"
    assert v.reasons


def test_empty_kind_denied():
    v = evaluate(ChangeRequest(kind="  ", description="mystery"), _manifest())
    assert v.verdict == "deny"


def test_allowed_kind_with_api_touch_needs_waiver():
    v = evaluate(
        ChangeRequest(kind="refactor", description="rename", touches_public_api=True),
        _manifest(),
    )
    assert v.verdict == "waiver-required"


def test_allowed_kind_adding_dependency_needs_waiver():
    v = evaluate(
        ChangeRequest(kind="perf", description="faster", adds_dependency=True),
        _manifest(),
    )
    assert v.verdict == "waiver-required"


def test_unknown_waiver_id_denied():
    v = evaluate(
        ChangeRequest(kind="feature", description="x", waiver_id="W-999"),
        _manifest(),
    )
    assert v.verdict == "deny"


def test_recorded_waiver_allows_feature():
    m = FreezeManifest(
        version="1.0.0rc1",
        frozen_at="2026-10-09",
        allowed_kinds=frozenset({"bugfix"}),
        waivers=(Waiver(id="W-1", change="c", reason="r", approved_by="Volmarr"),),
    )
    v = evaluate(ChangeRequest(kind="feature", description="x", waiver_id="W-1"), m)
    assert v.verdict == "allow"


# --- public API growth detection -------------------------------------------


def test_api_growth_detected():
    diff = check_public_api_growth({"a", "b"}, {"a", "b", "c"})
    assert diff["added"] == ["c"]
    assert diff["removed"] == []
    assert diff["growth"] is True
    assert diff["breakage"] is False


def test_api_removal_flagged_as_breakage():
    diff = check_public_api_growth({"a", "b"}, {"a"})
    assert diff["removed"] == ["b"]
    assert diff["breakage"] is True
    assert diff["growth"] is False


def test_no_drift_is_clean():
    diff = check_public_api_growth({"a"}, {"a"})
    assert diff["growth"] is False and diff["breakage"] is False
