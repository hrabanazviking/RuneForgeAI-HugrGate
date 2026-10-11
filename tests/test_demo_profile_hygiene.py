"""Slice 2 (tree-hygiene-demo-profile) — demo artifact tree hygiene.

Writer chain (found by digging, 2026-10-10):
  tests/test_deveco_442_gallery.py::test_example_runs[calibrated_triage.py]
  runs examples/calibrated_triage.py as a subprocess with cwd=<repo root>.
  The example's main() does ``shutil.rmtree(".hugrgate-demo")`` and saves a
  fresh CalibrationProfile whose ``created_at`` is ``datetime.now(utc)``,
  rewriting the checked-in
  .hugrgate-demo/profiles/triage-platt/1.0.0.json on every gallery run.

Fix: the example honors HUGRGATE_DEMO_DIR (default: the historical
".hugrgate-demo" so manual runs are unchanged); the gallery test points
it at a throwaway dir. These tests lock the hygiene in:

  1. Running the demo with HUGRGATE_DEMO_DIR set to a tmp dir leaves
     ``git status --short`` clean for the checked-in profile path.
  2. The profile artifact is otherwise fully deterministic (seeded RNG,
     sorted JSON keys): two runs differ only in ``created_at``.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
PROFILE = (REPO / ".hugrgate-demo" / "profiles" / "triage-platt"
           / "1.0.0.json")


def _run_demo(demo_dir: Path) -> subprocess.CompletedProcess[str]:
    env = dict(os.environ)
    env["HUGRGATE_DEMO_DIR"] = str(demo_dir)
    return subprocess.run(
        [sys.executable, str(REPO / "examples" / "calibrated_triage.py")],
        capture_output=True, text=True, timeout=180,
        cwd=str(REPO), env=env)


def _git_status_short(path: Path) -> str:
    proc = subprocess.run(
        ["git", "status", "--short", "--", str(path)],
        capture_output=True, text=True, cwd=str(REPO))
    return proc.stdout


def test_demo_run_leaves_checked_in_profile_untouched(tmp_path):
    """The demo must not dirty the checked-in profile when redirected."""
    before = PROFILE.read_text(encoding="utf-8")
    result = _run_demo(tmp_path / "demo-a")
    assert result.returncode == 0, result.stderr[-2000:]
    # Artifact landed in the tmp dir, not the repo tree.
    tmp_profile = tmp_path / "demo-a" / "profiles" / "triage-platt" / "1.0.0.json"
    assert tmp_profile.is_file(), result.stdout[-2000:]
    # Checked-in file byte-identical and git-clean.
    assert PROFILE.read_text(encoding="utf-8") == before
    assert _git_status_short(PROFILE) == "", (
        "demo run dirtied the checked-in profile: "
        + _git_status_short(PROFILE))


def test_demo_profile_output_is_deterministic(tmp_path):
    """Two demo runs produce identical profiles apart from created_at."""
    r1 = _run_demo(tmp_path / "demo-b")
    assert r1.returncode == 0, r1.stderr[-2000:]
    r2 = _run_demo(tmp_path / "demo-c")
    assert r2.returncode == 0, r2.stderr[-2000:]
    p1 = json.loads((tmp_path / "demo-b" / "profiles" / "triage-platt"
                     / "1.0.0.json").read_text(encoding="utf-8"))
    p2 = json.loads((tmp_path / "demo-c" / "profiles" / "triage-platt"
                     / "1.0.0.json").read_text(encoding="utf-8"))
    c1, c2 = p1.pop("created_at"), p2.pop("created_at")
    assert isinstance(c1, str) and isinstance(c2, str)
    assert p1 == p2, "demo profile is not deterministic across runs"
