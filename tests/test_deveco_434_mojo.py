"""Slice 434 — Mojo integration design verification.

The Mojo toolchain is not installed here, so the binding cannot be
compiled. What *can* be verified with teeth:

- every ``external_call["hg_..."]`` symbol in the Mojo file exists
  in the C header it binds to,
- the LP64 struct-field offsets hard-coded in the Mojo file match
  offsets computed from the header's own field declarations
  (catches layout drift between the two files),
- the status-code aliases mirror the frozen header values.
"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
HEADER = ROOT / "sdks" / "c" / "include" / "hugrgate.h"
MOJO = ROOT / "sdks" / "mojo" / "hugrgate_mojo.mojo"


def _header() -> str:
    return HEADER.read_text(encoding="utf-8")


def _mojo() -> str:
    return MOJO.read_text(encoding="utf-8")


def test_every_ffi_symbol_exists_in_header():
    header, mojo = _header(), _mojo()
    symbols = set(re.findall(r'external_call\["(hg_\w+)"', mojo))
    assert symbols, "no FFI symbols found in the Mojo file"
    for sym in sorted(symbols):
        assert re.search(rf"\b{sym}\s*\(", header), \
            f"FFI symbol {sym} has no declaration in hugrgate.h"


def test_all_abi_functions_are_bound():
    mojo = _mojo()
    for sym in ("hg_client_new", "hg_client_free", "hg_client_decide",
                "hg_decision_free", "hg_client_protocol",
                "hg_status_message", "hg_status_recoverable",
                "hg_error_free", "hg_free_string"):
        assert f'external_call["{sym}"' in mojo, sym


def _lp64_offsets(fields: list[tuple[str, str]]) -> dict[str, int]:
    """Compute LP64 field offsets.

    ``fields``: (c_type, name). int/enum -> 4/align 4;
    pointer/double -> 8/align 8.
    """
    offsets: dict[str, int] = {}
    cursor = 0
    for ctype, name in fields:
        size, align = (8, 8) if ("*" in ctype or "double" in ctype) \
            else (4, 4)
        if cursor % align:
            cursor += align - cursor % align
        offsets[name] = cursor
        cursor += size
    return offsets


def _struct_fields(header: str, tag: str) -> list[tuple[str, str]]:
    m = re.search(rf"typedef struct {tag} \{{(.*?)\}}",
                  header, flags=re.DOTALL)
    assert m, f"struct {tag} not found"
    # strip comments before splitting on semicolons
    body = re.sub(r"/\*.*?\*/", "", m.group(1), flags=re.DOTALL)
    fields = []
    for chunk in body.split(";"):
        chunk = chunk.strip()
        if not chunk:
            continue
        parts = chunk.split()
        name = parts[-1].lstrip("*")
        stars = len(parts[-1]) - len(name)
        ctype = " ".join(parts[:-1]) + " *" * stars
        fields.append((ctype.strip(), name))
    return fields


def test_mojo_struct_offsets_match_header_layout():
    header, mojo = _header(), _mojo()
    err_fields = _struct_fields(header, "hg_error")
    dec_fields = _struct_fields(header, "hg_decision")
    err_off = _lp64_offsets(err_fields)
    dec_off = _lp64_offsets(dec_fields)

    def mojo_alias(prefix: str, field: str) -> int:
        abbrev = {
            "code": "CODE", "message": "MSG",
            "recoverable": "RECOV", "service_code": "SVC",
            "value_json": "VALUE", "probability": "PROB",
            "distribution_json": "DIST", "uncertainty": "UNCERT",
            "accepted": "ACCEPT", "backend": "BACKEND",
            "model": "MODEL", "latency_ms": "LAT",
            "calibration_profile": "CALIB",
            "fallback_used": "FALLBACK", "metadata_json": "META",
        }[field]
        m = re.search(rf"alias (_{prefix}{abbrev}_OFF): Int = (\d+)",
                      mojo)
        assert m, f"missing Mojo offset alias for {field}"
        return int(m.group(2))

    for field in ("code", "message", "recoverable", "service_code"):
        assert mojo_alias("ERR_", field) == err_off[field], field
    for field in ("value_json", "probability", "distribution_json",
                  "uncertainty", "accepted", "backend", "model",
                  "latency_ms", "calibration_profile", "fallback_used",
                  "metadata_json"):
        assert mojo_alias("DEC_", field) == dec_off[field], field


def test_status_aliases_mirror_header():
    header, mojo = _header(), _mojo()
    for name, value in re.findall(r"(HG_\w+)\s*=\s*(\d+)", header):
        if name == "HG_STATUS_COUNT":
            continue
        m = re.search(rf"alias {name}: Int32 = (\d+)", mojo)
        assert m, f"missing Mojo alias for {name}"
        assert m.group(1) == value, f"{name}: mojo={m.group(1)} header={value}"


def test_protocol_version_alias():
    assert 'alias HG_PROTOCOL_VERSION = "1.0"' in _mojo()


def test_ownership_wrappers_present():
    mojo = _mojo()
    assert "struct Decision(Movable)" in mojo
    assert "struct Client(Movable)" in mojo
    assert "fn __del__(owned self)" in mojo
    assert "hg_decision_free" in mojo and "hg_client_free" in mojo
    # errors become Mojo Errors, never silent
    assert "_raise_for_status" in mojo
    assert "raise Error(" in mojo
