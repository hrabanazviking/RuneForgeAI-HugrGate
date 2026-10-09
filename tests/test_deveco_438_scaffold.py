"""Slice 438 — project scaffolder.

The proof of a scaffolder is that the scaffolded project works:
these tests scaffold into a tmp dir and *run the generated test
suite* (plus byte-compile every generated Python file).
"""

from __future__ import annotations

import os
import py_compile
import subprocess
import sys
from pathlib import Path

import pytest

from hugrgate.cli import main
from hugrgate.errors import ScaffoldError
from hugrgate.scaffold import (
    SCAFFOLD_FILES,
    scaffold_project,
    validate_project_name,
)

REPO_ROOT = Path(__file__).resolve().parent.parent


def _scaffold_env(root: Path) -> dict[str, str]:
    """Subprocess env: the scaffolded project sees the repo's
    hugrgate (this worktree) and its own src layout."""
    env = dict(os.environ)
    env["PYTHONPATH"] = (str(root / "src") + os.pathsep
                         + str(REPO_ROOT))
    return env


def test_validate_project_name():
    assert validate_project_name("myproj") == "myproj"
    assert validate_project_name("a1_b2") == "a1_b2"
    for bad in ("MyProj", "my-proj", "1abc", "", "has space",
                "import", "class"):
        with pytest.raises(ScaffoldError):
            validate_project_name(bad)


def test_scaffold_creates_all_files(tmp_path):
    written = scaffold_project("demo", tmp_path)
    names = sorted(str(p.relative_to(tmp_path / "demo"))
                   for p in written)
    expected = sorted(f.format(pkg="demo") for f in SCAFFOLD_FILES)
    assert names == expected


def test_scaffolded_python_files_compile(tmp_path):
    scaffold_project("demo", tmp_path)
    for path in (tmp_path / "demo").rglob("*.py"):
        py_compile.compile(str(path), doraise=True)


def test_scaffolded_suite_passes(tmp_path):
    """Run the generated project's own pytest suite for real."""
    scaffold_project("demo", tmp_path)
    root = tmp_path / "demo"
    proc = subprocess.run(
        [sys.executable, "-m", "pytest", "-q", "tests/"],
        cwd=root,
        capture_output=True,
        text=True,
        timeout=120,
        env=_scaffold_env(root),
    )
    assert proc.returncode == 0, (
        f"scaffolded suite failed:\n{proc.stdout}\n{proc.stderr}")
    assert "1 passed" in proc.stdout


def test_scaffolded_main_runs(tmp_path):
    scaffold_project("demo", tmp_path)
    root = tmp_path / "demo"
    proc = subprocess.run(
        [sys.executable, "-m", "demo.main"],
        cwd=root,
        capture_output=True,
        text=True,
        timeout=60,
        env=_scaffold_env(root),
    )
    assert proc.returncode == 0, proc.stderr
    assert "decision:" in proc.stdout


def test_scaffold_refuses_nonempty_dir(tmp_path):
    target = tmp_path / "demo"
    target.mkdir()
    (target / "existing.txt").write_text("x")
    with pytest.raises(ScaffoldError):
        scaffold_project("demo", tmp_path)
    scaffold_project("demo", tmp_path, force=True)  # must not raise


def test_scaffold_empty_existing_dir_ok(tmp_path):
    (tmp_path / "demo").mkdir()
    scaffold_project("demo", tmp_path)  # must not raise


def test_cli_new(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    assert main(["new", "myapp"]) == 0
    assert (tmp_path / "myapp" / "pyproject.toml").exists()
    out = capsys.readouterr().out
    assert "scaffolded project 'myapp'" in out
    assert "next:" in out


def test_cli_new_bad_name_is_exit_2(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    assert main(["new", "Bad-Name"]) == 2
    assert "invalid project name" in capsys.readouterr().err


def test_cli_new_into_parent_dir(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    assert main(["new", "sub", "--dir", "projects"]) == 0
    assert (tmp_path / "projects" / "sub" / "README.md").exists()
