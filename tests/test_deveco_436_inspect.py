"""Slice 436 — interactive inspector REPL.

Drives ``InspectSession`` with a scripted stdin: help, unknown
commands, backends/health/protocol against a stubbed client,
a full decide→last flow, url switching, and clean EOF/quit exits.
"""

from __future__ import annotations

import pytest

from hugrgate.inspect import InspectSession, run_inspect


class _FakeClient:
    def __init__(self, url=None, **kw):
        self.url = url

    def health(self):
        return {"status": "ok", "version": "0.1.0", "reachable": True,
                "uptime_s": 2.0, "decisions_served": 7}

    def protocol(self):
        return {"protocol_version": "1.0",
                "supported_versions": ["1.0"],
                "service_version": "0.1.0", "mode": "http"}

    def backends(self):
        return [{"name": "uniform", "is_remote": False},
                {"name": "keyword", "is_remote": False}]

    def decide(self, state, spec, policy=None, backend_name=None,
               context=None):
        from hugrgate.result import DecisionResult
        return DecisionResult(value="b", probability=0.75,
                              distribution={"a": 0.25, "b": 0.75},
                              uncertainty=0.1, accepted=True,
                              backend=backend_name or "uniform",
                              model="uniform-1.0", latency_ms=0.2,
                              calibration_profile="none",
                              fallback_used=False,
                              metadata={"k": "v"})

    def close(self):
        pass


@pytest.fixture()
def session(monkeypatch):
    import hugrgate.client
    import hugrgate.inspect
    monkeypatch.setattr(hugrgate.client, "HugrGateClient", _FakeClient)
    sess = InspectSession(url="http://stub")
    yield sess
    sess.close()


def _spec_state(tmp_path):
    spec = tmp_path / "spec.yaml"
    state = tmp_path / "state.yaml"
    spec.write_text('type: categorical\noptions: [a, b]\n')
    state.write_text('f: 1.0\n')
    return str(spec), str(state)


def test_help_lists_commands(session, capsys):
    session.handle_line("help")
    out = capsys.readouterr().out
    assert "decide <spec> <state>" in out
    assert "quit" in out


def test_unknown_command_reported(session, capsys):
    session.handle_line("frobnicate")
    assert "unknown command: frobnicate" in capsys.readouterr().out


def test_backends_lists_names(session, capsys):
    session.handle_line("backends")
    out = capsys.readouterr().out
    assert "- uniform" in out
    assert "- keyword" in out


def test_health_reports_ok(session, capsys):
    session.handle_line("health")
    assert "ok — version 0.1.0" in capsys.readouterr().out


def test_protocol_reports_version(session, capsys):
    session.handle_line("protocol")
    assert "protocol 1.0" in capsys.readouterr().out


def test_decide_then_last(session, tmp_path, capsys):
    spec, state = _spec_state(tmp_path)
    session.handle_line(f"decide {spec} {state} --backend keyword")
    out = capsys.readouterr().out
    assert "value='b'" in out
    assert "backend=keyword" in out
    session.handle_line("last")
    out = capsys.readouterr().out
    assert "probability: 0.7500" in out
    assert '"b": 0.75' in out


def test_last_before_decide(session, capsys):
    session.handle_line("last")
    assert "no decision yet" in capsys.readouterr().out


def test_decide_usage_error(session, capsys):
    session.handle_line("decide only-one-arg")
    assert "usage: decide" in capsys.readouterr().out


def test_decide_missing_file(session, capsys):
    session.handle_line("decide /nope/spec.yaml /nope/state.yaml")
    assert "error:" in capsys.readouterr().out


def test_decide_unknown_flag(session, capsys):
    session.handle_line("decide a b --bogus")
    assert "unknown flag: --bogus" in capsys.readouterr().out


def test_url_switches_service(session, capsys, monkeypatch):
    seen = {}
    orig = _FakeClient.__init__

    def fake_init(self, url=None, **kw):
        seen["url"] = url
        orig(self, url=url, **kw)

    monkeypatch.setattr(_FakeClient, "__init__", fake_init)
    session.handle_line("url http://other:9999")
    assert seen["url"] == "http://other:9999"
    assert "now talking to http://other:9999" in capsys.readouterr().out
    session.handle_line("url")
    assert "http://other:9999" in capsys.readouterr().out


def test_quit_variants_stop_loop(session):
    for cmd in ("quit", "exit", "q"):
        session.running = True
        session.handle_line(cmd)
        assert session.running is False


def test_run_scripted_session(monkeypatch, tmp_path, capsys):
    import builtins

    import hugrgate.client
    monkeypatch.setattr(hugrgate.client, "HugrGateClient", _FakeClient)
    spec, state = _spec_state(tmp_path)
    lines = iter(["help", "health", f"decide {spec} {state}",
                  "last", "bogus-cmd", "quit"])
    monkeypatch.setattr(builtins, "input", lambda prompt="": next(lines))
    assert run_inspect("http://stub") == 0
    out = capsys.readouterr().out
    assert "hugrgate inspector" in out
    assert "unknown command: bogus-cmd" in out
    assert out.rstrip().endswith("bye.")


def test_run_handles_eof(monkeypatch, capsys):
    import builtins

    import hugrgate.client
    monkeypatch.setattr(hugrgate.client, "HugrGateClient", _FakeClient)

    def boom(prompt=""):
        raise EOFError

    monkeypatch.setattr(builtins, "input", boom)
    assert run_inspect("http://stub") == 0
    assert "bye." in capsys.readouterr().out


def test_run_handles_keyboard_interrupt(monkeypatch, capsys):
    import builtins

    import hugrgate.client
    monkeypatch.setattr(hugrgate.client, "HugrGateClient", _FakeClient)

    def boom(prompt=""):
        raise KeyboardInterrupt

    monkeypatch.setattr(builtins, "input", boom)
    assert run_inspect("http://stub") == 0
