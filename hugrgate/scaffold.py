"""Project scaffolder. Slice 438.

``hugrgate new NAME`` creates a complete, working HugrGate project:

    myproj/
        pyproject.toml        # hugrgate dependency, pytest config
        README.md             # run instructions
        .gitignore
        spec.yaml             # starter DecisionSpec
        policy.yaml           # starter DecisionPolicy
        state.example.yaml    # example decision state
        src/myproj/__init__.py
        src/myproj/main.py    # decide() via the SDK v2 in-process gate
        tests/test_smoke.py   # a smoke test that actually passes

The scaffolded project's own test suite is executed by this
slice's tests to prove the scaffold works out of the box.
"""

from __future__ import annotations

import keyword
import re
from pathlib import Path

from hugrgate.errors import ScaffoldError

__all__ = ["SCAFFOLD_FILES", "scaffold_project", "validate_project_name"]

#: Files every scaffolded project contains (relative to the root).
SCAFFOLD_FILES = (
    "pyproject.toml",
    "README.md",
    ".gitignore",
    "spec.yaml",
    "policy.yaml",
    "state.example.yaml",
    "src/{pkg}/__init__.py",
    "src/{pkg}/main.py",
    "tests/__init__.py",
    "tests/test_smoke.py",
)

_NAME_RE = re.compile(r"^[a-z][a-z0-9_]*$")


def validate_project_name(name: str) -> str:
    """Validate a project name; return the Python package name.

    Raises :class:`ScaffoldError` for anything that would not make
    a clean ``src/<name>`` package.
    """
    if not _NAME_RE.match(name):
        raise ScaffoldError(
            f"invalid project name {name!r}: use lowercase letters, "
            "digits, and underscores, starting with a letter")
    if keyword.iskeyword(name):
        raise ScaffoldError(
            f"invalid project name {name!r}: it is a Python keyword")
    return name


def _pyproject(name: str) -> str:
    return f"""\
[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[project]
name = "{name}"
version = "0.1.0"
description = "HugrGate-powered decision service"
requires-python = ">=3.10"
dependencies = ["hugrgate>=0.1.0", "pyyaml>=6.0"]

[project.optional-dependencies]
server = ["hugrgate[server]"]

[tool.pytest.ini_options]
testpaths = ["tests"]

[tool.hatch.build.targets.wheel]
packages = ["src/{name}"]
"""


def _readme(name: str) -> str:
    return f"""\
# {name}

A HugrGate-powered decision project, scaffolded with `hugrgate new`.

## Run one decision

```bash
hugrgate decide --spec spec.yaml --state state.example.yaml
```

## Run the project entry point

```bash
python -m {name}.main
```

## Run the tests

```bash
pytest
```

## Serve it

```bash
hugrgate serve --config hugrgate.yaml   # after `hugrgate gen daemon`
```
"""


def _main_py() -> str:
    return '''\
"""Project entry point — one decision through the HugrGate SDK v2."""

from hugrgate.sdk import HugrGateSDK
from hugrgate.server import build_gate
from hugrgate.spec import DecisionSpec


def decide(state: dict) -> str:
    spec = DecisionSpec.from_dict(
        {"type": "categorical", "options": ["approve", "escalate"]})
    with HugrGateSDK(gate=build_gate()) as sdk:
        return str(sdk.decide_value(state, spec))


def main() -> None:
    print("decision:", decide({"signal": 0.7}))


if __name__ == "__main__":
    main()
'''


def _test_smoke(name: str) -> str:
    return f'''\
"""Scaffold smoke test — proves the project works out of the box."""

from {name}.main import decide


def test_decide_returns_a_valid_option():
    assert decide({{"signal": 0.7}}) in ("approve", "escalate")
'''


def scaffold_project(name: str, directory: str | Path = ".",
                     force: bool = False) -> list[Path]:
    """Create a new HugrGate project.

    ``directory/NAME`` is created and populated. Raises
    :class:`ScaffoldError` for bad names, or when the target exists
    and is non-empty (unless ``force``). Returns the written paths.
    """
    pkg = validate_project_name(name)
    root = Path(directory) / name
    if root.exists() and any(root.iterdir()) and not force:
        raise ScaffoldError(
            f"refusing to scaffold into non-empty directory: {root} "
            "(pass --force to overwrite)")
    root.mkdir(parents=True, exist_ok=True)

    from hugrgate.configgen import (
        generate_policy,
        generate_spec,
    )
    files: dict[str, str] = {
        "pyproject.toml": _pyproject(pkg),
        "README.md": _readme(name),
        ".gitignore": "__pycache__/\n*.pyc\n.venv/\n.pytest_cache/\n",
        "spec.yaml": generate_spec(
            "categorical", options=["approve", "escalate"]),
        "policy.yaml": generate_policy(),
        "state.example.yaml": "signal: 0.7\n",
        f"src/{pkg}/__init__.py":
            f'"""The {name} package."""\n__all__ = ["main"]\n',
        f"src/{pkg}/main.py": _main_py(),
        "tests/test_smoke.py": _test_smoke(pkg),
        "tests/__init__.py": "",
    }
    written = []
    for rel, content in files.items():
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        written.append(path)
    return written
