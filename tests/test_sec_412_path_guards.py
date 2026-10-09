"""Slice 412 — path traversal defenses.

Containment is the invariant: null bytes, ``..`` escapes, absolute
escapes, and symlink escapes all raise PathTraversalBlocked; the
checksum read boundary is jailed too.
"""

from __future__ import annotations

import pytest

from hugrgate.errors import HugrGateError, PathTraversalBlocked
from hugrgate.security.checksums import (
    build_manifest,
    verified_open,
)
from hugrgate.security.path_guards import (
    is_within,
    safe_join,
    safe_read_text,
)


def _jail(tmp_path):
    root = tmp_path / "jail"
    (root / "sub").mkdir(parents=True)
    (root / "sub" / "ok.txt").write_text("ok")
    (root / "top.txt").write_text("top")
    return root


def test_safe_join_normal(tmp_path):
    root = _jail(tmp_path)
    assert safe_join(root, "sub/ok.txt").read_text() == "ok"
    # Normalization that stays inside is fine.
    assert safe_join(root, "sub/../top.txt").read_text() == "top"


def test_dotdot_escape_blocked(tmp_path):
    root = _jail(tmp_path)
    with pytest.raises(PathTraversalBlocked) as exc:
        safe_join(root, "../../etc/passwd")
    assert exc.value.code == "path_traversal_blocked"
    assert exc.value.recoverable is False


def test_absolute_escape_blocked(tmp_path):
    root = _jail(tmp_path)
    with pytest.raises(PathTraversalBlocked):
        safe_join(root, "/etc/passwd")


def test_absolute_inside_root_allowed(tmp_path):
    root = _jail(tmp_path)
    target = root / "sub" / "ok.txt"
    assert safe_join(root, str(target)) == target


def test_symlink_escape_blocked(tmp_path):
    root = _jail(tmp_path)
    outside = tmp_path / "secret.txt"
    outside.write_text("secret")
    (root / "link").symlink_to(outside)
    with pytest.raises(PathTraversalBlocked):
        safe_join(root, "link")
    # Symlinks staying inside are fine.
    (root / "oklink").symlink_to(root / "sub" / "ok.txt")
    assert safe_join(root, "oklink").read_text() == "ok"


def test_null_byte_blocked(tmp_path):
    root = _jail(tmp_path)
    with pytest.raises(PathTraversalBlocked):
        safe_join(root, "sub/ok.txt\x00.png")


def test_nested_dotdot_blocked(tmp_path):
    root = _jail(tmp_path)
    with pytest.raises(PathTraversalBlocked):
        safe_join(root, "sub/../../..")


def test_is_within():
    import tempfile
    with tempfile.TemporaryDirectory() as td:
        assert is_within(td, td)
        assert not is_within(td, "/etc")


def test_safe_read_text(tmp_path):
    root = _jail(tmp_path)
    assert safe_read_text(root, "sub/ok.txt") == "ok"
    with pytest.raises(PathTraversalBlocked):
        safe_read_text(root, "../../etc/passwd")
    big = root / "big.txt"
    big.write_bytes(b"x" * 100)
    with pytest.raises(PathTraversalBlocked):
        safe_read_text(root, "big.txt", max_bytes=10)


def test_verified_open_jailed(tmp_path):
    root = _jail(tmp_path)
    manifest = build_manifest(root)
    # A hostile manifest key cannot escape the jail.
    evil = dict(manifest.files)
    evil["../../evil.txt"] = "0" * 64
    manifest.files.update(evil)
    with pytest.raises(PathTraversalBlocked):
        verified_open(root, "../../evil.txt", manifest)
    # Legit reads still work through the jail.
    with verified_open(root, "sub/ok.txt", manifest) as fh:
        assert fh.read() == b"ok"


def test_error_wire_round_trip():
    err = PathTraversalBlocked("escaped", path="../../x")
    rebuilt = HugrGateError.from_dict(err.to_dict())
    assert isinstance(rebuilt, PathTraversalBlocked)
