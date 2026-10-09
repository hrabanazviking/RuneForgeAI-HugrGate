"""Slice 161 — model metadata scanner.

Unit tests for ``hugrgate.runtimes.metadata``. Fixtures are genuine
artifacts built in tmp dirs: a minimal GGUF file, a real safetensors
header, and an HF repo layout with config + README frontmatter.
"""

from __future__ import annotations

import json
import struct
from pathlib import Path

from hugrgate.runtimes.metadata import (
    ModelMetadata,
    scan_directory,
    scan_model,
)

# -- fixture builders ------------------------------------------------------------


def _gguf_str(text: str) -> bytes:
    data = text.encode()
    return struct.pack("<Q", len(data)) + data


def write_gguf(path: Path) -> Path:
    def kv(key: str, vtype: int, value: bytes) -> bytes:
        return _gguf_str(key) + struct.pack("<I", vtype) + value

    kvs = [
        kv("general.architecture", 8, _gguf_str("llama")),
        kv("general.name", 8, _gguf_str("Tiny")),
        kv("llama.context_length", 4, struct.pack("<I", 2048)),
        kv("general.file_type", 4, struct.pack("<I", 2)),
    ]
    path.write_bytes(b"GGUF" + struct.pack("<I", 3) + struct.pack("<Q", 0)
                     + struct.pack("<Q", len(kvs)) + b"".join(kvs))
    return path


def write_safetensors(path: Path, tensors: dict[str, list[int]]) -> Path:
    header = {"__metadata__": {"format": "pt"}}
    for name, shape in tensors.items():
        header[name] = {"dtype": "F32", "shape": shape,
                        "data_offsets": [0, 0]}
    blob = json.dumps(header).encode()
    path.write_bytes(struct.pack("<Q", len(blob)) + blob)
    return path


def write_hf_repo(root: Path) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    (root / "config.json").write_text(json.dumps({
        "architectures": ["LlamaForCausalLM"],
        "model_type": "llama",
        "hidden_size": 1024,
        "num_hidden_layers": 12,
        "max_position_embeddings": 4096,
    }))
    (root / "tokenizer_config.json").write_text(json.dumps({
        "tokenizer_class": "LlamaTokenizer",
    }))
    (root / "README.md").write_text(
        "---\nlicense: apache-2.0\npipeline_tag: text-generation\n"
        "tags: [tiny, test]\nlanguage: [en]\n---\n# Tiny\n")
    return root


# -- scan_model: gguf ----------------------------------------------------------------

def test_scan_gguf_extracts_fields(tmp_path):
    path = write_gguf(tmp_path / "tiny.gguf")
    meta = scan_model(path)
    assert meta.ok
    assert meta.format == "gguf"
    assert meta.architecture == "llama"
    assert meta.name == "Tiny"
    assert meta.context_length == 2048
    assert meta.quantization == "MOSTLY_Q4_0"
    assert meta.parameters_estimate > 0
    assert meta.parameters == 0  # estimate only for GGUF
    assert "general.architecture" in meta.extra["gguf_keys"]


def test_scan_gguf_corrupt_gives_error(tmp_path):
    path = tmp_path / "bad.gguf"
    path.write_bytes(b"NOPE")
    meta = scan_model(path)
    assert not meta.ok
    assert meta.error is not None


# -- scan_model: safetensors ---------------------------------------------------------------

def test_scan_safetensors_counts_parameters(tmp_path):
    path = write_safetensors(tmp_path / "m.safetensors",
                             {"w1": [1024, 512], "b1": [512]})
    meta = scan_model(path)
    assert meta.ok
    assert meta.format == "safetensors"
    assert meta.parameters == 1024 * 512 + 512
    assert meta.parameters_human == "524.8K"


def test_scan_safetensors_corrupt_gives_error(tmp_path):
    path = tmp_path / "bad.safetensors"
    path.write_bytes(b"\xff" * 32)
    meta = scan_model(path)
    assert not meta.ok


# -- scan_model: onnx --------------------------------------------------------------------------

def test_scan_onnx_shallow_without_package(tmp_path):
    path = tmp_path / "m.onnx"
    path.write_bytes(b"\x08\x00" * 16)
    meta = scan_model(path)
    assert meta.format == "onnx"
    assert meta.scan_depth == "shallow"
    assert meta.size_bytes == 32


# -- scan_model: hf repo --------------------------------------------------------------------------

def test_scan_hf_repo_reads_config_and_frontmatter(tmp_path):
    repo = write_hf_repo(tmp_path / "tiny-llama")
    meta = scan_model(repo)
    assert meta.ok
    assert meta.format == "hf"
    assert meta.architecture == "llama"
    assert meta.context_length == 4096
    assert meta.extra["hidden_size"] == 1024
    assert meta.extra["num_layers"] == 12
    assert meta.tokenizer == "LlamaTokenizer"
    assert meta.license == "apache-2.0"
    assert meta.tags == ["tiny", "test"]
    assert meta.languages == ["en"]
    assert meta.extra["pipeline_tag"] == "text-generation"


def test_scan_hf_repo_without_config_is_shallow(tmp_path):
    repo = tmp_path / "bare"
    repo.mkdir()
    meta = scan_model(repo)
    # no config.json -> not an HF repo -> unsupported suffix error
    assert not meta.ok or meta.scan_depth == "shallow"


# -- scan_model: misc -------------------------------------------------------------------------------

def test_scan_unsupported_suffix_errors(tmp_path):
    path = tmp_path / "notes.txt"
    path.write_text("hi")
    meta = scan_model(path)
    assert not meta.ok
    assert "unsupported suffix" in meta.error


def test_scan_bin_is_shallow(tmp_path):
    path = tmp_path / "pytorch_model.bin"
    path.write_bytes(b"\x00" * 64)
    meta = scan_model(path)
    assert meta.ok
    assert meta.scan_depth == "shallow"
    assert meta.format == "pytorch-bin"


# -- scan_directory --------------------------------------------------------------------------------------

def test_scan_directory_finds_mixed_artifacts(tmp_path):
    write_gguf(tmp_path / "a.gguf")
    write_safetensors(tmp_path / "b.safetensors", {"w": [4, 4]})
    write_hf_repo(tmp_path / "repo")
    (tmp_path / "notes.txt").write_text("ignore me")
    metas = scan_directory([tmp_path])
    by_format = {m.format for m in metas}
    assert by_format == {"gguf", "safetensors", "hf"}
    assert all(m.ok for m in metas)


def test_scan_directory_excludes_repo_internals(tmp_path):
    repo = write_hf_repo(tmp_path / "repo")
    write_safetensors(repo / "model.safetensors", {"w": [2, 2]})
    metas = scan_directory([tmp_path])
    assert len(metas) == 1
    assert metas[0].format == "hf"


def test_scan_directory_non_recursive(tmp_path):
    sub = tmp_path / "sub"
    sub.mkdir()
    write_gguf(sub / "deep.gguf")
    write_gguf(tmp_path / "top.gguf")
    metas = scan_directory([tmp_path], recursive=False)
    assert [m.path.name for m in metas] == ["top.gguf"]


def test_scan_directory_ignores_missing_dirs(tmp_path):
    assert scan_directory([tmp_path / "nope"]) == []


def test_metadata_dataclass_defaults():
    meta = ModelMetadata(path=Path("x"), format="gguf", size_bytes=8)
    assert meta.ok
    assert meta.parameters_human == "0"
    meta.parameters_estimate = 7e9
    assert meta.parameters_human == "7.0B"
