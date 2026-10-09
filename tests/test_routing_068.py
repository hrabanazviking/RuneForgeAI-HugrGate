"""Slice 068 — conditional routing DAGs."""

from __future__ import annotations

import pytest

from hugrgate import (
    Abstention,
    Backend,
    BackendRegistry,
    DecisionPolicy,
    DecisionResult,
    DecisionSpec,
    SpecError,
)
from hugrgate.ladder import LadderRung
from hugrgate.routing import (
    DAGExecutor,
    DAGNode,
    LadderRouterV2,
    RoutingDAG,
    RoutingOptions,
    evaluate_condition,
)
from hugrgate.routing.architecture import RouterContext


class DagBackend(Backend):
    def __init__(self, name, prob=0.95):
        self.name = name
        self._prob = prob
        self.calls = 0

    def capabilities(self):
        return {"spec_types": ["categorical"]}

    def supports(self, spec):
        return spec.type == "categorical"

    def evaluate(self, state, spec, context=None):
        self.calls += 1
        n = len(spec.options)
        rest = (1.0 - self._prob) / max(n - 1, 1)
        return DecisionResult(
            value="a", probability=self._prob,
            distribution={o: (self._prob if o == "a" else rest)
                          for o in spec.options},
            backend=self.name)


def reg_of(*bs):
    r = BackendRegistry()
    for b in bs:
        r.register(b)
    return r


def spec():
    return DecisionSpec(type="categorical", options=["a", "b"])


def ctx_for(state=None, options=None):
    return RouterContext.from_request(
        state or {}, spec(), DecisionPolicy(),
        options or RoutingOptions())


# -- conditions ----------------------------------------------------------------------

def test_condition_operators():
    ctx = ctx_for({"ssn": "x", "a": 1})
    assert evaluate_condition({"always": True}, ctx)
    assert not evaluate_condition({"always": False}, ctx)
    assert evaluate_condition({"key_present": "ssn"}, ctx)
    assert evaluate_condition({"key_absent": "email"}, ctx)
    assert evaluate_condition({"spec_type": "categorical"}, ctx)
    assert evaluate_condition({"qos": "standard"}, ctx)
    assert evaluate_condition({"qos_in": ["standard", "critical"]}, ctx)
    assert evaluate_condition({"min_state_keys": 2}, ctx)
    assert not evaluate_condition({"min_state_keys": 5}, ctx)
    assert evaluate_condition({"all": [{"key_present": "ssn"},
                                       {"qos": "standard"}]}, ctx)
    assert evaluate_condition({"any": [{"key_present": "nope"},
                                       {"qos": "standard"}]}, ctx)
    assert evaluate_condition({"not": {"key_present": "nope"}}, ctx)
    with pytest.raises(SpecError):
        evaluate_condition({"teleport": True}, ctx)
    with pytest.raises(SpecError):
        evaluate_condition({"a": 1, "b": 2}, ctx)
    # callables work but are not serializable
    node = DAGNode("n", "b", condition=lambda c: True)
    assert node.serializable is False
    assert DAGNode("m", "b").serializable is True


# -- graph validation -------------------------------------------------------------------

def test_cycle_and_bad_refs_rejected():
    dag = RoutingDAG()
    dag.add_node(DAGNode("a", "ba"))
    dag.add_node(DAGNode("b", "bb"))
    dag.add_edge("a", "b")
    dag.add_edge("b", "a")
    with pytest.raises(SpecError) as exc:
        dag.validate()
    assert "cycle" in str(exc.value)
    dag2 = RoutingDAG()
    dag2.add_node(DAGNode("a", "ba"))
    with pytest.raises(SpecError):
        dag2.add_edge("a", "ghost")
    with pytest.raises(SpecError):
        dag2.add_node(DAGNode("a", "ba"))  # duplicate
    with pytest.raises(SpecError):
        RoutingDAG().validate()  # empty


def test_roots():
    dag = RoutingDAG()
    for n in "abcd":
        dag.add_node(DAGNode(n, f"b{n}"))
    dag.add_edge("a", "b")
    dag.add_edge("a", "c")
    assert dag.roots() == ["a", "d"]


# -- execution -------------------------------------------------------------------------------

def test_linear_chain_executes_in_order():
    a, b, c = (DagBackend("a", 0.5), DagBackend("b", 0.99),
               DagBackend("c", 0.99))
    reg = reg_of(a, b, c)
    dag = RoutingDAG()
    for n in "abc":
        dag.add_node(DAGNode(n, n, min_confidence=0.9))
    dag.add_edge("a", "b")
    dag.add_edge("b", "c")
    router = LadderRouterV2(reg, rungs=[LadderRung("a", 0.9)],
                            executor=DAGExecutor(dag))
    won = router.decide({}, spec(), DecisionPolicy(minimum_probability=0.9))
    assert won.backend == "b"
    assert won.metadata["dag_node"] == "b"
    assert won.metadata["execution"] == "dag"
    assert c.calls == 0  # winner stops the DAG
    assert a.calls == 1 and b.calls == 1


def test_false_condition_skips_but_releases_successors():
    a = DagBackend("a", 0.99)
    b = DagBackend("b", 0.99)
    reg = reg_of(a, b)
    dag = RoutingDAG()
    dag.add_node(DAGNode("gated", "a", min_confidence=0.9,
                         condition={"key_present": "ssn"}))
    dag.add_node(DAGNode("open", "b", min_confidence=0.9))
    dag.add_edge("gated", "open")
    router = LadderRouterV2(reg, rungs=[LadderRung("a", 0.9)],
                            executor=DAGExecutor(dag))
    won = router.decide({"note": "hi"}, spec(),
                        DecisionPolicy(minimum_probability=0.9))
    assert won.backend == "b"  # gated node skipped, successor still ran
    assert a.calls == 0


def test_condition_routes_on_state_keys():
    scrub = DagBackend("scrubber", 0.99)
    plain = DagBackend("plain", 0.99)
    reg = reg_of(scrub, plain)
    dag = RoutingDAG()
    dag.add_node(DAGNode("pii", "scrubber", min_confidence=0.9,
                         condition={"key_present": "ssn"}))
    dag.add_node(DAGNode("std", "plain", min_confidence=0.9))
    dag.add_edge("pii", "std")
    router = LadderRouterV2(reg, rungs=[LadderRung("scrubber", 0.9)],
                            executor=DAGExecutor(dag))
    policy = DecisionPolicy(minimum_probability=0.9)
    won = router.decide({"ssn": "x"}, spec(), policy)
    assert won.backend == "scrubber"
    won2 = router.decide({"note": "hi"}, spec(), policy)
    assert won2.backend == "plain"


def test_diamond_runs_join_once():
    a = DagBackend("a", 0.5)
    b = DagBackend("b", 0.5)
    c = DagBackend("c", 0.5)
    d = DagBackend("d", 0.99)
    reg = reg_of(a, b, c, d)
    dag = RoutingDAG()
    for n in "abcd":
        dag.add_node(DAGNode(n, n, min_confidence=0.9))
    dag.add_edge("a", "b")
    dag.add_edge("a", "c")
    dag.add_edge("b", "d")
    dag.add_edge("c", "d")
    router = LadderRouterV2(reg, rungs=[LadderRung("a", 0.9)],
                            executor=DAGExecutor(dag))
    won = router.decide({}, spec(), DecisionPolicy(minimum_probability=0.9))
    assert won.backend == "d"
    assert d.calls == 1  # join ran exactly once


def test_exhausted_dag_abstains():
    a = DagBackend("a", 0.1)
    reg = reg_of(a)
    dag = RoutingDAG()
    dag.add_node(DAGNode("only", "a", min_confidence=0.9))
    router = LadderRouterV2(reg, rungs=[LadderRung("a", 0.9)],
                            executor=DAGExecutor(dag))
    with pytest.raises(Abstention):
        router.decide({}, spec(), DecisionPolicy(minimum_probability=0.9))


def test_executor_without_dag_raises():
    reg = reg_of(DagBackend("a", 0.99))
    router = LadderRouterV2(reg, rungs=[LadderRung("a", 0.9)],
                            executor=DAGExecutor())
    with pytest.raises(SpecError):
        router.decide({}, spec())
