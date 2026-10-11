"""Slice 442 — the example gallery stays executable.

Every script in examples/ is run in a subprocess with the repo
venv; a non-zero exit fails the gallery. Marked slow because the
set takes ~15 seconds.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.slow

EXAMPLES = sorted(
    (Path(__file__).resolve().parent.parent / "examples").glob("*.py"))


def test_gallery_index_exists():
    gallery = (Path(__file__).resolve().parent.parent
               / "docs" / "dev-gallery.md")
    assert gallery.exists()
    text = gallery.read_text(encoding="utf-8")
    for script in EXAMPLES:
        assert script.stem in text, script.stem


@pytest.mark.parametrize("script", [p.name for p in EXAMPLES])
def test_example_runs(script, tmp_path):
    path = (Path(__file__).resolve().parent.parent
            / "examples" / script)
    # Route demo scratch output (e.g. calibrated_triage.py's
    # .hugrgate-demo/ tree) to a throwaway dir so the gallery never
    # dirties the checked-in tree (slice: tree-hygiene-demo-profile).
    env = dict(os.environ)
    env["HUGRGATE_DEMO_DIR"] = str(tmp_path / "hugrgate-demo")
    proc = subprocess.run(
        [sys.executable, str(path)],
        capture_output=True, text=True, timeout=120,
        cwd=str(path.parent.parent), env=env)
    assert proc.returncode == 0, (
        f"{script} exited {proc.returncode}:\n{proc.stderr[-2000:]}")
