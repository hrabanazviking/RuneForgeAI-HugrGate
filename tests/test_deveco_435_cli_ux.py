"""Slice 435 — CLI UX overhaul (fast tests).

Covers --format table/yaml output, the completion scripts,
did-you-mean suggestions, and doctor against a stubbed client.
The live-server doctor test lives in test_deveco_435_doctor_live.py.
"""

from __future__ import annotations

import json

import pytest

from hugrgate.cli import _render_table, build_parser, main


def _spec_state(tmp_path):
    spec = tmp_path / "spec.yaml"
    state = tmp_path / "state.yaml"
    spec.write_text('type: categorical\noptions: [a, b]\n')
    state.write_text('f: 1.0\n')
    return str(spec), str(state)


def test_table_renderer_aligns_columns():
    out = _render_table(
        [{"name": "uniform", "lat": 0.5}, {"name": "keyword-long", "lat": 12.0}],
        ["name", "lat"])
    lines = out.splitlines()
    assert lines[0].startswith("name")
    assert "uniform" in lines[2] and "keyword-long" in lines[3]
    # separator row of dashes
    assert set(lines[1].replace(" ", "")) == {"-"}


def test_backends_table_format(capsys):
    assert main(["--format", "table", "backends"]) == 0
    out = capsys.readouterr().out
    assert "name" in out.splitlines()[0]
    assert "uniform" in out


def test_backends_json_still_default(capsys):
    assert main(["backends"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert "backends" in payload


def test_backends_yaml_format(capsys):
    assert main(["--format", "yaml", "backends"]) == 0
    out = capsys.readouterr().out
    assert "backends:" in out
    assert "uniform" in out


def test_models_table_format(capsys):
    assert main(["--format", "table", "models"]) == 0
    out = capsys.readouterr().out
    assert "name" in out.splitlines()[0]


def test_decide_table_format(tmp_path, capsys):
    spec, state = _spec_state(tmp_path)
    assert main(["--format", "table", "decide",
                 "--spec", spec, "--state", state]) == 0
    out = capsys.readouterr().out
    assert "value" in out.splitlines()[0]
    assert "probability" in out


@pytest.mark.parametrize("shell", ["bash", "zsh", "fish"])
def test_completion_scripts_list_commands(capsys, shell):
    assert main(["completion", shell]) == 0
    out = capsys.readouterr().out
    for cmd in ("decide", "backends", "doctor", "completion", "openapi"):
        assert cmd in out, f"{cmd} missing from {shell} completion"


def test_did_you_mean_suggests_command(capsys):
    with pytest.raises(SystemExit) as exc:
        main(["decid"])
    assert exc.value.code == 2
    err = capsys.readouterr().err
    assert "did you mean 'decide'?" in err


def test_format_flag_rejects_unknown_choice(capsys):
    with pytest.raises(SystemExit):
        main(["--format", "xml", "backends"])


class _FakeClient:
    def __init__(self, **kw):
        self.kw = kw

    def health(self):
        return {"status": "ok", "version": "0.1.0", "reachable": True,
                "uptime_s": 1.0, "decisions_served": 3}

    def protocol(self):
        return {"protocol_version": "1.0",
                "supported_versions": ["1.0"], "service_version": "0.1.0"}

    def backends(self):
        return [{"name": "uniform"}]

    def decide(self, state, spec, policy=None, backend_name=None,
               context=None):
        from hugrgate.result import DecisionResult
        return DecisionResult(value="a", probability=1.0,
                              distribution={"a": 1.0}, uncertainty=0.0,
                              accepted=True, backend="uniform",
                              model="uniform-1.0", latency_ms=0.1,
                              calibration_profile="none",
                              fallback_used=False, metadata={})

    def close(self):
        pass


class _DeadClient(_FakeClient):
    def health(self):
        return {"reachable": False, "error": "connection refused"}


def test_doctor_all_checks_pass(monkeypatch, capsys):
    import hugrgate.client
    monkeypatch.setattr(hugrgate.client, "HugrGateClient", _FakeClient)
    assert main(["doctor", "--url", "http://x"]) == 0
    out = capsys.readouterr().out
    assert "[ok] service reachable" in out
    assert "[ok] protocol version agreement" in out
    assert "[ok] backend inventory" in out
    assert "[ok] end-to-end decision" in out
    assert "all checks passed" in out


def test_doctor_reports_unreachable(monkeypatch, capsys):
    import hugrgate.client
    monkeypatch.setattr(hugrgate.client, "HugrGateClient", _DeadClient)
    assert main(["doctor", "--url", "http://x"]) == 1
    out = capsys.readouterr().out
    assert "[FAIL] service reachable" in out
    assert "1 check(s) failed" in out


def test_doctor_detects_protocol_skew(monkeypatch, capsys):
    class Skewed(_FakeClient):
        def protocol(self):
            return {"protocol_version": "2.0",
                    "supported_versions": ["2.0"],
                    "service_version": "9.9.9"}

    import hugrgate.client
    monkeypatch.setattr(hugrgate.client, "HugrGateClient", Skewed)
    assert main(["doctor", "--url", "http://x"]) == 1
    out = capsys.readouterr().out
    assert "[FAIL] protocol version agreement" in out


def test_parser_lists_new_commands():
    from hugrgate.cli import _command_names
    choices = _command_names(build_parser())
    assert "doctor" in choices
    assert "completion" in choices
    assert "openapi" in choices
