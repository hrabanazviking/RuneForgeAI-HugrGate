"""Slice 166 — local NLI model pack.

Unit tests for the NLI pack registry in ``hugrgate.runtimes.packs``.
"""

from __future__ import annotations

import pytest

from hugrgate.errors import SpecError
from hugrgate.runtimes.packs import (
    NLI_PACKS,
    ModelPack,
    default_pack,
    describe_packs,
    find_packs,
    get_pack,
    packs_for,
    runtime_for_pack,
)
from hugrgate.runtimes.transformers_rt import TransformersRuntime


def test_nli_packs_registered():
    assert len(NLI_PACKS) == 3
    for pack in NLI_PACKS:
        assert pack.kind == "nli"
        assert pack.hf_id and "/" in pack.hf_id
        assert pack.task == "zero-shot-classification"
        assert pack.description


def test_packs_for_rejects_unknown_kind():
    with pytest.raises(SpecError):
        packs_for("poetry")


def test_pack_rejects_unknown_kind():
    with pytest.raises(SpecError):
        ModelPack(kind="poetry", name="x", hf_id="x/y")


def test_exactly_one_default():
    assert default_pack("nli").default is True
    assert default_pack("nli").name == "bart-large-mnli"


def test_get_pack_roundtrip():
    pack = get_pack("nli", "deberta-v3-large-mnli")
    assert pack.hf_id == "MoritzLaurer/deberta-v3-large-mnli"


def test_get_pack_unknown_raises_with_known_list():
    with pytest.raises(SpecError, match="known:"):
        get_pack("nli", "nope")


def test_find_packs_searches():
    hits = find_packs("mnli")
    assert {p.name for p in hits} >= {"bart-large-mnli",
                                     "deberta-v3-large-mnli"}


def test_pack_to_model_ref():
    ref = get_pack("nli", "bart-large-mnli").to_model_ref()
    assert ref.runtime == "transformers"
    assert ref.path == "facebook/bart-large-mnli"
    assert ref.format == "hf"
    assert ref.alias == "bart-large-mnli"


def test_runtime_for_pack_builds_zero_shot_runtime():
    rt = runtime_for_pack(default_pack("nli"))
    assert isinstance(rt, TransformersRuntime)
    assert rt.task == "zero-shot-classification"
    assert rt.info().model is not None
    assert rt.info().model.path == "facebook/bart-large-mnli"


def test_runtime_for_pack_by_name_needs_kind():
    with pytest.raises(SpecError, match="kind is required"):
        runtime_for_pack("bart-large-mnli")
    rt = runtime_for_pack("nli-deberta-v3-small", kind="nli")
    assert isinstance(rt, TransformersRuntime)


def test_nli_pack_wires_to_nli_fn():
    # The documented recipe: pack -> runtime -> as_nli_fn -> NLIBackend.
    rt = runtime_for_pack("nli-deberta-v3-small", kind="nli")
    assert callable(rt.as_nli_fn())


def test_describe_packs_renders():
    text = describe_packs("nli")
    assert "## nli packs" in text
    assert "facebook/bart-large-mnli" in text
    assert "[default]" in text
