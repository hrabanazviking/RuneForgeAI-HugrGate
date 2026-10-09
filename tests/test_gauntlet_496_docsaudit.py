"""Slice 496 — tests for the documentation executable audit tool.

Loads tools/docs_exec_audit.py by path (it is a script, not a
package module) and covers extraction, the # noexec opt-out,
and pass/fail/timeout/syntax-error outcomes.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
TOOL = REPO / "tools" / "docs_exec_audit.py"


def _load():
    spec = importlib.util.spec_from_file_location("docs_exec_audit", TOOL)
    module = importlib.util.module_from_spec(spec)
    sys.modules["docs_exec_audit"] = module
    spec.loader.exec_module(module)
    return module


audit = _load()


def test_extract_blocks_finds_python_only(tmp_path):
    doc = tmp_path / "d.md"
    doc.write_text(
        "# Title\n\n```python\nprint(1)\n```\n\n```bash\necho hi\n```\n\n"
        "```python\nprint(2)\n```\n")
    blocks = audit.extract_blocks(doc)
    assert len(blocks) == 2
    assert "print(1)" in blocks[0]
    assert "print(2)" in blocks[1]


def test_noexec_detection():
    assert audit.noexec_reason("# noexec\nprint(1)") == "opted out"
    assert audit.noexec_reason("# noexec: needs a gate\nprint(1)") == \
        "needs a gate"
    assert audit.noexec_reason("# NOEXEC\nprint(1)") == "opted out"
    assert audit.noexec_reason("print(1)") is None
    assert audit.noexec_reason("") == "empty block"


def test_run_block_pass(tmp_path):
    status, detail = audit.run_block("print('hello')", 30.0, tmp_path)
    assert status == "PASS"
    assert detail == ""


def test_run_block_fail(tmp_path):
    status, detail = audit.run_block("raise ValueError('boom')", 30.0,
                                     tmp_path)
    assert status == "FAIL"
    assert "boom" in detail


def test_run_block_syntax_error(tmp_path):
    status, detail = audit.run_block("def broken(:", 30.0, tmp_path)
    assert status == "SYNTAX-ERROR"
    assert detail != ""


def test_run_block_timeout(tmp_path):
    status, _detail = audit.run_block("import time; time.sleep(30)", 0.5,
                                      tmp_path)
    assert status == "TIMEOUT"


def test_audit_files_reports_skip(tmp_path):
    doc = tmp_path / "d.md"
    doc.write_text("```python\n# noexec: fragment\nundefined_name\n```\n")
    report = audit.audit_files([doc], 30.0, tmp_path)
    assert report.passed
    assert report.results[0].status == "SKIP"


def test_audit_files_reports_failure(tmp_path):
    doc = tmp_path / "d.md"
    doc.write_text("```python\nraise RuntimeError('x')\n```\n")
    report = audit.audit_files([doc], 30.0, tmp_path)
    assert not report.passed
    assert len(report.failed) == 1


def test_gauntlet_docs_audit_clean():
    """The real gauntlet: the audited docs must be green."""
    files = [REPO / "docs" / name for name in (
        "quickstart.md", "api.md", "ladder.md", "calibration.md",
        "campaign-xiv/observability.md", "evlab/evaluation-lab.md")]
    report = audit.audit_files(files, 60.0, REPO)
    assert report.passed, report.summary()
    assert len(report.results) == 7
