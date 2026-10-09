"""Slice 406 — model checksum enforcement.

Manifests pin every file in a model directory to a SHA-256 digest;
tampered, truncated, missing, or attacker-added files fail closed
before any loader parses the bytes.
"""

from __future__ import annotations

import pytest

from hugrgate.errors import SignatureVerificationFailed
from hugrgate.security.checksums import (
    ChecksumManifest,
    ModelChecksumGate,
    build_manifest,
    enforce_manifest,
    hash_file,
    verified_open,
    verify_manifest,
)


def _model_dir(tmp_path):
    root = tmp_path / "model"
    root.mkdir()
    (root / "weights.bin").write_bytes(b"\x00" * 1024 + b"weights")
    (root / "config.json").write_text('{"name": "m"}')
    (root / "tokenizer").mkdir()
    (root / "tokenizer" / "vocab.txt").write_text("a b c")
    return root


def test_build_and_verify_round_trip(tmp_path):
    root = _model_dir(tmp_path)
    manifest = build_manifest(root)
    assert len(manifest.files) == 3
    report = verify_manifest(root, manifest)
    assert report.passed
    assert sorted(report.ok) == sorted(manifest.files)


def test_tampered_file_detected(tmp_path):
    root = _model_dir(tmp_path)
    manifest = build_manifest(root)
    (root / "weights.bin").write_bytes(b"\x00" * 1024 + b"EVIL")
    report = verify_manifest(root, manifest)
    assert not report.passed
    assert report.mismatched == ["weights.bin"]
    with pytest.raises(SignatureVerificationFailed) as exc:
        enforce_manifest(root, manifest)
    assert "mismatched" in str(exc.value)


def test_truncated_file_detected(tmp_path):
    root = _model_dir(tmp_path)
    manifest = build_manifest(root)
    (root / "weights.bin").write_bytes(b"\x00" * 10)
    assert verify_manifest(root, manifest).mismatched == ["weights.bin"]


def test_missing_file_detected(tmp_path):
    root = _model_dir(tmp_path)
    manifest = build_manifest(root)
    (root / "config.json").unlink()
    report = verify_manifest(root, manifest)
    assert report.missing == ["config.json"]
    assert not report.passed


def test_extra_file_flagged_in_strict_mode(tmp_path):
    root = _model_dir(tmp_path)
    manifest = build_manifest(root)
    (root / "backdoor.sh").write_text("evil")
    assert verify_manifest(root, manifest).extra == []  # non-strict: blind
    report = verify_manifest(root, manifest, strict=True)
    assert report.extra == ["backdoor.sh"]
    with pytest.raises(SignatureVerificationFailed):
        enforce_manifest(root, manifest, strict=True)


def test_verified_open_refuses_tampered(tmp_path):
    root = _model_dir(tmp_path)
    manifest = build_manifest(root)
    with verified_open(root, "config.json", manifest) as fh:
        assert fh.read() == b'{"name": "m"}'
    (root / "config.json").write_text('{"name": "evil"}')
    with pytest.raises(SignatureVerificationFailed):
        verified_open(root, "config.json", manifest)
    with pytest.raises(SignatureVerificationFailed):
        verified_open(root, "not-pinned.txt", manifest)


def test_gate_blocks_loader_on_tamper(tmp_path):
    root = _model_dir(tmp_path)
    gate = ModelChecksumGate(build_manifest(root))
    calls = []
    assert gate.load(root, lambda r: calls.append(r) or "loaded") == "loaded"
    (root / "weights.bin").write_bytes(b"tampered")
    with pytest.raises(SignatureVerificationFailed):
        gate.load(root, lambda r: calls.append(r))
    assert len(calls) == 1  # loader never saw the tampered bytes


def test_manifest_serialization_round_trip(tmp_path):
    manifest = build_manifest(_model_dir(tmp_path))
    clone = ChecksumManifest.from_json(manifest.to_json())
    assert clone.files == manifest.files
    with pytest.raises(SignatureVerificationFailed):
        ChecksumManifest.from_dict({"algorithm": "md5", "files": {}})
    with pytest.raises(SignatureVerificationFailed):
        ChecksumManifest.from_json("not json")


def test_hash_file_is_stable(tmp_path):
    p = tmp_path / "f.bin"
    p.write_bytes(b"abc" * 1000)
    assert hash_file(p) == hash_file(p)
    assert len(hash_file(p)) == 64
