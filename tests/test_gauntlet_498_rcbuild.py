"""Slice 498 — tests for the release-candidate build verifier.

Loads tools/rc_build.py by path and unit-tests the verification
logic against crafted wheels: metadata/entry-point checks pass on
a good wheel and flag each failure mode. (The end-to-end build +
smoke run was executed manually during the slice; see the slice
doc for the evidence.)
"""

from __future__ import annotations

import importlib.util
import sys
import zipfile
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
TOOL = REPO / "tools" / "rc_build.py"


def _load():
    spec = importlib.util.spec_from_file_location("rc_build", TOOL)
    module = importlib.util.module_from_spec(spec)
    sys.modules["rc_build"] = module
    spec.loader.exec_module(module)
    return module


rc = _load()

GOOD_META = """Metadata-Version: 2.1
Name: hugrgate
Version: 0.1.0
Requires-Python: >=3.10
Requires-Dist: pyyaml>=6.0
"""

GOOD_EP = """[console_scripts]
hugrgate = hugrgate.cli:main
hugrgate-server = hugrgate.daemon:main
"""


def _wheel(path: Path, name: str, meta: str | None,
           ep: str | None) -> Path:
    wheel = path / name
    with zipfile.ZipFile(wheel, "w") as zf:
        zf.writestr("hugrgate/__init__.py", "")
        if meta is not None:
            zf.writestr("hugrgate-0.1.0.dist-info/METADATA", meta)
        if ep is not None:
            zf.writestr("hugrgate-0.1.0.dist-info/entry_points.txt", ep)
    return wheel


def test_verify_good_wheel(tmp_path):
    wheel = _wheel(tmp_path, "hugrgate-0.1.0-py3-none-any.whl",
                   GOOD_META, GOOD_EP)
    assert rc.verify_wheel_metadata(wheel) == []


def test_verify_missing_metadata(tmp_path):
    wheel = _wheel(tmp_path, "hugrgate-0.1.0-py3-none-any.whl", None, GOOD_EP)
    problems = rc.verify_wheel_metadata(wheel)
    assert any("METADATA" in p for p in problems)


def test_verify_missing_entry_points(tmp_path):
    wheel = _wheel(tmp_path, "hugrgate-0.1.0-py3-none-any.whl",
                   GOOD_META, None)
    problems = rc.verify_wheel_metadata(wheel)
    assert any("entry_points" in p for p in problems)


def test_verify_missing_script(tmp_path):
    ep = "[console_scripts]\nhugrgate = hugrgate.cli:main\n"
    wheel = _wheel(tmp_path, "hugrgate-0.1.0-py3-none-any.whl",
                   GOOD_META, ep)
    problems = rc.verify_wheel_metadata(wheel)
    assert any("hugrgate-server" in p for p in problems)


def test_verify_missing_runtime_dep(tmp_path):
    meta = GOOD_META.replace("Requires-Dist: pyyaml>=6.0\n", "")
    wheel = _wheel(tmp_path, "hugrgate-0.1.0-py3-none-any.whl",
                   meta, GOOD_EP)
    problems = rc.verify_wheel_metadata(wheel)
    assert any("pyyaml" in p for p in problems)


def test_verify_bad_wheel_tag(tmp_path):
    wheel = _wheel(tmp_path, "hugrgate-0.1.0-py2.py3-none-any.whl",
                   GOOD_META, GOOD_EP)
    problems = rc.verify_wheel_metadata(wheel)
    assert any("tag" in p for p in problems)


def test_find_artifacts(tmp_path):
    (tmp_path / "hugrgate-0.1.0-py3-none-any.whl").touch()
    (tmp_path / "hugrgate-0.1.0.tar.gz").touch()
    wheels, sdists = rc.find_artifacts(tmp_path)
    assert len(wheels) == 1 and len(sdists) == 1


def test_find_artifacts_empty(tmp_path):
    wheels, sdists = rc.find_artifacts(tmp_path)
    assert wheels == [] and sdists == []


def test_report_exit_codes(capsys):
    assert rc._report([("a", True, ""), ("b", True, "")]) == 0
    assert rc._report([("a", True, ""), ("b", False, "boom")]) == 1
    out = capsys.readouterr().out
    assert "1/2 checks passed" in out
