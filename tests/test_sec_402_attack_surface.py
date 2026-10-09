"""Slice 402 — attack-surface inventory.

The inventory is code-derived: enumeration comes from the AST of the
live source, and the gate test fails if the curated registry drifts
from it.
"""

from __future__ import annotations

import pytest

from hugrgate.security.attack_surface import (
    AttackSurface,
    SurfaceEntry,
    curated_surface,
    enumerate_surface,
    find_unlisted,
)


def test_inventory_has_no_drift():
    """Every code-derived entry must be in the curated registry."""
    assert find_unlisted(curated_surface()) == {}


def test_enumeration_finds_decide_endpoint():
    derived = enumerate_surface()
    assert "POST /decide" in derived["api_endpoint"]
    assert "GET /health" in derived["api_endpoint"]


def test_enumeration_finds_all_cli_commands():
    derived = enumerate_surface()
    assert set(derived["cli_command"]) == {
        "decide", "backends", "models", "health",
        "serve", "bench", "report",
        "check-backend", "check-contract", "completion", "doctor",
        "gen", "init", "inspect", "new", "openapi", "plugins",
    }


def test_hot_surface_is_explicit():
    surface = curated_surface()
    hot = {(e.kind, e.name) for e in surface.unauthenticated()
           if e.risk == "high"}
    assert ("api_endpoint", "POST /decide") in hot
    assert ("plugin_loader", "BackendRegistry.register") in hot


def test_drift_detected_when_entry_missing():
    surface = curated_surface()
    pruned = AttackSurface(entries=[
        e for e in surface.entries
        if not (e.kind == "api_endpoint" and e.name == "POST /decide")
    ])
    drift = find_unlisted(pruned)
    assert drift == {"api_endpoint": ["POST /decide"]}


def test_duplicate_entry_rejected():
    surface = AttackSurface()
    entry = SurfaceEntry("x", "api_endpoint", "d", False, "low")
    surface.add(entry)
    with pytest.raises(ValueError, match="duplicate"):
        surface.add(entry)


def test_bad_kind_and_risk_rejected():
    with pytest.raises(ValueError, match="kind"):
        SurfaceEntry("x", "nope", "d", False, "low")
    with pytest.raises(ValueError, match="risk"):
        SurfaceEntry("x", "api_endpoint", "d", False, "extreme")


def test_round_trip():
    surface = curated_surface()
    clone = AttackSurface.from_dict(surface.to_dict())
    assert len(clone.entries) == len(surface.entries)
    assert clone.names("cli_command") == surface.names("cli_command")


def test_every_entry_has_description():
    for entry in curated_surface().entries:
        assert entry.description.strip(), entry.name
