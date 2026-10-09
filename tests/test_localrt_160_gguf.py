"""Slice 160 — GGUF model discovery.

Unit tests for ``hugrgate.runtimes.gguf``. A tiny GGUF writer builds
real (minimal) GGUF files in tmp dirs — the parser is tested against
genuine bytes, not mocks.
"""

from __future__ import annotations

import struct
from pathlib import Path

import pytest

from hugrgate.runtimes.gguf import (
    GGUFError,
    discover_gguf_models,
    find_gguf_files,
    gguf_model_size_human,
    parse_gguf_header,
)


def _gguf_str(text: str) -> bytes:
    data = text.encode("utf-8")
    return struct.pack("<Q", len(data)) + data


def _kv(key: str, value_type: int, value: bytes) -> bytes:
    return _gguf_str(key) + struct.pack("<I", value_type) + value


def _u32(value: int) -> bytes:
    return struct.pack("<I", value)


def _u64(value: int) -> bytes:
    return struct.pack("<Q", value)


def write_gguf(path: Path, kvs: list[bytes],
               tensor_count: int = 0) -> Path:
    header = (b"GGUF" + _u32(3) + _u64(tensor_count) + _u64(len(kvs))
              + b"".join(kvs))
    path.write_bytes(header)
    return path


def sample_kvs() -> list[bytes]:
    return [
        _kv("general.architecture", 8, _gguf_str("llama")),
        _kv("general.name", 8, _gguf_str("TinyLlama")),
        _kv("llama.context_length", 4, _u32(2048)),
        _kv("llama.embedding_length", 4, _u32(1024)),
        _kv("llama.block_count", 4, _u32(12)),
        _kv("llama.attention.head_count", 4, _u32(8)),
        _kv("general.file_type", 4, _u32(2)),
        _kv("general.quantization_version", 4, _u32(2)),
        _kv("tags", 9, _u32(8) + _u64(2) + _gguf_str("tiny")
             + _gguf_str("test")),
        _kv("use_fp16", 7, b"\x01"),
    ]


# -- parse_gguf_header ---------------------------------------------------------------

def test_parses_all_value_types(tmp_path):
    path = write_gguf(tmp_path / "m.gguf", sample_kvs())
    meta = parse_gguf_header(path)
    assert meta["general.architecture"] == "llama"
    assert meta["general.name"] == "TinyLlama"
    assert meta["llama.context_length"] == 2048
    assert meta["llama.embedding_length"] == 1024
    assert meta["llama.block_count"] == 12
    assert meta["llama.attention.head_count"] == 8
    assert meta["general.file_type"] == 2
    assert meta["tags"] == ["tiny", "test"]
    assert meta["use_fp16"] is True
    assert meta["__tensor_count"] == 0


def test_rejects_bad_magic(tmp_path):
    path = tmp_path / "bad.gguf"
    path.write_bytes(b"NOPE" + b"\x00" * 32)
    with pytest.raises(GGUFError, match="bad magic"):
        parse_gguf_header(path)


def test_rejects_wrong_version(tmp_path):
    path = tmp_path / "v2.gguf"
    path.write_bytes(b"GGUF" + _u32(2) + _u64(0) + _u64(0))
    with pytest.raises(GGUFError, match="version 2"):
        parse_gguf_header(path)


def test_rejects_truncated_file(tmp_path):
    path = tmp_path / "trunc.gguf"
    path.write_bytes(b"GGUF" + _u32(3))
    with pytest.raises(GGUFError, match="truncated"):
        parse_gguf_header(path)


def test_rejects_unknown_value_type(tmp_path):
    path = write_gguf(tmp_path / "m.gguf",
                      [_kv("weird", 99, b"")])
    with pytest.raises(GGUFError, match="unknown GGUF value type"):
        parse_gguf_header(path)


def test_skips_tensor_infos(tmp_path):
    # one tensor info: name, n_dims=2, dims, dtype, offset
    tensor_info = (_gguf_str("tok_embd.weight") + _u32(2) + _u64(1024)
                   + _u64(32000) + _u32(1) + _u64(0))
    path = tmp_path / "t.gguf"
    path.write_bytes(b"GGUF" + _u32(3) + _u64(1) + _u64(0) + tensor_info)
    meta = parse_gguf_header(path)
    assert meta["__tensor_count"] == 1


# -- find_gguf_files ---------------------------------------------------------------------

def test_find_gguf_files_recursive_and_flat(tmp_path):
    (tmp_path / "a.gguf").write_bytes(b"x")
    sub = tmp_path / "sub"
    sub.mkdir()
    (sub / "b.gguf").write_bytes(b"x")
    (sub / "c.bin").write_bytes(b"x")
    found = find_gguf_files([tmp_path])
    assert {p.name for p in found} == {"a.gguf", "b.gguf"}
    flat = find_gguf_files([tmp_path], recursive=False)
    assert [p.name for p in flat] == ["a.gguf"]


def test_find_ignores_missing_dirs(tmp_path):
    assert find_gguf_files([tmp_path / "nope"]) == []


def test_find_dedupes_overlapping_dirs(tmp_path):
    sub = tmp_path / "sub"
    sub.mkdir()
    (sub / "b.gguf").write_bytes(b"x")
    found = find_gguf_files([tmp_path, sub])
    assert [p.name for p in found] == ["b.gguf"]


# -- discover_gguf_models -------------------------------------------------------------------

def test_discover_extracts_model_fields(tmp_path):
    write_gguf(tmp_path / "tiny.gguf", sample_kvs())
    (models,) = discover_gguf_models([tmp_path])
    assert models.ok
    assert models.architecture == "llama"
    assert models.name == "TinyLlama"
    assert models.context_length == 2048
    assert models.embedding_length == 1024
    assert models.block_count == 12
    assert models.head_count == 8
    assert models.quantization == "MOSTLY_Q4_0"
    assert models.size_bytes > 0
    assert "TinyLlama" in models.display


def test_discover_tolerates_corrupt_files(tmp_path):
    write_gguf(tmp_path / "good.gguf", sample_kvs())
    (tmp_path / "bad.gguf").write_bytes(b"NOPE")
    models = discover_gguf_models([tmp_path])
    assert len(models) == 2
    by_name = {m.path.name: m for m in models}
    assert by_name["good.gguf"].ok
    assert not by_name["bad.gguf"].ok
    assert by_name["bad.gguf"].error is not None


def test_discover_unknown_quantization_labeled(tmp_path):
    kvs = [_kv("general.architecture", 8, _gguf_str("llama")),
           _kv("general.file_type", 4, _u32(999))]
    write_gguf(tmp_path / "m.gguf", kvs)
    (model,) = discover_gguf_models([tmp_path])
    assert model.quantization == "file_type_999"


def test_discover_empty_dir(tmp_path):
    assert discover_gguf_models([tmp_path]) == []


# -- gguf_model_size_human ---------------------------------------------------------------------

def test_size_human():
    assert gguf_model_size_human(512) == "512.0 B"
    assert gguf_model_size_human(2048) == "2.0 KB"
    assert gguf_model_size_human(5 * 1024 * 1024) == "5.0 MB"
