"""Slice 432 — C ABI design verification.

Parses ``sdks/c/include/hugrgate.h`` and enforces the ABI stability
rules stated in the header, plus a real ``gcc -fsyntax-only``
compile check in both C99 and C++ modes.
"""

from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path

import pytest

HEADER = Path(__file__).resolve().parent.parent / "sdks" / "c" / \
    "include" / "hugrgate.h"


def _src() -> str:
    return HEADER.read_text(encoding="utf-8")


def test_header_guard_and_extern_c():
    src = _src()
    assert "#ifndef HUGRGATE_H" in src
    assert "#define HUGRGATE_H" in src
    assert '#endif /* HUGRGATE_H */' in src
    assert 'extern "C"' in src
    assert "#ifdef __cplusplus" in src


def test_version_macros():
    src = _src()
    assert "#define HUGRGATE_ABI_VERSION_MAJOR 1" in src
    assert "#define HUGRGATE_ABI_VERSION_MINOR 0" in src
    assert '#define HUGRGATE_PROTOCOL_VERSION "1.0"' in src
    assert '#define HUGRGATE_SDK_VERSION "2.0"' in src


def test_status_codes_are_frozen_and_append_only():
    src = _src()
    expected = [
        ("HG_OK", "0"), ("HG_ERR_INVALID_ARG", "1"),
        ("HG_ERR_NOMEM", "2"), ("HG_ERR_TRANSPORT", "3"),
        ("HG_ERR_TIMEOUT", "4"), ("HG_ERR_PROTOCOL", "5"),
        ("HG_ERR_SPEC", "6"), ("HG_ERR_POLICY", "7"),
        ("HG_ERR_BACKEND", "8"), ("HG_ERR_UNAVAILABLE", "9"),
        ("HG_ERR_ABSTAINED", "10"), ("HG_ERR_BAD_RESPONSE", "11"),
    ]
    for name, value in expected:
        assert re.search(rf"{name} = {value}\b", src), name
    assert "HG_STATUS_COUNT" in src  # sentinel for append-only growth


def test_client_handle_is_opaque():
    src = _src()
    assert "typedef struct hg_client hg_client_t;" in src
    # no definition of struct hg_client may appear in the header
    assert not re.search(r"struct hg_client\s*\{", src)


def test_error_and_decision_structs():
    src = _src()
    assert re.search(r"typedef struct hg_error \{", src)
    assert re.search(r"typedef struct hg_decision \{", src)
    for field in ("code;", "message;", "recoverable;", "service_code;",
                  "value_json;", "probability;", "distribution_json;",
                  "backend;", "model;", "metadata_json;"):
        assert field in src, field
    # no bitfields in the ABI
    assert not re.search(r":\s*\d+\s*;", src)


def test_all_functions_use_hg_prefix_and_c_linkage_types():
    src = _src()
    decls = re.findall(r"^\s*[\w][\w\s\*]*?\b(hg_\w+)\s*\(", src,
                       flags=re.MULTILINE)
    assert decls, "no hg_ functions found"
    for name in ("hg_client_new", "hg_client_free", "hg_client_decide",
                 "hg_decision_free", "hg_client_protocol",
                 "hg_status_message", "hg_status_recoverable",
                 "hg_error_free", "hg_free_string"):
        assert name in decls, name
    # every fallible function reports via hg_error_t **
    for name in ("hg_client_new", "hg_client_decide",
                 "hg_client_protocol"):
        decl = re.search(rf"^\s*[\w][\w\s\*]*?\b{name}\s*\([^;]*\);",
                         src, flags=re.MULTILINE | re.DOTALL)
        assert decl and "hg_error_t **" in decl.group(0), name


def test_no_cpp_only_constructs_in_abi():
    src = _src()
    code = re.sub(r"/\*.*?\*/", "", src, flags=re.DOTALL)
    code = re.sub(r"//.*", "", code)
    assert "bool" not in code.split()
    assert "nullptr" not in code


@pytest.mark.skipif(shutil.which("gcc") is None,
                    reason="gcc not installed")
@pytest.mark.parametrize("std,lang", [("c99", "c"), ("c++11", "c++")])
def test_header_compiles_clean(tmp_path, std, lang):
    tu = tmp_path / "tu.c"
    tu.write_text('#include <hugrgate.h>\nint main(void){return 0;}\n')
    proc = subprocess.run(
        ["gcc", f"-std={std}", f"-x{lang}", "-fsyntax-only",
         "-Wall", "-Wextra", "-Werror",
         f"-I{HEADER.parent}", str(tu)],
        capture_output=True, text=True, timeout=60)
    assert proc.returncode == 0, proc.stderr
