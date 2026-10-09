"""Tests for slice 202 — node identity."""

from __future__ import annotations

import hashlib
import json
import os
import stat

import pytest

from hugrgate.cluster.identity import KEY_BYTES, NodeIdentity
from hugrgate.errors import SpecError


def json_blob(d):
    return json.dumps(d)


# --- success ---------------------------------------------------------------

def test_generate_produces_unique_ids():
    a, b = NodeIdentity.generate(), NodeIdentity.generate()
    assert a.node_id != b.node_id
    assert len(a.node_id) == 64
    assert all(c in "0123456789abcdef" for c in a.node_id)


def test_node_id_is_sha256_of_key():
    ident = NodeIdentity.generate()
    assert ident.node_id == hashlib.sha256(ident.key).hexdigest()


def test_save_load_round_trip_is_stable(tmp_path):
    ident = NodeIdentity.generate("norn-1")
    path = tmp_path / "node.key"
    ident.save(path)
    back = NodeIdentity.load(path)
    assert back.node_id == ident.node_id
    assert back.display_name == "norn-1"
    assert back.key == ident.key


def test_key_file_is_owner_only(tmp_path):
    path = tmp_path / "node.key"
    NodeIdentity.generate().save(path)
    mode = stat.S_IMODE(os.stat(path).st_mode)
    assert mode == 0o600, f"key file mode {oct(mode)} is not 0600"


def test_advertisement_never_leaks_secret():
    ident = NodeIdentity.generate("skald")
    ad = ident.to_advertisement()
    assert ad["node_id"] == ident.node_id
    assert ad["display_name"] == "skald"
    assert "key" not in json_blob(ad)
    assert ident.key.hex() not in json_blob(ad)


# --- failure -----------------------------------------------------------------

def test_rejects_short_key():
    with pytest.raises(SpecError, match="32 bytes"):
        NodeIdentity(key=b"short")


def test_rejects_non_bytes_key():
    with pytest.raises(SpecError, match="32 bytes"):
        NodeIdentity(key="ab" * 32)  # type: ignore[arg-type]


def test_load_missing_file():
    with pytest.raises(SpecError, match="not found"):
        NodeIdentity.load("/nonexistent/path/node.key")


def test_load_malformed_json(tmp_path):
    path = tmp_path / "bad.key"
    path.write_text("{not json", encoding="utf-8")
    with pytest.raises(SpecError, match="unreadable"):
        NodeIdentity.load(path)


def test_load_missing_key_field(tmp_path):
    path = tmp_path / "nokey.key"
    path.write_text('{"display_name": "x"}', encoding="utf-8")
    with pytest.raises(SpecError, match="no hex 'key'"):
        NodeIdentity.load(path)


def test_load_malformed_key_hex(tmp_path):
    path = tmp_path / "badhex.key"
    path.write_text('{"key": "zzzz"}', encoding="utf-8")
    with pytest.raises(SpecError, match="malformed key"):
        NodeIdentity.load(path)


def test_load_rejects_non_object(tmp_path):
    path = tmp_path / "list.key"
    path.write_text('[1, 2]', encoding="utf-8")
    with pytest.raises(SpecError, match="JSON object"):
        NodeIdentity.load(path)


# --- boundary ----------------------------------------------------------------

def test_empty_display_name_allowed():
    assert NodeIdentity.generate().display_name == ""


def test_overwrite_replaces_key(tmp_path):
    path = tmp_path / "node.key"
    first = NodeIdentity.generate()
    first.save(path)
    second = NodeIdentity.generate()
    second.save(path)
    assert NodeIdentity.load(path).node_id == second.node_id


def test_key_length_constant():
    assert KEY_BYTES == 32
    assert len(NodeIdentity.generate().key) == KEY_BYTES
