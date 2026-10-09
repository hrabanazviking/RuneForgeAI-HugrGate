"""Slice 167 — local embedding model pack.

Unit tests for the embedding packs in ``hugrgate.runtimes.packs``.
"""

from __future__ import annotations

import pytest

from hugrgate.errors import SpecError
from hugrgate.runtimes.packs import (
    EMBEDDING_PACKS,
    default_pack,
    describe_packs,
    find_packs,
    get_pack,
    runtime_for_pack,
)
from hugrgate.runtimes.transformers_rt import TransformersRuntime


def test_embedding_packs_registered():
    assert len(EMBEDDING_PACKS) == 4
    for pack in EMBEDDING_PACKS:
        assert pack.kind == "embedding"
        assert pack.task == "feature-extraction"
        assert pack.dims > 0
        assert pack.hf_id and "/" in pack.hf_id


def test_embedding_default():
    pack = default_pack("embedding")
    assert pack.name == "all-minilm-l6-v2"
    assert pack.dims == 384


def test_get_embedding_pack():
    pack = get_pack("embedding", "bge-small-en-v1.5")
    assert pack.hf_id == "BAAI/bge-small-en-v1.5"
    assert pack.dims == 384


def test_embedding_pack_dims_vary():
    assert get_pack("embedding", "all-minilm-l6-v2").dims == 384
    assert get_pack("embedding", "nomic-embed-text-v1.5").dims == 768


def test_e5_pack_carries_prefix_hints():
    pack = get_pack("embedding", "e5-small-v2")
    assert pack.extra["query_prefix"] == "query: "
    assert pack.extra["passage_prefix"] == "passage: "


def test_runtime_for_embedding_pack():
    rt = runtime_for_pack(default_pack("embedding"))
    assert isinstance(rt, TransformersRuntime)
    assert rt.task == "feature-extraction"
    assert rt.info().model.path == \
        "sentence-transformers/all-MiniLM-L6-v2"


def test_runtime_for_pack_by_name():
    rt = runtime_for_pack("bge-small-en-v1.5", kind="embedding")
    assert isinstance(rt, TransformersRuntime)
    assert rt.task == "feature-extraction"


def test_find_embedding_packs():
    hits = find_packs("bge")
    assert [p.name for p in hits] == ["bge-small-en-v1.5"]


def test_unknown_embedding_pack():
    with pytest.raises(SpecError, match="known:"):
        get_pack("embedding", "nope")


def test_describe_embedding_packs():
    text = describe_packs("embedding")
    assert "## embedding packs" in text
    assert "384d" in text
    assert "768d" in text
