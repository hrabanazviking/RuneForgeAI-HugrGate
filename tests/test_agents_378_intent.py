"""Slice 378 — intent routing."""

from __future__ import annotations

import pytest

from hugrgate.agents.contract import AgentContract
from hugrgate.agents.intent import IntentRoute, IntentRouter, tokenize
from hugrgate.errors import AgentContractViolation, AgentNotFound


def _router() -> IntentRouter:
    r = IntentRouter()
    r.register("summarize.text", "summarizer",
               keywords=("summarize", "summary", "tldr"))
    r.register("translate.text", "translator",
               keywords=("translate", "translation", "spanish"))
    return r


def test_tokenize_word_boundaries():
    assert tokenize("Summarize THIS, please!") == {"summarize", "this", "please"}
    assert "cat" not in tokenize("concatenate")


def test_keyword_routing_picks_best_match():
    r = _router()
    route = r.route("please summarize this document for me")
    assert isinstance(route, IntentRoute)
    assert (route.agent_id, route.intent) == ("summarizer", "summarize.text")
    assert not route.fallback
    assert 0.0 < route.confidence <= 1.0
    route = r.route("translate this to spanish")
    assert route.agent_id == "translator"


def test_no_substring_false_positives():
    r = IntentRouter()
    r.register("pets", "vet", keywords=("cat",))
    with pytest.raises(AgentNotFound):
        r.route("please concatenate these files")


def test_priority_breaks_keyword_ties_deterministically():
    r = IntentRouter()
    r.register("i", "agent-b", keywords=("go",), priority=0)
    r.register("i", "agent-a", keywords=("go",), priority=0)
    assert r.route("go").agent_id == "agent-a"  # tie -> agent_id order
    r2 = IntentRouter()
    r2.register("i", "agent-b", keywords=("go",), priority=5)
    r2.register("i", "agent-a", keywords=("go", "go2"), priority=0)
    assert r2.route("go").agent_id == "agent-b"  # priority wins


def test_intent_hint_restricts_candidates():
    r = _router()
    route = r.route("do the thing", intent_hint="translate.text")
    assert route.agent_id == "translator"


def test_fallback_agent_and_missing_fallback():
    r = _router()
    r.set_fallback("generalist")
    route = r.route("blorpy wumpus zzz")
    assert route.fallback and route.agent_id == "generalist"
    assert route.confidence == 0.0
    r2 = _router()
    with pytest.raises(AgentNotFound) as ei:
        r2.route("blorpy wumpus zzz")
    assert ei.value.code == "agent_not_found"


def test_unregister_and_reregister_replaces():
    r = _router()
    assert r.unregister("summarize.text", "summarizer") is True
    assert r.unregister("summarize.text", "summarizer") is False
    r.set_fallback("fb")
    assert r.route("summarize this").agent_id == "fb"
    r.register("summarize.text", "summarizer", keywords=("summarize",))
    r.register("summarize.text", "summarizer", keywords=("digest",))
    assert r.route("digest this").agent_id == "summarizer"
    assert "summarize.text" in r.intents()


def test_contract_checked_on_register():
    c = AgentContract(agent_id="s", intents=("summarize.text",))
    r = IntentRouter(contracts={"s": c})
    r.register("summarize.text", "s", keywords=("summarize",))
    with pytest.raises(AgentContractViolation):
        r.register("fly.plane", "s", keywords=("fly",))
    # Agents without contracts are unrestricted.
    r.register("fly.plane", "unknown-agent", keywords=("fly",))
    assert r.route("fly now").agent_id == "unknown-agent"


def test_register_validates_args():
    r = IntentRouter()
    with pytest.raises(ValueError):
        r.register("", "a")
    with pytest.raises(ValueError):
        r.register("i", "")
