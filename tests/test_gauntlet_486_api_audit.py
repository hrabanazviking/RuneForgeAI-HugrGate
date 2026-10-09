"""Slice 486 — API compatibility audit.

The append-only surface policy (slice 003) becomes executable:
``hugrgate/gauntlet/api_audit.py`` snapshots every module's
``__all__`` contract, diffs it against the checked-in 1.0 baseline,
and classifies drift as additive / breaking / clean. Signature
narrowings (removed params, new required params, optional turned
required) are breaking; new defaulted params are fine.
"""

from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from hugrgate.gauntlet.api_audit import (
    diff_snapshots,
    load_baseline,
    save_baseline,
    signatures_compatible,
    snapshot_package,
)

ROOT = Path(__file__).resolve().parent.parent
BASELINE = ROOT / "docs" / "gauntlet" / "api-baseline-1.0.json"


def _snap() -> dict:
    return {
        "m": {
            "keep": {"kind": "function", "sig": "(a, b=1)"},
            "gone": {"kind": "function", "sig": "(x)"},
            "narrow": {"kind": "function", "sig": "(a)"},
            "widen": {"kind": "function", "sig": "(a)"},
            "const": {"kind": "constant", "sig": ""},
        }
    }


def test_added_names_are_additive_not_breaking():
    base, cur = _snap(), _snap()
    cur["m"]["new"] = {"kind": "function", "sig": "(a)"}
    diff = diff_snapshots(base, cur)
    assert diff.added_names == [("m", "new")]
    assert diff.additive is True
    assert diff.breaking is False


def test_removed_names_are_breaking():
    base, cur = _snap(), _snap()
    del cur["m"]["gone"]
    diff = diff_snapshots(base, cur)
    assert diff.removed_names == [("m", "gone")]
    assert diff.breaking is True


def test_removed_modules_are_breaking():
    base, cur = _snap(), _snap()
    cur["m2"] = dict(cur["m"])
    base["m2"] = dict(base["m"])
    del cur["m2"]
    diff = diff_snapshots(base, cur)
    assert diff.removed_modules == ["m2"]
    assert diff.breaking is True


def test_added_modules_are_additive():
    base, cur = _snap(), _snap()
    cur["m2"] = dict(cur["m"])
    diff = diff_snapshots(base, cur)
    assert diff.added_modules == ["m2"]
    assert diff.breaking is False


def test_signature_narrowing_is_breaking():
    base, cur = _snap(), _snap()
    cur["m"]["narrow"] = {"kind": "function", "sig": "(a, b)"}
    diff = diff_snapshots(base, cur)
    assert len(diff.changed) == 1
    assert diff.changed[0][:2] == ("m", "narrow")
    assert diff.breaking is True


def test_signature_widening_with_default_is_clean():
    base, cur = _snap(), _snap()
    cur["m"]["widen"] = {"kind": "function", "sig": "(a, b=2)"}
    diff = diff_snapshots(base, cur)
    assert diff.changed == []
    assert diff.breaking is False


def test_kind_change_is_breaking():
    base, cur = _snap(), _snap()
    cur["m"]["const"] = {"kind": "function", "sig": "(a)"}
    diff = diff_snapshots(base, cur)
    assert diff.breaking is True


def test_signatures_compatible_cases():
    assert signatures_compatible("(a, b)", "(a, b, c=1)")
    assert not signatures_compatible("(a, b)", "(a, b, c)")
    assert not signatures_compatible("(a, b=1)", "(a, b)")
    assert signatures_compatible("(a, b)", "(a, b=1)")
    assert not signatures_compatible("garbage", "(a)")


def test_baseline_loads_and_matches_live_tree():
    assert BASELINE.is_file()
    baseline = load_baseline(BASELINE)
    assert len(baseline) > 400
    diff = diff_snapshots(baseline, snapshot_package(ROOT))
    assert diff.summary() == "no drift", diff.summary()
    assert diff.breaking is False


def test_baseline_is_canonical_json():
    text = BASELINE.read_text(encoding="utf-8")
    assert text == json.dumps(json.loads(text), indent=2, sort_keys=True) + "\n"


def test_load_baseline_rejects_corrupt(tmp_path):
    bad = tmp_path / "base.json"
    bad.write_text("{nope", encoding="utf-8")
    with pytest.raises(ValueError):
        load_baseline(bad)
    bad.write_text("[1, 2]", encoding="utf-8")
    with pytest.raises(ValueError):
        load_baseline(bad)


def test_save_baseline_roundtrip(tmp_path):
    snap = _snap()
    path = save_baseline(tmp_path / "b.json", copy.deepcopy(snap))
    assert load_baseline(path) == snap
