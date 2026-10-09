"""Backend plugin SDK. Slice 439.

Third-party backends plug into HugrGate through the
``hugrgate.backends`` entry-point group::

    # third-party pyproject.toml
    [project.entry-points."hugrgate.backends"]
    mybackend = "mypackage.module:MyBackend"

    # mypackage/module.py
    from hugrgate.backend import Backend
    class MyBackend(Backend):
        name = "mybackend"
        ...

This module is the *loading* side:

- :func:`discover_plugins` — find installed entry points without
  importing them (cheap, never raises on a broken plugin when
  ``on_error="collect"``).
- :func:`load_plugin` — import one entry point, instantiate it,
  and validate it against the :class:`Backend` contract.
- :func:`validate_plugin` — interface + smoke validation.
- :func:`register_discovered_plugins` — load everything and
  register it on a :class:`BackendRegistry`, isolating failures:
  one broken plugin can never take down the others (or the gate).

Failures raise :class:`~hugrgate.errors.PluginError` with the
plugin name attached.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from importlib.metadata import EntryPoint, entry_points
from typing import Any, Literal

from hugrgate.backend import Backend, BackendRegistry
from hugrgate.errors import PluginError
from hugrgate.spec import DecisionSpec

__all__ = [
    "PluginInfo",
    "discover_plugins",
    "load_plugin",
    "register_discovered_plugins",
    "validate_plugin",
]

#: Entry-point group third-party backends register under.
ENTRY_POINT_GROUP = "hugrgate.backends"


@dataclass
class PluginInfo:
    """One discovered plugin: its entry point plus load outcome."""

    name: str
    entry_point: EntryPoint | None = None
    backend: Backend | None = None
    error: PluginError | None = None

    @property
    def loaded(self) -> bool:
        return self.backend is not None


def _iter_entry_points() -> list[EntryPoint]:
    # importlib.metadata entry_points().select() exists on all
    # supported Pythons (>= 3.10).
    return list(entry_points().select(group=ENTRY_POINT_GROUP))


def discover_plugins(
    on_error: Literal["raise", "collect"] = "collect",
) -> tuple[list[PluginInfo], list[PluginInfo]]:
    """Discover installed backend plugins.

    Returns ``(loaded, failed)``. With ``on_error="collect"``
    (default) a broken plugin is reported in ``failed`` with its
    :class:`PluginError`; with ``"raise"`` the first failure raises.
    Entry points are *imported* here — discovery without import is
    not possible for validation, but failures are isolated per
    plugin.
    """
    loaded: list[PluginInfo] = []
    failed: list[PluginInfo] = []
    for ep in _iter_entry_points():
        info = PluginInfo(name=ep.name, entry_point=ep)
        try:
            info.backend = load_plugin(ep.name, entry_point=ep)
        except PluginError as e:
            info.error = e
            if on_error == "raise":
                raise
            failed.append(info)
        else:
            loaded.append(info)
    return loaded, failed


def load_plugin(name: str,
                entry_point: EntryPoint | None = None) -> Backend:
    """Load and validate one plugin by entry-point name.

    Raises :class:`PluginError` when the entry point is missing,
    cannot be imported, does not resolve to a :class:`Backend`
    instance, or fails validation.
    """
    ep = entry_point
    if ep is None:
        matches = [e for e in _iter_entry_points() if e.name == name]
        if not matches:
            raise PluginError(f"no plugin named {name!r} is installed",
                              plugin=name)
        ep = matches[0]
    try:
        obj = ep.load()
    except Exception as e:
        raise PluginError(
            f"plugin {name!r} failed to import: {e}",
            plugin=name) from e
    # Entry points may reference a class (instantiate, no-arg) or an
    # already-built instance.
    backend = obj() if isinstance(obj, type) else obj
    try:
        validate_plugin(backend, name=name)
    except PluginError:
        raise
    except Exception as e:
        raise PluginError(f"plugin {name!r} failed validation: {e}",
                          plugin=name) from e
    return backend


def validate_plugin(backend: Any, name: str = "?") -> None:
    """Validate a plugin object against the Backend contract.

    Raises :class:`PluginError` on the first violation found.
    """
    if not isinstance(backend, Backend):
        raise PluginError(
            f"plugin {name!r} is not a hugrgate.backend.Backend "
            f"(got {type(backend).__name__})", plugin=name)
    bname = backend.name
    if not isinstance(bname, str) or not bname.strip():
        raise PluginError(
            f"plugin {name!r} has an invalid backend name: {bname!r}",
            plugin=name)
    for method in ("capabilities", "supports", "evaluate"):
        if not callable(getattr(backend, method, None)):
            raise PluginError(
                f"plugin {name!r} backend {bname!r} is missing "
                f"callable {method}()", plugin=name)
    caps = backend.capabilities()
    if not isinstance(caps, dict):
        raise PluginError(
            f"plugin {name!r} capabilities() must return a dict, "
            f"got {type(caps).__name__}", plugin=name)
    # Smoke: supports() must accept a spec and return a bool without
    # raising; evaluate() must survive a trivial call when the
    # plugin claims support.
    probe = DecisionSpec.from_dict(
        {"type": "categorical", "options": ["a", "b"]})
    try:
        supported = backend.supports(probe)
    except Exception as e:
        raise PluginError(
            f"plugin {name!r} supports() raised: {e}",
            plugin=name) from e
    if not isinstance(supported, bool):
        raise PluginError(
            f"plugin {name!r} supports() must return bool, got "
            f"{type(supported).__name__}", plugin=name)


@dataclass
class PluginReport:
    """Outcome of :func:`register_discovered_plugins`."""

    registered: list[str] = field(default_factory=list)
    skipped: list[str] = field(default_factory=list)
    errors: list[PluginError] = field(default_factory=list)


def register_discovered_plugins(
    registry: BackendRegistry,
    on_error: Literal["raise", "collect"] = "collect",
    replace: bool = False,
) -> PluginReport:
    """Load every discovered plugin and register it on ``registry``.

    One broken plugin never blocks the others; failures land in
    ``report.errors`` (or raise with ``on_error="raise"``).
    Backends whose name is already registered are skipped unless
    ``replace`` is true.
    """
    report = PluginReport()
    loaded, failed = discover_plugins(on_error=on_error)
    for info in failed:
        assert info.error is not None
        report.errors.append(info.error)
    for info in loaded:
        assert info.backend is not None
        name = info.backend.name
        if registry.get(name) is not None and not replace:
            report.skipped.append(name)
            continue
        try:
            registry.register(info.backend, replace=replace)
        except Exception as e:
            if on_error == "raise":
                raise PluginError(
                    f"plugin {info.name!r} failed to register: {e}",
                    plugin=info.name) from e
            report.errors.append(PluginError(
                f"plugin {info.name!r} failed to register: {e}",
                plugin=info.name))
        else:
            report.registered.append(name)
    return report
