"""Slice 439 — backend plugin SDK.

Fake entry points (a good backend, an import bomb, a wrong-type
object, a backend with a bad name) exercise discovery isolation,
loading, validation, and registry registration. A real
BackendRegistry proves the loaded plugin actually decides.
"""

from __future__ import annotations

from collections.abc import Mapping
from importlib.metadata import EntryPoint
from typing import Any

import pytest

from hugrgate.backend import Backend, BackendRegistry
from hugrgate.core import HugrGate
from hugrgate.errors import PluginError
from hugrgate.plugins import (
    PluginInfo,
    discover_plugins,
    load_plugin,
    register_discovered_plugins,
    validate_plugin,
)
from hugrgate.spec import DecisionSpec


class GoodBackend(Backend):
    name = "goodplug"

    def capabilities(self) -> dict[str, Any]:
        return {"kinds": ["categorical"]}

    def supports(self, spec: DecisionSpec) -> bool:
        return True

    def evaluate(self, state: Mapping[str, Any], spec: DecisionSpec,
                 context: Mapping[str, Any] | None = None):
        from hugrgate.result import DecisionResult
        return DecisionResult(value="a", probability=1.0,
                              distribution={"a": 1.0}, uncertainty=0.0,
                              accepted=True, backend=self.name,
                              model="goodplug-1", latency_ms=0.1,
                              calibration_profile="none",
                              fallback_used=False, metadata={})


class BadNameBackend(GoodBackend):
    name = "  "


class NoCapabilitiesBackend(GoodBackend):
    name = "nocaps"

    def capabilities(self):  # type: ignore[no-untyped-def]
        return ["not", "a", "dict"]


def _ep(name: str, target: str) -> EntryPoint:
    return EntryPoint(name=name, value=target,
                      group="hugrgate.backends")


GOOD_EP = _ep("goodplug",
              "tests.test_deveco_439_plugins:GoodBackend")
BOMB_EP = _ep("bomb",
              "tests.test_deveco_439_plugins:_missing_attr_xyz")
WRONG_EP = _ep("wrong",
               "tests.test_deveco_439_plugins:GoodBackend.name")
BADNAME_EP = _ep("badname",
                 "tests.test_deveco_439_plugins:BadNameBackend")
NOCAPS_EP = _ep("nocaps",
                "tests.test_deveco_439_plugins:NoCapabilitiesBackend")


@pytest.fixture()
def fake_entry_points(monkeypatch):
    import hugrgate.plugins
    eps = [GOOD_EP, BOMB_EP, WRONG_EP, BADNAME_EP, NOCAPS_EP]
    monkeypatch.setattr(hugrgate.plugins, "_iter_entry_points",
                        lambda: list(eps))
    return eps


def test_discover_isolates_failures(fake_entry_points):
    loaded, failed = discover_plugins()
    assert [i.name for i in loaded] == ["goodplug"]
    assert sorted(i.name for i in failed) == [
        "badname", "bomb", "nocaps", "wrong"]
    for info in failed:
        assert isinstance(info.error, PluginError)
        assert info.error.code == "plugin_error"
        assert info.error.recoverable is True


def test_discover_raise_mode(fake_entry_points):
    with pytest.raises(PluginError):
        discover_plugins(on_error="raise")


def test_load_plugin_good(fake_entry_points):
    backend = load_plugin("goodplug")
    assert isinstance(backend, Backend)
    assert backend.name == "goodplug"


def test_load_plugin_missing_name(fake_entry_points):
    with pytest.raises(PluginError) as exc:
        load_plugin("nope")
    assert "no plugin named" in exc.value.message


def test_load_plugin_import_bomb(fake_entry_points):
    with pytest.raises(PluginError) as exc:
        load_plugin("bomb")
    assert "failed to import" in exc.value.message


def test_load_plugin_wrong_type(fake_entry_points):
    with pytest.raises(PluginError) as exc:
        load_plugin("wrong")
    assert "not a hugrgate.backend.Backend" in exc.value.message


def test_validate_plugin_bad_name():
    with pytest.raises(PluginError):
        validate_plugin(BadNameBackend())


def test_validate_plugin_bad_capabilities():
    with pytest.raises(PluginError) as exc:
        validate_plugin(NoCapabilitiesBackend())
    assert "must return a dict" in exc.value.message


def test_validate_plugin_requires_instance():
    with pytest.raises(PluginError):
        validate_plugin(GoodBackend)  # class, not instance
    validate_plugin(GoodBackend())  # instance is fine


def test_register_discovered_plugins(fake_entry_points):
    registry = BackendRegistry()
    report = register_discovered_plugins(registry)
    assert report.registered == ["goodplug"]
    assert len(report.errors) == 4
    assert registry.get("goodplug") is not None


def test_register_skips_duplicates(fake_entry_points):
    registry = BackendRegistry()
    registry.register(GoodBackend())
    report = register_discovered_plugins(registry)
    assert report.registered == []
    assert report.skipped == ["goodplug"]


def test_plugin_backend_decides_end_to_end(fake_entry_points):
    gate = HugrGate()
    report = register_discovered_plugins(gate.registry)
    assert report.registered == ["goodplug"]
    spec = DecisionSpec.from_dict(
        {"type": "categorical", "options": ["a", "b"]})
    result = gate.decide({"f": 1.0}, spec, backend_name="goodplug")
    assert result.value == "a"
    assert result.backend == "goodplug"


def test_cli_plugins_lists_status(monkeypatch, capsys, fake_entry_points):
    from hugrgate.cli import main
    assert main(["plugins"]) == 1  # failures present -> exit 1
    out = capsys.readouterr().out
    assert "goodplug" in out
    assert "FAILED" in out


def test_cli_plugins_table_format(monkeypatch, capsys, fake_entry_points):
    from hugrgate.cli import main
    assert main(["--format", "table", "plugins"]) == 1
    out = capsys.readouterr().out
    assert "name" in out.splitlines()[0]
    assert "status" in out


def test_plugin_info_loaded_property():
    info = PluginInfo(name="x")
    assert info.loaded is False
    info.backend = GoodBackend()
    assert info.loaded is True
