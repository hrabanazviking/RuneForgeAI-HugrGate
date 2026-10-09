"""Slice 421 — secret-handling audit.

The auditor must fire on every planted violation class, stay
quiet on clean code, and — as a standing gate — find zero
high-severity issues in the real ``hugrgate/`` tree.
"""

from __future__ import annotations

from pathlib import Path

from hugrgate.security.secret_audit import (
    audit_file,
    audit_tree,
    run_secret_audit,
)

REPO_ROOT = Path(__file__).resolve().parent.parent


def _write(tmp_path: Path, name: str, code: str) -> Path:
    path = tmp_path / name
    path.write_text(code)
    return path


def test_hardcoded_secret_fires(tmp_path):
    path = _write(tmp_path, "m.py", 'api_key = "sk-live-abc123"\n')
    findings = audit_file(path)
    assert any(f.rule == "hardcoded_secret" and f.severity == "high"
               for f in findings)


def test_event_code_constant_does_not_fire(tmp_path):
    path = _write(tmp_path, "m.py",
                  'EVENT_SECRET_DETECTED = "secret_detected"\n')
    assert audit_file(path) == []


def test_opaque_upper_constant_still_fires(tmp_path):
    path = _write(tmp_path, "m.py",
                  'API_KEY = "sk-live-9f8e7d6c5b4a39281"\n')
    findings = audit_file(path)
    assert any(f.rule == "hardcoded_secret" for f in findings)


def test_secret_in_log_fires(tmp_path):
    path = _write(tmp_path, "m.py",
                  "import logging\n"
                  'api_key = get_key()\n'
                  'logging.info("using key %s", api_key)\n')
    findings = audit_file(path)
    assert any(f.rule == "secret_in_log" for f in findings)


def test_tls_disabled_fires(tmp_path):
    path = _write(tmp_path, "m.py",
                  "import requests\n"
                  'requests.get("https://x", verify=False)\n')
    findings = audit_file(path)
    assert any(f.rule == "tls_disabled" and f.severity == "high"
               for f in findings)


def test_secret_in_url_fires(tmp_path):
    path = _write(tmp_path, "m.py",
                  'url = "https://svc.example.com"\n'
                  'requests.get(url, params={"api_key": "abc"})\n'
                  'other = "https://user:hunter2@svc.example.com/x"\n')
    findings = audit_file(path)
    assert any(f.rule == "secret_in_url" for f in findings)


def test_secret_in_exception_fires(tmp_path):
    path = _write(tmp_path, "m.py",
                  'password = lookup()\n'
                  'raise RuntimeError(f"bad password {password}")\n')
    findings = audit_file(path)
    assert any(f.rule == "secret_in_exception" for f in findings)


def test_exception_class_name_does_not_fire(tmp_path):
    path = _write(tmp_path, "m.py",
                  "from hugrgate.errors import SecretDetected\n"
                  'raise SecretDetected("2 secret-shaped values found")\n')
    assert audit_file(path) == []


def test_weak_randomness_fires(tmp_path):
    path = _write(tmp_path, "m.py",
                  "import random\n"
                  "token = random.choice('abcdef0123456789')\n")
    findings = audit_file(path)
    assert any(f.rule == "weak_secret_gen" for f in findings)


def test_env_default_secret_fires(tmp_path):
    path = _write(tmp_path, "m.py",
                  "import os\n"
                  'pw = os.environ.get("APP_PASSWORD", "changeme")\n')
    findings = audit_file(path)
    assert any(f.rule == "env_default_secret" for f in findings)


def test_clean_file_is_quiet(tmp_path):
    path = _write(tmp_path, "m.py",
                  "import logging, secrets\n"
                  "log = logging.getLogger(__name__)\n"
                  "token = secrets.token_hex(16)\n"
                  'log.info("issued token id %s", token_id)\n'
                  'key = derive_key(password_from_vault())\n')
    assert audit_file(path) == []


def test_test_fixtures_downgraded_to_info(tmp_path):
    test_dir = tmp_path / "tests"
    test_dir.mkdir()
    path = _write(test_dir, "t.py", 'api_key = "sk-test-123"\n')
    findings = audit_file(path)
    assert findings and all(f.severity == "info" for f in findings)


def test_standing_gate_real_tree_has_no_high_findings():
    report = run_secret_audit(REPO_ROOT / "hugrgate")
    assert report["high"] == [], [
        (f.path, f.line, f.rule, f.snippet)
        for f in report["high"]]
    assert report["by_severity"].get("medium", 0) == 0


def test_audit_tree_skips_venv(tmp_path):
    venv_file = tmp_path / "venv" / "lib" / "evil.py"
    venv_file.parent.mkdir(parents=True)
    venv_file.write_text('password = "hunter2"\n')
    assert audit_tree(tmp_path) == []
