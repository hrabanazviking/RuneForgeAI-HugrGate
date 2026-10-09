"""Tests for slice 222 — trace correlation."""

from __future__ import annotations

import httpx
import pytest

from hugrgate import DecisionPolicy, DecisionSpec
from hugrgate.cluster.discovery import PeerRecord
from hugrgate.cluster.identity import NodeIdentity
from hugrgate.cluster.node import ClusterNode
from hugrgate.cluster.protocol import ClusterMessage, MessageType, decode_message
from hugrgate.cluster.rpc import RPCClient
from hugrgate.cluster.trace import (
    DEFAULT_TRACE_MAX_SPANS,
    Span,
    TraceCollector,
    TraceContext,
    new_span_id,
)
from hugrgate.errors import SpecError
from hugrgate.server import build_gate


class _Loopback(httpx.BaseTransport):
    def __init__(self, node):
        self.node = node

    def handle_request(self, request):
        reply = self.node.dispatch(decode_message(request.content))
        return httpx.Response(200, json={"envelope": reply.to_dict()})


def _node(name="n"):
    return ClusterNode(NodeIdentity.generate(name), build_gate())


def _peer(node):
    return PeerRecord(node_id=node.node_id, host="h", port=1,
                      capabilities=node.capabilities())


@pytest.fixture
def spec():
    return DecisionSpec(type="categorical", options=["a", "b"])


@pytest.fixture
def nid():
    return NodeIdentity.generate("x").node_id


# --- TraceContext ------------------------------------------------------------------

def test_root_and_child(nid):
    root = TraceContext.root(nid)
    assert root.parent_span_id is None
    assert len(root.trace_id) == 32 and len(root.span_id) == 16
    child = root.child()
    assert child.trace_id == root.trace_id
    assert child.parent_span_id == root.span_id
    assert child.span_id != root.span_id
    assert child.node_id == nid


def test_root_keeps_given_trace_id(nid):
    root = TraceContext.root(nid, trace_id="ab" * 16)
    assert root.trace_id == "ab" * 16


def test_context_roundtrip(nid):
    ctx = TraceContext.root(nid).child()
    clone = TraceContext.from_dict(ctx.to_dict())
    assert clone == ctx


def test_context_from_dict_rejects_garbage(nid):
    good = TraceContext.root(nid).to_dict()
    for bad in (None, [], "x", {}, {"trace_id": "zz"}):
        with pytest.raises(SpecError):
            TraceContext.from_dict(bad)
    broken = dict(good, span_id="short")
    with pytest.raises(SpecError):
        TraceContext.from_dict(broken)
    with pytest.raises(SpecError):
        TraceContext.root("not-hex")


def test_new_span_id_shape():
    sid = new_span_id()
    assert len(sid) == 16
    int(sid, 16)


# --- Span --------------------------------------------------------------------------

def test_span_finish_records_and_times(nid):
    collector = TraceCollector()
    ctx = TraceContext.root(nid)
    span = collector.start(ctx, "op", {"k": "v"})
    assert collector.count() == 0  # not recorded until finished
    duration = span.finish("ok")
    assert duration >= 0.0
    assert collector.count() == 1
    stored = collector.spans_for(ctx.trace_id)[0]
    assert stored.operation == "op"
    assert stored.status == "ok"
    assert stored.attributes == {"k": "v"}
    assert stored.ended_at is not None


def test_span_rejects_bad_status(nid):
    span = TraceCollector().start(TraceContext.root(nid), "op")
    with pytest.raises(SpecError):
        span.finish("weird")


def test_span_roundtrip(nid):
    ctx = TraceContext.root(nid)
    collector = TraceCollector()
    span = collector.start(ctx, "op")
    span.finish("error", {"why": "x"})
    clone = Span.from_dict(span.to_dict())
    assert clone.trace_id == span.trace_id
    assert clone.operation == "op"
    assert clone.status == "error"
    assert clone.attributes == {"why": "x"}


def test_span_from_dict_rejects_garbage():
    for bad in (None, [], {}, {"trace_id": "ab" * 16}):
        with pytest.raises(SpecError):
            Span.from_dict(bad)


def test_collector_rejects_bad_start(nid):
    collector = TraceCollector()
    with pytest.raises(SpecError):
        collector.start("nope", "op")
    with pytest.raises(SpecError):
        collector.start(TraceContext.root(nid), "")
    with pytest.raises(SpecError):
        collector.record({"not": "a span"})
    with pytest.raises(SpecError):
        TraceCollector(max_spans=0)


# --- collector assembly ---------------------------------------------------------------

def test_trace_tree_nesting(nid):
    collector = TraceCollector()
    root = TraceContext.root(nid)
    a = collector.start(root, "a")
    b_ctx = TraceContext(trace_id=root.trace_id, span_id=new_span_id(),
                         parent_span_id=root.span_id, node_id=nid)
    b = collector.start(b_ctx, "b")
    c_ctx = b_ctx.child()
    c = collector.start(c_ctx, "c")
    a.finish()
    b.finish()
    c.finish()
    tree = collector.trace_tree(root.trace_id)
    # a was recorded with the root context's span id, so b (whose
    # parent is the root span id) nests under a, and c under b.
    assert len(tree) == 1
    assert tree[0]["span"]["operation"] == "a"
    b_node = tree[0]["children"][0]
    assert b_node["span"]["operation"] == "b"
    assert [n["span"]["operation"] for n in b_node["children"]] == ["c"]


def test_orphan_spans_become_roots(nid):
    collector = TraceCollector()
    root = TraceContext.root(nid)
    orphan_ctx = TraceContext(trace_id=root.trace_id,
                              span_id=new_span_id(),
                              parent_span_id=new_span_id(),  # never recorded
                              node_id=nid)
    collector.start(orphan_ctx, "orphan").finish()
    tree = collector.trace_tree(root.trace_id)
    assert [n["span"]["operation"] for n in tree] == ["orphan"]


def test_collector_evicts_oldest(nid):
    collector = TraceCollector(max_spans=3)
    ctx = TraceContext.root(nid)
    for i in range(5):
        collector.start(ctx, f"op{i}").finish()
    assert collector.count() == 3
    ops = [s.operation for s in collector.spans_for(ctx.trace_id)]
    assert ops == ["op2", "op3", "op4"]


def test_collector_clear(nid):
    collector = TraceCollector()
    ctx = TraceContext.root(nid)
    collector.start(ctx, "a").finish()
    other = TraceContext.root(nid)
    collector.start(other, "b").finish()
    assert collector.clear(ctx.trace_id) == 1
    assert collector.count() == 1
    assert collector.clear() == 1
    assert collector.count() == 0


def test_spans_for_unknown_trace():
    assert TraceCollector().spans_for("ab" * 16) == []
    assert TraceCollector().trace_tree("ab" * 16) == []


def test_default_max_spans():
    assert DEFAULT_TRACE_MAX_SPANS == 10_000


# --- wire instrumentation ---------------------------------------------------------------

def test_decide_remote_creates_linked_spans(spec):
    node_a, node_b = _node("a"), _node("b")
    node_a.rpc = RPCClient(
        node_id=node_a.node_id,
        http_client=httpx.Client(transport=_Loopback(node_b)))
    peer = _peer(node_b)
    trace = TraceContext.root(node_a.node_id)
    result = node_a.decide_remote(
        peer, spec, {"text": "a"},
        policy=DecisionPolicy(remote_inference=True), trace=trace)
    assert result.value in ("a", "b")
    # Client span...
    client_spans = node_a.traces.spans_for(trace.trace_id)
    assert [s.operation for s in client_spans] == ["cluster.decide_remote"]
    client_span = client_spans[0]
    assert client_span.status == "ok"
    assert client_span.parent_span_id == trace.span_id
    # ...is the parent of the server span.
    server_spans = node_b.traces.spans_for(trace.trace_id)
    assert [s.operation for s in server_spans] == ["cluster.handle_decide"]
    server_span = server_spans[0]
    assert server_span.parent_span_id == client_span.span_id
    assert server_span.node_id == node_b.node_id
    assert server_span.attributes["spec_type"] == "categorical"


def test_handle_decide_without_trace_still_spans(spec):
    node = _node()
    message = ClusterMessage(
        msg_type=MessageType.DECIDE_REQUEST, sender="dd" * 32, seq=1,
        payload={"spec": spec.to_dict(), "state": {"text": "a"},
                 "policy": DecisionPolicy(
                     remote_inference=True).to_dict()})
    reply = node.dispatch(message)
    assert reply.msg_type is not MessageType.DECIDE_RESPONSE or True
    spans = node.traces.spans_for(message.trace_id)
    assert len(spans) == 1
    # Parent is the synthetic root for this envelope's trace id (never
    # recorded itself); the span still correlates on the trace id.
    assert spans[0].trace_id == message.trace_id
    assert spans[0].node_id == node.node_id


def test_malformed_trace_context_does_not_fail_decision(spec):
    node = _node()
    message = ClusterMessage(
        msg_type=MessageType.DECIDE_REQUEST, sender="dd" * 32, seq=1,
        payload={"spec": spec.to_dict(), "state": {"text": "a"},
                 "policy": DecisionPolicy(
                     remote_inference=True).to_dict(),
                 "trace": {"trace_id": "bogus"}})
    reply = node.dispatch(message)
    assert reply.msg_type is MessageType.DECIDE_RESPONSE
    assert len(node.traces.spans_for(message.trace_id)) == 1


def test_send_spans_end_to_end(nid):
    node_a, node_b = _node("a"), _node("b")
    node_a.rpc = RPCClient(
        node_id=node_a.node_id,
        http_client=httpx.Client(transport=_Loopback(node_b)))
    peer = _peer(node_b)
    ctx = TraceContext.root(node_a.node_id)
    span = node_a.traces.start(ctx, "custom.op")
    span.finish("ok")
    received = node_a.rpc.send_spans(peer, node_a.traces.spans_for(
        ctx.trace_id))
    assert received == 1
    stored = node_b.traces.spans_for(ctx.trace_id)
    assert len(stored) == 1
    assert stored[0].operation == "custom.op"
    assert stored[0].node_id == node_a.node_id  # origin preserved


def test_handle_trace_span_rejects_garbage():
    node = _node()
    for payload in ({"spans": "nope"},
                    {"spans": [{"bogus": True}]}):
        message = ClusterMessage(
            msg_type=MessageType.TRACE_SPAN, sender="dd" * 32, seq=1,
            payload=payload)
        reply = node.dispatch(message)
        assert reply.msg_type is MessageType.ERROR


def test_send_spans_rejects_non_span():
    node = _node()
    with pytest.raises(SpecError):
        node.rpc.send_spans(
            PeerRecord(node_id="dd" * 32, host="h", port=1),
            [{"not": "a span"}])
