"""Slice 396 — agent provenance graph."""

from __future__ import annotations

import pytest

from hugrgate.agents.provenance import AgentProvenanceGraph


def _graph():
    g = AgentProvenanceGraph()
    g.add_decision("route1", kind="route", agent_id="router",
                   ticket_id="t1")
    g.add_decision("disp1", kind="dispatch", agent_id="dispatcher",
                   ticket_id="t1", parents=("route1",))
    g.add_decision("fuse1", kind="fuse", agent_id="arbiter",
                   ticket_id="t1", parents=("disp1",),
                   details={"label": "yes"})
    g.add_decision("esc1", kind="escalate", agent_id="supervisor",
                   ticket_id="t1", parents=("fuse1",))
    # Second ticket, shared root cause node:
    g.add_decision("route2", kind="route", agent_id="router",
                   ticket_id="t2", parents=("route1",))
    return g


def test_add_and_get():
    g = _graph()
    n = g.get("fuse1")
    assert n.kind == "fuse" and n.agent_id == "arbiter"
    assert n.details == {"label": "yes"}
    assert g.get("ghost") is None
    assert len(g) == 5


def test_validation():
    g = AgentProvenanceGraph()
    g.add_decision("a", kind="route", agent_id="x", ticket_id="t")
    with pytest.raises(ValueError):
        g.add_decision("a", kind="route", agent_id="x", ticket_id="t")
    with pytest.raises(ValueError):
        g.add_decision("b", kind="x", agent_id="x", ticket_id="t",
                       parents=("ghost",))
    with pytest.raises(ValueError):
        g.add_decision("c", kind="x", agent_id="x", ticket_id="t",
                       parents=("c",))


def test_ancestors_descendants_roots():
    g = _graph()
    assert g.ancestors("esc1") == ("disp1", "fuse1", "route1")
    assert g.ancestors("route1") == ()
    assert g.descendants("route1") == ("disp1", "esc1", "fuse1", "route2")
    assert g.descendants("esc1") == ()
    assert g.roots() == ("route1",)
    with pytest.raises(ValueError):
        g.ancestors("ghost")


def test_lineage_paths():
    g = _graph()
    assert g.lineage("esc1") == (("route1", "disp1", "fuse1", "esc1"),)
    assert g.lineage("route2") == (("route1", "route2"),)
    # Diamond: two paths to the same node.
    g2 = AgentProvenanceGraph()
    g2.add_decision("r", kind="route", agent_id="a", ticket_id="t")
    g2.add_decision("b", kind="x", agent_id="a", ticket_id="t",
                    parents=("r",))
    g2.add_decision("c", kind="x", agent_id="a", ticket_id="t",
                    parents=("r",))
    g2.add_decision("d", kind="x", agent_id="a", ticket_id="t",
                    parents=("b", "c"))
    assert g2.lineage("d") == (("r", "b", "d"), ("r", "c", "d"))


def test_acyclic_and_export():
    g = _graph()
    assert g.check_acyclic() is True
    ex = g.export()
    assert [n["node_id"] for n in ex["nodes"]].index("route1") < \
        [n["node_id"] for n in ex["nodes"]].index("esc1")  # topo order
    assert ["route1", "disp1"] in ex["edges"]
    assert len(ex["edges"]) == 4
    # Wire-safe: only plain types.
    import json
    json.dumps(ex)
