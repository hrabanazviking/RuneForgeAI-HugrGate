"""Slice 301 — Decision history API: record, read, bound, import."""

from __future__ import annotations

import time

import pytest

from hugrgate.errors import MemoryError
from hugrgate.memory import DecisionHistory, Episode
from hugrgate.provenance import DecisionRecord, ProvenanceStore


def _record(**kw) -> DecisionRecord:
    base = dict(request_hash="h" * 16, spec={"type": "binary"},
                backend="local", model="m1", value=True, probability=0.8)
    base.update(kw)
    return DecisionRecord(**base)


def test_record_and_get_roundtrip():
    hist = DecisionHistory()
    stored = hist.record(_record(), privacy_class="sensitive",
                         tags=["nightly"])
    assert isinstance(stored.episode_id, str) and stored.episode_id
    assert stored.privacy_class == "sensitive"
    assert stored.tags == ("nightly",)
    assert stored.outcome is None and stored.ground_truth is None
    fetched = hist.get(stored.episode_id)
    assert fetched == stored
    assert hist.count() == 1


def test_record_deep_copies_input():
    hist = DecisionHistory()
    rec = _record()
    stored = hist.record(rec)
    rec.metadata["mutated"] = True
    rec.value = "changed"
    fetched = hist.get(stored.episode_id)
    assert fetched.record.value is True
    assert "mutated" not in fetched.record.metadata


def test_get_returns_copies_not_aliases():
    hist = DecisionHistory()
    stored = hist.record(_record())
    fetched = hist.get(stored.episode_id)
    fetched.record.value = "tampered"
    assert hist.get(stored.episode_id).record.value is True


def test_get_unknown_id_raises_memory_error():
    hist = DecisionHistory()
    with pytest.raises(MemoryError):
        hist.get("no-such-episode")


def test_record_rejects_non_record():
    hist = DecisionHistory()
    with pytest.raises(TypeError):
        hist.record({"not": "a record"})


def test_record_rejects_unknown_privacy_class():
    hist = DecisionHistory()
    with pytest.raises(ValueError):
        hist.record(_record(), privacy_class="cosmic")


def test_episode_rejects_unknown_privacy_class():
    with pytest.raises(ValueError):
        Episode(episode_id="x", record=_record(), privacy_class="cosmic")


def test_recent_and_count():
    hist = DecisionHistory()
    assert hist.recent() == []
    assert hist.count() == 0
    ids = [hist.record(_record()).episode_id for _ in range(5)]
    assert hist.count() == 5
    last_two = hist.recent(2)
    assert [e.episode_id for e in last_two] == ids[3:]
    assert hist.recent(0) == []
    with pytest.raises(ValueError):
        hist.recent(-1)


def test_recent_returns_chronological_order():
    hist = DecisionHistory()
    first = hist.record(_record())
    second = hist.record(_record())
    got = hist.recent(10)
    assert got[0].episode_id == first.episode_id
    assert got[1].episode_id == second.episode_id


def test_by_request_hash():
    hist = DecisionHistory()
    hist.record(_record(request_hash="aa"))
    hist.record(_record(request_hash="bb"))
    hist.record(_record(request_hash="aa"))
    got = hist.by_request_hash("aa")
    assert len(got) == 2
    assert all(e.record.request_hash == "aa" for e in got)
    assert hist.by_request_hash("zz") == []


def test_episodes_between():
    hist = DecisionHistory()
    before = time.time()
    hist.record(_record())
    after = time.time()
    assert len(hist.episodes_between(before - 1, after + 1)) == 1
    assert hist.episodes_between(after + 10, after + 20) == []
    with pytest.raises(ValueError):
        hist.episodes_between(after + 5, after)


def test_max_episodes_evicts_oldest_first():
    hist = DecisionHistory(max_episodes=3)
    ids = [hist.record(_record()).episode_id for _ in range(5)]
    assert hist.count() == 3
    assert hist.evicted_count() == 2
    assert [e.episode_id for e in hist.recent(10)] == ids[2:]
    with pytest.raises(MemoryError):
        hist.get(ids[0])


def test_max_episodes_rejects_zero():
    with pytest.raises(ValueError):
        DecisionHistory(max_episodes=0)


def test_import_from_provenance():
    store = ProvenanceStore()
    for i in range(3):
        store.append(_record(request_hash=f"h{i:015d}"))
    hist = DecisionHistory()
    n = hist.import_from_provenance(store, privacy_class="public")
    assert n == 3
    assert hist.count() == 3
    assert all(e.privacy_class == "public" for e in hist.recent(10))
    # additive: importing again adds more episodes, never destroys
    assert hist.import_from_provenance(store) == 3
    assert hist.count() == 6


def test_import_from_empty_provenance():
    hist = DecisionHistory()
    assert hist.import_from_provenance(ProvenanceStore()) == 0
    assert hist.count() == 0


def test_import_rejects_wrong_type():
    hist = DecisionHistory()
    with pytest.raises(TypeError):
        hist.import_from_provenance(object())


def test_clear():
    hist = DecisionHistory()
    hist.record(_record())
    hist.record(_record())
    assert hist.clear() == 2
    assert hist.count() == 0
    assert hist.clear() == 0


def test_estimate_bytes_grows_with_episodes():
    hist = DecisionHistory()
    empty = hist.estimate_bytes()
    assert empty == 0
    hist.record(_record())
    assert hist.estimate_bytes() > 0


def test_thread_safety_smoke():
    import threading
    hist = DecisionHistory()
    errors: list[BaseException] = []

    def work():
        try:
            for _ in range(50):
                hist.record(_record())
                hist.recent(5)
                hist.count()
        except BaseException as exc:  # noqa: BLE001 - smoke test collects
            errors.append(exc)

    threads = [threading.Thread(target=work) for _ in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert not errors
    assert hist.count() == 200
