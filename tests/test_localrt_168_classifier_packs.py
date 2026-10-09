"""Slice 168 — local classifier model pack.

Unit tests for the classifier packs in ``hugrgate.runtimes.packs``.
"""

from __future__ import annotations

import pytest

from hugrgate.errors import SpecError
from hugrgate.runtimes.packs import (
    CLASSIFIER_PACKS,
    default_pack,
    describe_packs,
    find_packs,
    get_pack,
    packs_for,
    runtime_for_pack,
)
from hugrgate.runtimes.transformers_rt import TransformersRuntime


def test_classifier_packs_registered():
    assert len(CLASSIFIER_PACKS) == 2
    for pack in CLASSIFIER_PACKS:
        assert pack.kind == "classifier"
        assert pack.task == "text-classification"
        assert pack.labels
        assert pack.hf_id and "/" in pack.hf_id


def test_classifier_default():
    pack = default_pack("classifier")
    assert pack.name == "twitter-roberta-sentiment"
    assert pack.labels == ("positive", "neutral", "negative")


def test_go_emotions_labels():
    pack = get_pack("classifier", "go-emotions")
    assert len(pack.labels) == 28
    assert "joy" in pack.labels
    assert "neutral" in pack.labels


def test_runtime_for_classifier_pack():
    rt = runtime_for_pack(default_pack("classifier"))
    assert isinstance(rt, TransformersRuntime)
    assert rt.task == "text-classification"
    assert rt.info().model.path == \
        "cardiffnlp/twitter-roberta-base-sentiment-latest"


def test_runtime_for_pack_by_name():
    rt = runtime_for_pack("go-emotions", kind="classifier")
    assert isinstance(rt, TransformersRuntime)


def test_find_classifier_packs():
    hits = find_packs("emotion")
    assert [p.name for p in hits] == ["go-emotions"]


def test_unknown_classifier_pack():
    with pytest.raises(SpecError, match="known:"):
        get_pack("classifier", "nope")


def test_all_kinds_present():
    assert set(packs_for("classifier")) == set(CLASSIFIER_PACKS)
    assert len(packs_for("nli")) == 3
    assert len(packs_for("embedding")) == 4


def test_describe_all_kinds():
    text = describe_packs()
    assert "## nli packs" in text
    assert "## embedding packs" in text
    assert "## classifier packs" in text
    assert "28 labels" in text
