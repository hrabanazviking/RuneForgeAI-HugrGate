"""API compatibility audit for the 1.0 release (slice 486).

The package surface is append-only within a major version
(slice 003's policy); this module makes the policy executable:

- :func:`snapshot_package`: capture every ``hugrgate`` module's
  ``__all__`` contract as ``{module: {name: {kind, sig}}}``.
- :func:`save_baseline` / :func:`load_baseline`: the JSON baseline
  lives at ``docs/gauntlet/api-baseline-1.0.json``.
- :func:`diff_snapshots`: classify drift as additive (new modules /
  names — allowed under the freeze only with a waiver, slice 476),
  breaking (removed modules / names, signature narrowings, kind
  changes), or clean.
- :func:`signatures_compatible`: a new signature is compatible when
  every call the old signature accepted still binds — new
  *defaulted* parameters are fine, new required parameters or
  removed parameters are not.

Breaking drift fails the 1.0 release gate; additive drift needs a
freeze waiver.
"""

from __future__ import annotations

import ast
import importlib
import inspect
import json
from dataclasses import dataclass, field
from pathlib import Path

__all__ = [
    "ApiDiff",
    "diff_snapshots",
    "load_baseline",
    "save_baseline",
    "signatures_compatible",
    "snapshot_package",
]


def _describe(module: object, name: str) -> dict[str, str]:
    obj = getattr(module, name)
    if inspect.isclass(obj):
        kind = "class"
    elif inspect.isfunction(obj) or inspect.isbuiltin(obj):
        kind = "function"
    else:
        kind = "constant"
    try:
        sig = str(inspect.signature(obj)) if kind != "constant" else ""
    except (TypeError, ValueError):
        sig = ""
    return {"kind": kind, "sig": sig}


def _iter_modules(root: Path) -> list[str]:
    mods = []
    pkg = root / "hugrgate"
    for path in sorted(pkg.rglob("*.py")):
        if "__pycache__" in path.parts:
            continue
        rel = ".".join(path.relative_to(root).with_suffix("").parts)
        mods.append(rel[: -len(".__init__")] if rel.endswith(".__init__")
                    else rel)
    return mods


def snapshot_package(root: str | Path | None = None) -> dict[str, dict[str, dict[str, str]]]:
    """Snapshot every ``hugrgate`` module's ``__all__`` contract."""
    if root is None:
        root = Path(__file__).resolve().parent.parent.parent
    root = Path(root)
    snapshot: dict[str, dict[str, dict[str, str]]] = {}
    for mod_name in _iter_modules(root):
        module = importlib.import_module(mod_name)
        names = list(getattr(module, "__all__", []))
        snapshot[mod_name] = {n: _describe(module, n) for n in sorted(names)}
    return snapshot


def save_baseline(path: str | Path,
                  snapshot: dict | None = None) -> Path:
    """Write the snapshot as canonical JSON; returns the path."""
    if snapshot is None:
        snapshot = snapshot_package()
    path = Path(path)
    path.write_text(json.dumps(snapshot, indent=2, sort_keys=True) + "\n",
                    encoding="utf-8")
    return path


def load_baseline(path: str | Path) -> dict:
    """Load a baseline snapshot; raises on corrupt files."""
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"cannot load API baseline {path}: {exc}") from exc
    if not isinstance(data, dict):
        raise ValueError(f"API baseline {path} is not an object")
    return data


def _params_of(sig: str) -> list[inspect.Parameter] | None:
    """Parse a signature string back into parameters (no eval).

    Returns None when the string is not a parseable signature —
    callers treat that as incompatible (fail closed).
    """
    try:
        tree = ast.parse(f"def _f{sig}: pass")
    except SyntaxError:
        return None
    node = tree.body[0]
    if not isinstance(node, ast.FunctionDef):
        return None
    args = node.args
    params: list[inspect.Parameter] = []
    pos = list(args.posonlyargs) + list(args.args)
    defaults = [None] * (len(pos) - len(args.defaults)) + list(args.defaults)
    for arg, default in zip(pos, defaults, strict=True):
        kind = (inspect.Parameter.POSITIONAL_ONLY
                if arg in args.posonlyargs
                else inspect.Parameter.POSITIONAL_OR_KEYWORD)
        params.append(inspect.Parameter(
            arg.arg, kind,
            default=object() if default is not None
            else inspect.Parameter.empty))
    if args.vararg is not None:
        params.append(inspect.Parameter(args.vararg.arg,
                                        inspect.Parameter.VAR_POSITIONAL))
    for arg, default in zip(args.kwonlyargs, args.kw_defaults, strict=True):
        params.append(inspect.Parameter(
            arg.arg, inspect.Parameter.KEYWORD_ONLY,
            default=object() if default is not None
            else inspect.Parameter.empty))
    if args.kwarg is not None:
        params.append(inspect.Parameter(args.kwarg.arg,
                                        inspect.Parameter.VAR_KEYWORD))
    return params


def signatures_compatible(old_sig: str, new_sig: str) -> bool:
    """Whether ``new_sig`` still accepts everything ``old_sig`` did.

    Every old parameter must survive with the same kind, and the new
    signature must not add required parameters. Unparseable
    signatures are incompatible (fail closed).
    """
    if old_sig == new_sig:
        return True
    old_params = _params_of(old_sig)
    new_params = _params_of(new_sig)
    if old_params is None or new_params is None:
        return False
    old_by_name = {p.name: p for p in old_params}
    new_by_name = {p.name: p for p in new_params}
    for pname, p in old_by_name.items():
        q = new_by_name.get(pname)
        if q is None or q.kind is not p.kind:
            return False
        if (p.default is not inspect.Parameter.empty
                and q.default is inspect.Parameter.empty):
            # Optional became required: old callers may omit it.
            return False
    required_kinds = (inspect.Parameter.POSITIONAL_ONLY,
                      inspect.Parameter.POSITIONAL_OR_KEYWORD,
                      inspect.Parameter.KEYWORD_ONLY)
    for pname, q in new_by_name.items():
        if (pname not in old_by_name
                and q.default is inspect.Parameter.empty
                and q.kind in required_kinds):
            return False
    return True


@dataclass
class ApiDiff:
    """Classified drift between baseline and current snapshots."""

    added_modules: list[str] = field(default_factory=list)
    removed_modules: list[str] = field(default_factory=list)
    added_names: list[tuple[str, str]] = field(default_factory=list)
    removed_names: list[tuple[str, str]] = field(default_factory=list)
    changed: list[tuple[str, str, str, str]] = field(default_factory=list)

    @property
    def breaking(self) -> bool:
        return bool(self.removed_modules or self.removed_names
                    or self.changed)

    @property
    def additive(self) -> bool:
        return bool(self.added_modules or self.added_names)

    def summary(self) -> str:
        parts = []
        if self.removed_modules:
            parts.append(f"removed modules: {self.removed_modules}")
        if self.removed_names:
            parts.append(f"removed names: {self.removed_names}")
        if self.changed:
            parts.append(
                "changed: " + ", ".join(f"{m}.{n}" for m, n, _, _ in self.changed))
        if self.added_modules:
            parts.append(f"added modules: {self.added_modules}")
        if self.added_names:
            parts.append(f"added names: {len(self.added_names)}")
        return "; ".join(parts) if parts else "no drift"


def diff_snapshots(baseline: dict, current: dict) -> ApiDiff:
    """Classify drift between two snapshots from :func:`snapshot_package`."""
    diff = ApiDiff()
    base_mods = set(baseline)
    cur_mods = set(current)
    diff.added_modules = sorted(cur_mods - base_mods)
    diff.removed_modules = sorted(base_mods - cur_mods)
    for mod in sorted(base_mods & cur_mods):
        base_names = baseline[mod]
        cur_names = current[mod]
        for name in sorted(set(cur_names) - set(base_names)):
            diff.added_names.append((mod, name))
        for name in sorted(set(base_names) - set(cur_names)):
            diff.removed_names.append((mod, name))
        for name in sorted(set(base_names) & set(cur_names)):
            old, new = base_names[name], cur_names[name]
            if old["kind"] != new["kind"]:
                diff.changed.append((mod, name, old["sig"], new["sig"]))
            elif old["kind"] != "constant" and not signatures_compatible(
                    old["sig"], new["sig"]):
                diff.changed.append((mod, name, old["sig"], new["sig"]))
    return diff
