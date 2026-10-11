"""Slice 18 (dusk run, Sif's Loom Wave C) — decide provenance summary.

``cmd_decide`` prints a one-line provenance summary (decision id,
backend, confidence) on the default (human) output only. Explicit
``--format json/table/yaml`` machine outputs must stay unchanged.
"""

from __future__ import annotations

import json
import re

import pytest

from hugrgate.cli import main
from hugrgate.loaders import load_spec, load_state
from hugrgate.provenance import DecisionRecord
from hugrgate.server import build_gate

_SUMMARY_RE = re.compile(
    r"^provenance: decision=([0-9a-f]{16}) backend=(\S+) "
    r"confidence=([0-9.]+)$",
    re.MULTILINE)


def _spec_state(tmp_path):
    spec = tmp_path / "spec.yaml"
    state = tmp_path / "state.yaml"
    spec.write_text("type: categorical\noptions: [a, b]\n")
    state.write_text("f: 1.0\n")
    return str(spec), str(state)


def _expected_decision(spec_path, state_path):
    """Recompute the in-process decision + its provenance request hash."""
    spec = load_spec(spec_path)
    state = load_state(state_path)
    result = build_gate().decide(state, spec, None, backend_name=None)
    record = DecisionRecord.from_decision(state, spec, result)
    return record.request_hash, result


def test_default_output_has_provenance_summary(tmp_path, capsys):
    spec, state = _spec_state(tmp_path)
    assert main(["decide", "--spec", spec, "--state", state]) == 0
    out = capsys.readouterr().out
    match = _SUMMARY_RE.search(out)
    assert match, ("provenance summary line missing from default "
                   f"output:\n{out}")
    decision_id, result = _expected_decision(spec, state)
    assert match.group(1) == decision_id
    assert match.group(2) == result.backend
    assert float(match.group(3)) == pytest.approx(result.probability,
                                                  abs=1e-4)


def test_explicit_json_format_unchanged(tmp_path, capsys):
    spec, state = _spec_state(tmp_path)
    assert main(["--format", "json", "decide", "--spec", spec,
                 "--state", state]) == 0
    out = capsys.readouterr().out
    assert "provenance:" not in out
    # Must still be pure JSON — no stray summary line appended.
    payload = json.loads(out)
    assert payload["abstained"] is False
    decision = payload["decision"]
    assert decision["backend"]
    assert 0.0 <= decision["probability"] <= 1.0


@pytest.mark.parametrize("fmt", ["table", "yaml"])
def test_other_machine_formats_untouched(tmp_path, capsys, fmt):
    spec, state = _spec_state(tmp_path)
    assert main(["--format", fmt, "decide", "--spec", spec,
                 "--state", state]) == 0
    out = capsys.readouterr().out
    assert "provenance:" not in out
