"""Slice 257 — corrupt-model simulation tests."""

from __future__ import annotations

import pytest

from hugrgate.chaos import (
    CORRUPTION_KINDS,
    MUST_REJECT_KINDS,
    ModelCorruptor,
)
from hugrgate.errors import GGUFError, SpecError
from hugrgate.runtimes.gguf import discover_gguf_models, parse_gguf_header


@pytest.fixture
def model_dir(tmp_path):
    good = ModelCorruptor.write_valid(tmp_path / "tiny.gguf")
    assert parse_gguf_header(good)["general.architecture"] == "llama"
    return tmp_path


# --- corruption kinds ---------------------------------------------------------------------

@pytest.mark.parametrize("kind", sorted(MUST_REJECT_KINDS))
def test_must_reject_kinds_are_rejected(model_dir, kind):
    corruptor = ModelCorruptor(seed=257)
    bad = corruptor.corrupt(model_dir / "tiny.gguf", kind)
    assert bad.name == f"tiny.corrupt-{kind}.gguf"
    err = corruptor.assert_rejected(bad)
    assert isinstance(err, GGUFError)
    # The original is untouched and still parses.
    assert parse_gguf_header(model_dir / "tiny.gguf")[
        "general.architecture"] == "llama"


def test_rejection_messages_name_the_corruption(model_dir):
    corruptor = ModelCorruptor(seed=1)
    expectations = {
        "flip_magic": "bad magic",
        "bad_version": "version 99",
        "truncate": "truncated file",
        "kv_bomb": "implausible",
        "zero_out": "bad magic",
    }
    for kind, fragment in expectations.items():
        bad = corruptor.corrupt(model_dir / "tiny.gguf", kind)
        err = corruptor.assert_rejected(bad)
        assert fragment in str(err), (kind, str(err))


def test_bit_flip_never_escapes_as_another_exception(model_dir):
    # bit_flip may or may not break parsing; the contract is that the
    # outcome is always GGUFError-or-valid-metadata, never a hang,
    # never a foreign exception type.
    corruptor = ModelCorruptor()
    for seed in range(25):
        bad = corruptor.corrupt(model_dir / "tiny.gguf", "bit_flip",
                                seed=seed)
        try:
            metadata = parse_gguf_header(bad)
        except GGUFError:
            pass
        else:
            assert isinstance(metadata, dict)


def test_corruption_is_seeded_reproducible(model_dir):
    a = ModelCorruptor(seed=9).corrupt(model_dir / "tiny.gguf", "truncate")
    a_bytes = a.read_bytes()
    a.unlink()
    b = ModelCorruptor(seed=9).corrupt(model_dir / "tiny.gguf", "truncate")
    assert b.read_bytes() == a_bytes
    b.unlink()
    c = ModelCorruptor(seed=10).corrupt(model_dir / "tiny.gguf", "truncate")
    assert c.read_bytes() != a_bytes


def test_unknown_corruption_kind_rejected():
    with pytest.raises(SpecError, match="unknown corruption kind"):
        ModelCorruptor().corrupt("/tmp/x.gguf", "meteor-strike")


def test_write_valid_rejects_negative_tensors(tmp_path):
    with pytest.raises(SpecError, match="tensor_count"):
        ModelCorruptor.write_valid(tmp_path / "x.gguf", tensor_count=-1)


# --- discovery never aborts -----------------------------------------------------------------

def test_discover_marks_corrupt_models_without_aborting(model_dir):
    corruptor = ModelCorruptor(seed=3)
    for kind in CORRUPTION_KINDS:
        if kind in MUST_REJECT_KINDS:
            corruptor.corrupt(model_dir / "tiny.gguf", kind)
    models = corruptor.assert_scan_survives(model_dir)
    by_name = {m.path.name: m for m in models}
    assert by_name["tiny.gguf"].ok is True
    for kind in MUST_REJECT_KINDS:
        name = f"tiny.corrupt-{kind}.gguf"
        assert by_name[name].ok is False, name
        assert by_name[name].error, name
    # direct entry point agrees
    direct = discover_gguf_models([model_dir])
    assert len(direct) == len(models)


def test_assert_rejected_fails_loudly_on_valid_file(model_dir):
    with pytest.raises(AssertionError, match="NOT rejected"):
        ModelCorruptor.assert_rejected(model_dir / "tiny.gguf")
