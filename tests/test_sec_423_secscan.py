"""Slice 423 — static security analysis gate.

Rule tests drive the real ``tools/secscan.py`` CLI on fixture
files; the standing gate asserts zero high-severity findings over
the real ``hugrgate/`` tree.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SECSCAN = REPO_ROOT / "tools" / "secscan.py"


def _scan(tmp_path: Path, code: str) -> list[dict]:
    path = tmp_path / "snippet.py"
    path.write_text(code)
    proc = subprocess.run(
        [sys.executable, str(SECSCAN), str(path), "--format", "json"],
        capture_output=True, text=True, timeout=120)
    assert proc.returncode in (0, 1), proc.stderr
    return json.loads(proc.stdout)


def test_eval_exec_flagged(tmp_path):
    findings = _scan(tmp_path, "eval(user_input)\nexec('x = 1')\n")
    assert sum(1 for f in findings
               if f["rule"] == "dynamic_code_exec") == 2
    assert all(f["severity"] == "high" for f in findings
               if f["rule"] == "dynamic_code_exec")


def test_bare_compile_flagged_but_re_compile_not(tmp_path):
    findings = _scan(tmp_path, "compile('1+1', '<s>', 'eval')\n")
    assert any(f["rule"] == "dynamic_code_exec" for f in findings)
    findings = _scan(tmp_path, "import re\nre.compile('a+')\n")
    assert not any(f["rule"] == "dynamic_code_exec" for f in findings)


def test_pickle_loads_flagged(tmp_path):
    findings = _scan(tmp_path, "import pickle\npickle.loads(blob)\n")
    assert any(f["rule"] == "unsafe_deserialization"
               and f["severity"] == "high" for f in findings)


def test_yaml_load_without_loader_flagged(tmp_path):
    findings = _scan(tmp_path, "import yaml\nyaml.load(text)\n")
    assert any(f["rule"] == "unsafe_deserialization" for f in findings)
    findings = _scan(tmp_path,
                     "import yaml\nyaml.load(text, Loader=yaml.SafeLoader)\n")
    assert not any(f["rule"] == "unsafe_deserialization"
                   for f in findings)


def test_shell_true_and_os_system_flagged(tmp_path):
    findings = _scan(tmp_path,
                     "import subprocess, os\n"
                     "subprocess.run(cmd, shell=True)\n"
                     "os.system('ls')\n")
    assert sum(1 for f in findings
               if f["rule"] == "shell_execution") == 2


def test_hostile_fixture_marker_downgrades(tmp_path):
    findings = _scan(tmp_path,
                     "# secscan: hostile-fixture\nimport os\nos.system('x')\n")
    assert findings and all(f["severity"] == "info" for f in findings)


def test_weak_hash_is_medium_not_high(tmp_path):
    findings = _scan(tmp_path,
                     "import hashlib\nhashlib.md5(b'x').hexdigest()\n")
    assert any(f["rule"] == "weak_hash" and f["severity"] == "medium"
               for f in findings)


def test_standing_gate_no_high_findings_in_tree():
    proc = subprocess.run(
        [sys.executable, str(SECSCAN), str(REPO_ROOT / "hugrgate"),
         "--format", "json"],
        capture_output=True, text=True, timeout=300)
    assert proc.returncode == 0, (
        f"secscan failed on the real tree:\n{proc.stdout}\n{proc.stderr}")
    findings = json.loads(proc.stdout)
    highs = [f for f in findings if f["severity"] == "high"]
    assert highs == [], highs


def test_secscan_clean_on_tools():
    proc = subprocess.run(
        [sys.executable, str(SECSCAN), str(REPO_ROOT / "tools")],
        capture_output=True, text=True, timeout=120)
    assert proc.returncode == 0, proc.stdout + proc.stderr
