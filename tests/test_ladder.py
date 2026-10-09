"""Tests for Batch D (Slices 31-40): the intelligence ladder."""

from __future__ import annotations

import time

import pytest

from hugrgate import (
    Backend, BackendRegistry, DecisionPolicy, DecisionResult, DecisionSpec,
    HugrGate, Abstention, BackendError, BackendUnavailable,
    PrivacyViolation, SpecError, TimeoutError,
)
from hugrgate.backends.embedding import HashEmbedder, PrototypeBackend
from hugrgate.backends.llm import LLMBackend, LLMChoice, LLMEngine
from hugrgate.backends.nli import NLIBackend
from hugrgate.cache import DecisionCache, cache_key
from hugrgate.ladder import LadderRouter, LadderRung
from hugrgate.negotiate import select_backend
from hugrgate.privacy import PrivacyGuard
from hugrgate.provenance import DecisionRecord, ProvenanceStore


# --------------------------------------------------------------------------
# Test doubles

class FixedBackend(Backend):
    """Returns a fixed-confidence result; optionally fails or abstains."""

    def __init__(self, name, prob=0.9, value="a", latency=5.0, remote=False,
                 fail=None, do_abstain=False, cost=0.0, options=None):
        self.name = name
        self._prob = prob
        self._value = value
        self._latency = latency
        self.is_remote = remote
        self._fail = fail
        self._abstain = do_abstain
        self._cost = cost
        self._options = options or ["a", "b"]
        self.calls = 0

    def capabilities(self):
        return {"spec_types": ["categorical"]}

    def supports(self, spec):
        return spec.type == "categorical"

    def evaluate(self, state, spec, context=None):
        self.calls += 1
        if self._fail:
            raise self._fail
        if self._abstain:
            raise Abstention("nope", reason="test")
        n = len(spec.options)
        rest = (1.0 - self._prob) / (n - 1)
        return DecisionResult(
            value=self._value, probability=self._prob,
            distribution={o: (self._prob if o == self._value else rest)
                          for o in spec.options},
            backend=self.name)

    def estimated_latency(self):
        return self._latency

    def estimated_cost(self):
        return self._cost


def make_spec():
    return DecisionSpec(type="categorical", options=["a", "b"])


def make_router(*backends, **kw):
    registry = BackendRegistry()
    for b in backends:
        registry.register(b)
    rungs = [LadderRung(b.name, min_confidence=mc)
             for b, mc in kw.pop("gates", [(b, 0.8) for b in backends])]
    return LadderRouter(registry, rungs=rungs, **kw)


# --------------------------------------------------------------------------
# Slice 31 — LadderRouter

def test_ladder_easy_case_stops_at_rung_one():
    fast = FixedBackend("fast", prob=0.95)
    slow = FixedBackend("slow", prob=0.99)
    router = make_router(fast, slow)
    result = router.decide({"x": 1}, make_spec())
    assert result.value == "a"
    assert result.backend == "fast"
    assert slow.calls == 0
    assert len(router.last_audit) == 1
    assert router.last_audit[0].outcome == "accepted"
    assert result.metadata["ladder_rung"] == 0


def test_ladder_hard_case_climbs():
    weak = FixedBackend("weak", prob=0.5)
    strong = FixedBackend("strong", prob=0.95)
    router = make_router(weak, strong)
    result = router.decide({"x": 1}, make_spec())
    assert result.backend == "strong"
    assert [e.outcome for e in router.last_audit] == [
        "below_confidence", "accepted"]
    assert result.metadata["ladder_trace"][0]["backend_name"] == "weak"


def test_ladder_exhausted_abstains():
    weak = FixedBackend("weak", prob=0.5)
    weaker = FixedBackend("weaker", prob=0.4)
    router = make_router(weak, weaker)
    with pytest.raises(Abstention) as exc:
        router.decide({"x": 1}, make_spec())
    assert exc.value.reason == "ladder_exhausted"
    assert len(exc.value.details["ladder_trace"]) == 2


def test_ladder_backend_error_climbs():
    broken = FixedBackend("broken", fail=BackendError("boom"))
    strong = FixedBackend("strong", prob=0.95)
    router = make_router(broken, strong)
    result = router.decide({"x": 1}, make_spec())
    assert result.backend == "strong"
    assert router.last_audit[0].outcome == "backend_error"


def test_ladder_backend_abstention_climbs():
    shy = FixedBackend("shy", do_abstain=True)
    strong = FixedBackend("strong", prob=0.95)
    router = make_router(shy, strong)
    result = router.decide({"x": 1}, make_spec())
    assert result.backend == "strong"
    assert router.last_audit[0].outcome == "backend_abstained"


def test_ladder_unknown_backend_skipped():
    strong = FixedBackend("strong", prob=0.95)
    router = make_router(strong)
    router.rungs.insert(0, LadderRung("ghost", min_confidence=0.9))
    result = router.decide({"x": 1}, make_spec())
    assert result.backend == "strong"
    assert router.last_audit[0].outcome == "skipped_unknown_backend"


def test_ladder_per_spec_type_ladders():
    fast = FixedBackend("fast", prob=0.95)
    registry = BackendRegistry()
    registry.register(fast)
    router = LadderRouter(
        registry,
        ladders={"categorical": [LadderRung("fast", min_confidence=0.9)]})
    assert router.ladder_for(make_spec())[0].backend_name == "fast"
    with pytest.raises(SpecError):
        router.decide({"x": 1},
                      DecisionSpec(type="binary", statement="s?"))


def test_ladder_needs_rungs():
    with pytest.raises(SpecError):
        LadderRouter(BackendRegistry())


def test_ladder_rung_validation():
    with pytest.raises(SpecError):
        LadderRung("x", min_confidence=1.5)
    with pytest.raises(SpecError):
        LadderRung("x", latency_budget_ms=-1.0)


def test_ladder_provenance_logs_attempted_rungs():
    weak = FixedBackend("weak", prob=0.5)
    strong = FixedBackend("strong", prob=0.95)
    store = ProvenanceStore()
    router = make_router(weak, strong, provenance=store)
    router.decide({"x": 1}, make_spec())
    assert store.count() == 2
    assert [r.backend for r in store.recent(2)] == ["weak", "strong"]


def test_ladder_policy_minimum_probability_applies():
    strong = FixedBackend("strong", prob=0.95)
    router = make_router(strong, gates=[(strong, 0.5)])
    policy = DecisionPolicy(minimum_probability=0.99)
    with pytest.raises(Abstention):
        router.decide({"x": 1}, make_spec(), policy)


def test_ladder_rejects_invalid_backend_values():
    class Evil(FixedBackend):
        def evaluate(self, state, spec, context=None):
            return DecisionResult(value="zzz", probability=0.99,
                                  distribution={"zzz": 1.0})
    router = make_router(Evil("evil"))
    with pytest.raises(SpecError):
        router.decide({"x": 1}, make_spec())


# --------------------------------------------------------------------------
# Slice 32 — latency budgets + privacy gate

def test_ladder_skips_rung_over_its_budget():
    slow = FixedBackend("slow", prob=0.99, latency=500.0)
    fast = FixedBackend("fast", prob=0.95, latency=5.0)
    registry = BackendRegistry()
    registry.register(slow)
    registry.register(fast)
    router = LadderRouter(registry, rungs=[
        LadderRung("slow", min_confidence=0.9, latency_budget_ms=50.0),
        LadderRung("fast", min_confidence=0.9),
    ])
    result = router.decide({"x": 1}, make_spec())
    assert result.backend == "fast"
    assert slow.calls == 0
    assert router.last_audit[0].outcome == "skipped_latency_budget"


def test_ladder_skips_rung_over_remaining_budget():
    medium = FixedBackend("medium", prob=0.5, latency=40.0)
    slow = FixedBackend("slow", prob=0.99, latency=500.0)
    router = make_router(medium, slow)
    policy = DecisionPolicy(maximum_latency_ms=100.0)
    with pytest.raises(Abstention):
        router.decide({"x": 1}, make_spec(), policy)
    assert router.last_audit[1].outcome == "skipped_latency_budget"


def test_ladder_privacy_gate_blocks_remote_rung():
    remote = FixedBackend("remote", prob=0.99, remote=True)
    local = FixedBackend("local", prob=0.95)
    router = make_router(remote, local)
    result = router.decide({"x": 1}, make_spec(),
                           DecisionPolicy(remote_inference=False))
    assert result.backend == "local"
    assert remote.calls == 0
    assert router.last_audit[0].outcome == "skipped_privacy_blocked"


def test_ladder_privacy_gate_allows_remote_when_permitted():
    remote = FixedBackend("remote", prob=0.99, remote=True)
    local = FixedBackend("local", prob=0.95)
    router = make_router(remote, local)
    result = router.decide({"x": 1}, make_spec(),
                           DecisionPolicy(remote_inference=True))
    assert result.backend == "remote"


def test_ladder_guard_forbidden_overrides_policy():
    remote = FixedBackend("remote", prob=0.99, remote=True)
    local = FixedBackend("local", prob=0.95)
    router = make_router(remote, local,
                         privacy_guard=PrivacyGuard(remote_inference="forbidden"))
    result = router.decide({"x": 1}, make_spec(),
                           DecisionPolicy(remote_inference=True))
    assert result.backend == "local"
    assert router.last_audit[0].outcome == "skipped_privacy_blocked"


# --------------------------------------------------------------------------
# Slice 33 — embedding backend

def test_hash_embedder_deterministic_and_normalized():
    emb = HashEmbedder(dim=64)
    a = emb.embed(["hello world", ""])
    b = emb.embed(["hello world", ""])
    assert a.shape == (2, 64)
    assert (a == b).all()
    assert abs(float((a[0] ** 2).sum()) - 1.0) < 1e-9
    assert (a[1] == 0).all()  # empty text -> zero vector


def test_hash_embedder_offline_no_download():
    emb = HashEmbedder()
    vecs = emb.embed(["the quick brown fox"])
    assert vecs.shape == (1, 256)
    assert vecs.dtype.kind == "f"


SPORTS = [
    "the team scored a goal in the final match",
    "the quarterback threw a touchdown pass",
    "the striker kicked the ball into the net",
    "overtime victory for the home team",
]
COOKING = [
    "add salt and simmer the soup gently",
    "bake the bread at high heat",
    "chop the onions and garlic finely",
    "whisk the eggs into the batter",
]


def trained_prototype():
    backend = PrototypeBackend(HashEmbedder(dim=256), temperature=0.25)
    backend.fit([(t, "sports") for t in SPORTS]
                + [(t, "cooking") for t in COOKING])
    return backend


def test_prototype_classifies_held_out():
    backend = trained_prototype()
    spec = DecisionSpec(type="categorical", options=["sports", "cooking"])
    r1 = backend.evaluate(
        {"text": "the striker scored the winning goal in overtime"}, spec)
    r2 = backend.evaluate(
        {"text": "bake the bread at high heat until golden"}, spec)
    assert r1.value == "sports"
    assert r2.value == "cooking"
    assert r1.probability > 0.5
    assert abs(sum(r1.distribution.values()) - 1.0) < 1e-6
    assert set(r1.distribution) == {"sports", "cooking"}


def test_prototype_binary_spec():
    backend = PrototypeBackend()
    backend.fit([("this is wonderful", "true"), ("this is awful", "false"),
                 ("absolutely delightful", "true"), ("utterly terrible", "false")])
    spec = DecisionSpec(type="binary", statement="Is it positive?")
    result = backend.evaluate({"text": "this is wonderful indeed"}, spec)
    assert result.value == "true"
    assert set(result.distribution) == {"true", "false"}


def test_prototype_unfitted_unavailable():
    backend = PrototypeBackend()
    with pytest.raises(BackendUnavailable):
        backend.evaluate({"text": "hi"}, make_spec())


def test_prototype_missing_class_unavailable():
    backend = PrototypeBackend()
    backend.fit([("aaa bbb", "sports"), ("ccc ddd", "cooking")])
    spec = DecisionSpec(type="categorical",
                        options=["sports", "cooking", "politics"])
    with pytest.raises(BackendUnavailable):
        backend.evaluate({"text": "hello"}, spec)


def test_prototype_supports():
    backend = trained_prototype()
    assert backend.supports(make_spec())
    assert backend.supports(DecisionSpec(type="binary", statement="s?"))
    assert not backend.supports(
        DecisionSpec(type="numeric", minimum=0.0, maximum=1.0))
    assert backend.fitted
    assert backend.health()["status"] == "ok"


def test_prototype_text_field_fallback():
    backend = trained_prototype()
    spec = DecisionSpec(type="categorical", options=["sports", "cooking"])
    result = backend.evaluate(
        {"message": "the team won the match in overtime"}, spec)
    assert result.value == "sports"


# --------------------------------------------------------------------------
# Slice 34 — NLI backend

def test_nli_entailment_true():
    backend = NLIBackend(nli_fn=lambda p, s: 0.9)
    spec = DecisionSpec(type="binary", statement="The server is down.")
    result = backend.evaluate({"premise": "The server is down."}, spec)
    assert result.value == "true"
    assert result.probability == pytest.approx(0.9)
    assert result.distribution["true"] == pytest.approx(0.9)
    assert result.distribution["false"] == pytest.approx(0.1)


def test_nli_entailment_false():
    backend = NLIBackend(nli_fn=lambda p, s: 0.2)
    spec = DecisionSpec(type="binary", statement="The server is down.")
    result = backend.evaluate({"text": "All systems nominal."}, spec)
    assert result.value == "false"
    assert result.probability == pytest.approx(0.8)


def test_nli_no_engine_unavailable():
    backend = NLIBackend()
    spec = DecisionSpec(type="binary", statement="s?")
    with pytest.raises(BackendUnavailable):
        backend.evaluate({"premise": "p"}, spec)
    assert backend.health()["status"] == "unavailable"


def test_nli_constrained_to_binary():
    backend = NLIBackend(nli_fn=lambda p, s: 0.9)
    assert not backend.supports(make_spec())
    with pytest.raises(BackendError):
        backend.evaluate({"premise": "p"}, make_spec())


def test_nli_bad_fn_output_rejected():
    backend = NLIBackend(nli_fn=lambda p, s: 1.7)
    with pytest.raises(BackendError):
        backend.evaluate({"premise": "p"},
                         DecisionSpec(type="binary", statement="s?"))


# --------------------------------------------------------------------------
# Slice 35 — LLM backend

class MockEngine(LLMEngine):
    name = "mock-engine"

    def __init__(self, text, confidence=0.8):
        self.text = text
        self.confidence = confidence
        self.last = None

    def generate(self, prompt, choices, max_tokens, timeout_s):
        self.last = {"prompt": prompt, "choices": choices,
                     "max_tokens": max_tokens, "timeout_s": timeout_s}
        return LLMChoice(value=self.text, confidence=self.confidence)


def test_llm_constrained_categorical():
    backend = LLMBackend(engine=MockEngine("escalate", 0.85), max_tokens=16)
    spec = DecisionSpec(type="categorical",
                        options=["ignore", "log", "inspect", "escalate"])
    result = backend.evaluate({"severity": 9}, spec)
    assert result.value == "escalate"
    assert result.probability == pytest.approx(0.85)
    assert set(result.distribution) == set(spec.options)
    assert abs(sum(result.distribution.values()) - 1.0) < 1e-6
    assert result.metadata["constrained"] is True
    assert backend.engine.last["max_tokens"] == 16
    assert backend.engine.last["choices"] == spec.options


def test_llm_never_emits_invalid_values():
    backend = LLMBackend(engine=MockEngine("nuke it from orbit"))
    spec = DecisionSpec(type="categorical", options=["a", "b"])
    with pytest.raises(BackendError):
        backend.evaluate({"x": 1}, spec)


def test_llm_binary_yes_no_mapping():
    backend = LLMBackend(engine=MockEngine("yes", 0.7))
    spec = DecisionSpec(type="binary", statement="Is it urgent?")
    result = backend.evaluate({"x": 1}, spec)
    assert result.value == "true"
    assert set(result.distribution) == {"true", "false"}


def test_llm_ordinal_support():
    backend = LLMBackend(engine=MockEngine("high", 0.9))
    spec = DecisionSpec(type="ordinal", levels=["low", "medium", "high"])
    assert backend.supports(spec)
    assert backend.evaluate({"x": 1}, spec).value == "high"


def test_llm_no_engine_unavailable():
    backend = LLMBackend()
    with pytest.raises(BackendUnavailable):
        backend.evaluate({"x": 1}, make_spec())
    assert backend.health()["status"] == "unavailable"


def test_llm_timeout_propagates():
    class SlowEngine(LLMEngine):
        def generate(self, prompt, choices, max_tokens, timeout_s):
            raise TimeoutError("too slow", timeout_s=timeout_s)
    backend = LLMBackend(engine=SlowEngine(), timeout_s=0.1)
    with pytest.raises(TimeoutError):
        backend.evaluate({"x": 1}, make_spec())


def test_llm_case_insensitive_match():
    backend = LLMBackend(engine=MockEngine("ESCALATE", 0.6))
    spec = DecisionSpec(type="categorical", options=["escalate", "ignore"])
    assert backend.evaluate({"x": 1}, spec).value == "escalate"


# --------------------------------------------------------------------------
# Slice 36 — negotiation

def registry_of(*backends):
    reg = BackendRegistry()
    for b in backends:
        reg.register(b)
    return reg


def test_negotiate_filters_unsupported():
    reg = registry_of(FixedBackend("cat"))
    out = select_backend(DecisionSpec(type="binary", statement="s?"),
                         DecisionPolicy(), reg)
    assert out == []


def test_negotiate_privacy_filter():
    reg = registry_of(FixedBackend("remote", remote=True),
                      FixedBackend("local"))
    out = select_backend(make_spec(), DecisionPolicy(), reg)
    assert [b.name for b in out] == ["local"]
    out = select_backend(make_spec(),
                         DecisionPolicy(remote_inference=True), reg)
    assert {b.name for b in out} == {"remote", "local"}


def test_negotiate_latency_filter():
    reg = registry_of(FixedBackend("fast", latency=5.0),
                      FixedBackend("slow", latency=500.0))
    out = select_backend(make_spec(),
                         DecisionPolicy(maximum_latency_ms=50.0), reg)
    assert [b.name for b in out] == ["fast"]


def test_negotiate_cost_filter():
    reg = registry_of(FixedBackend("cheap", cost=0.0),
                      FixedBackend("pricey", cost=10.0))
    out = select_backend(make_spec(), DecisionPolicy(max_cost=1.0), reg)
    assert [b.name for b in out] == ["cheap"]


def test_negotiate_health_filter():
    reg = registry_of(FixedBackend("healthy"), FixedBackend("sick"))
    health = {"healthy": 0.95, "sick": 0.1}
    out = select_backend(make_spec(), DecisionPolicy(), reg,
                         health=health.get, min_health=0.5)
    assert [b.name for b in out] == ["healthy"]


def test_negotiate_ranking_and_determinism():
    reg = registry_of(FixedBackend("b_mid", latency=5.0),
                      FixedBackend("a_best", latency=9.0),
                      FixedBackend("c_tie", latency=5.0))
    stats = {"a_best": {"accuracy": 0.99, "calibration_error": 0.01},
             "b_mid": {"accuracy": 0.6, "calibration_error": 0.2},
             "c_tie": {"accuracy": 0.6, "calibration_error": 0.2}}
    out = select_backend(make_spec(), DecisionPolicy(), reg, stats=stats)
    names = [b.name for b in out]
    assert names[0] == "a_best"
    assert names[1:] == ["b_mid", "c_tie"]  # tie -> latency, then name
    again = select_backend(make_spec(), DecisionPolicy(), reg, stats=stats)
    assert [b.name for b in again] == names


def test_negotiate_allowed_backends_list():
    reg = registry_of(FixedBackend("one"), FixedBackend("two"))
    policy = DecisionPolicy(allowed_backends=["two"])
    out = select_backend(make_spec(), policy, reg)
    assert [b.name for b in out] == ["two"]


# --------------------------------------------------------------------------
# Slice 37 — batch inference

def test_backend_batch_default_matches_sequential():
    backend = FixedBackend("stub", prob=0.9)
    spec = make_spec()
    states = [{"i": 1}, {"i": 2}, {"i": 3}]
    batched = backend.batch(states, spec)
    sequential = [backend.evaluate(s, spec) for s in states]
    assert [(r.value, r.probability) for r in batched] == \
           [(r.value, r.probability) for r in sequential]


def test_decide_batch_matches_sequential():
    gate = HugrGate()
    gate.register(FixedBackend("stub", prob=0.9))
    spec = make_spec()
    states = [{"i": 1}, {"i": 2}, {"i": 3}]
    batched = gate.decide_batch(states, spec)
    sequential = [gate.decide(s, spec) for s in states]
    assert [(r.value, r.probability, r.backend) for r in batched] == \
           [(r.value, r.probability, r.backend) for r in sequential]


# --------------------------------------------------------------------------
# Slice 38 — cache

def cached_result():
    return DecisionResult(value="a", probability=0.9,
                          distribution={"a": 0.9, "b": 0.1},
                          backend="stub")


def test_cache_miss_then_hit():
    cache = DecisionCache()
    spec, policy = make_spec(), DecisionPolicy()
    state = {"x": 1}
    assert cache.get(state, spec, policy) is None
    assert cache.put(state, spec, policy, cached_result()) is True
    hit = cache.get(state, spec, policy)
    assert hit is not None
    assert hit.value == "a" and hit.probability == pytest.approx(0.9)
    assert cache.stats()["hits"] == 1


def test_cache_key_changes_with_state_spec_policy():
    cache = DecisionCache()
    spec, policy = make_spec(), DecisionPolicy()
    cache.put({"x": 1}, spec, policy, cached_result())
    assert cache.get({"x": 2}, spec, policy) is None  # state differs
    assert cache.get({"x": 1}, make_spec(),  # policy differs
                     DecisionPolicy(minimum_probability=0.5)) is None


def test_cache_ttl_expiry():
    cache = DecisionCache(ttl_seconds=0.05)
    spec, policy = make_spec(), DecisionPolicy()
    cache.put({"x": 1}, spec, policy, cached_result())
    assert cache.get({"x": 1}, spec, policy) is not None
    time.sleep(0.07)
    assert cache.get({"x": 1}, spec, policy) is None


def test_cache_max_size_evicts_lru():
    cache = DecisionCache(max_size=2)
    spec, policy = make_spec(), DecisionPolicy()
    cache.put({"x": 1}, spec, policy, cached_result())
    cache.put({"x": 2}, spec, policy, cached_result())
    cache.get({"x": 1}, spec, policy)  # touch -> x=2 is LRU
    cache.put({"x": 3}, spec, policy, cached_result())
    assert len(cache) == 2
    assert cache.get({"x": 2}, spec, policy) is None
    assert cache.get({"x": 1}, spec, policy) is not None


def test_cache_never_caches_strict_privacy():
    cache = DecisionCache()
    spec = make_spec()
    policy = DecisionPolicy(privacy_class="strict")
    assert cache.put({"x": 1}, spec, policy, cached_result()) is False
    assert cache.get({"x": 1}, spec, policy) is None
    assert len(cache) == 0


def test_cache_invalidate_on_model_change():
    cache = DecisionCache()
    spec, policy = make_spec(), DecisionPolicy()
    cache.put({"x": 1}, spec, policy, cached_result())
    other = cached_result()
    other.backend = "other"
    cache.put({"x": 2}, spec, policy, other)
    assert cache.invalidate_backend("stub") == 1
    assert cache.get({"x": 1}, spec, policy) is None
    assert cache.get({"x": 2}, spec, policy) is not None


def test_cache_returns_copies():
    cache = DecisionCache()
    spec, policy = make_spec(), DecisionPolicy()
    cache.put({"x": 1}, spec, policy, cached_result())
    hit = cache.get({"x": 1}, spec, policy)
    hit.probability = 0.123  # mutate the copy
    fresh = cache.get({"x": 1}, spec, policy)
    assert fresh.probability == pytest.approx(0.9)


def test_cache_key_stable():
    spec, policy = make_spec(), DecisionPolicy()
    assert cache_key({"x": 1}, spec, policy) == \
        cache_key({"x": 1}, spec, policy)


# --------------------------------------------------------------------------
# Slice 40 — privacy enforcement

def test_guard_forbidden_blocks_remote_at_selection():
    guard = PrivacyGuard(remote_inference="forbidden")
    reg = registry_of(FixedBackend("remote", remote=True),
                      FixedBackend("local"))
    out = select_backend(make_spec(), DecisionPolicy(remote_inference=True),
                         reg, privacy_guard=guard)
    assert [b.name for b in out] == ["local"]


def test_guard_check_raises_privacy_violation_on_attempt():
    guard = PrivacyGuard(remote_inference="forbidden")
    remote = FixedBackend("remote", remote=True)
    with pytest.raises(PrivacyViolation):
        guard.check_backend(remote, DecisionPolicy(remote_inference=True))


def test_guard_defers_to_policy_when_allowed():
    guard = PrivacyGuard()  # allow
    remote = FixedBackend("remote", remote=True)
    guard.check_backend(remote, DecisionPolicy(remote_inference=True))  # ok
    with pytest.raises(BackendUnavailable):
        guard.check_backend(remote, DecisionPolicy(remote_inference=False))


def test_guard_invalid_mode():
    with pytest.raises(ValueError):
        PrivacyGuard(remote_inference="sometimes")


def test_guard_redact_record():
    guard = PrivacyGuard()
    record = DecisionRecord(
        request_hash="abc", spec={}, backend="b", model="m",
        metadata={"state_keys": ["ssn"], "note": "keep"})
    redacted = guard.redact_record(record)
    assert "state_keys" not in redacted.metadata
    assert redacted.metadata["note"] == "keep"
    assert redacted.metadata["redacted"] is True
    assert record.metadata["state_keys"] == ["ssn"]  # original untouched


def test_guard_redact_state():
    guard = PrivacyGuard()
    assert guard.redact_state({"a": 1, "b": 2}) == \
        {"a": "<redacted>", "b": "<redacted>"}


def test_guard_cache_allowed():
    assert PrivacyGuard.cache_allowed(DecisionPolicy()) is True
    assert PrivacyGuard.cache_allowed(
        DecisionPolicy(privacy_class="strict")) is False


def test_ladder_strict_policy_redacts_provenance():
    strong = FixedBackend("strong", prob=0.95)
    store = ProvenanceStore()
    router = make_router(strong, provenance=store)
    router.decide({"secret": "s3cr3t"}, make_spec(),
                  DecisionPolicy(privacy_class="strict"))
    record = store.recent(1)[0]
    assert "state_keys" not in record.metadata
    assert record.metadata.get("redacted") is True
