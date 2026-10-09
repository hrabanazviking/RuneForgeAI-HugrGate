"""Slice 418 — replay attack defenses.

Adversarial battery: exact replays, tampered envelopes, stale
and future timestamps, unknown key ids, and a nonce flood must
all be rejected; a well-formed first delivery must pass.
"""

from __future__ import annotations

import time

import pytest

from hugrgate.errors import ReplayDetected
from hugrgate.security.replay import (
    ReplayGuard,
    open_request,
    seal_request,
)

KEY = b"k" * 32


def test_fresh_envelope_opens():
    guard = ReplayGuard()
    env = seal_request({"action": "decide"}, KEY, "node-1")
    assert open_request(env, {"node-1": KEY}, guard) == {"action": "decide"}


def test_exact_replay_rejected():
    guard = ReplayGuard()
    env = seal_request({"action": "decide"}, KEY, "node-1")
    open_request(env, {"node-1": KEY}, guard)
    with pytest.raises(ReplayDetected, match="replay"):
        open_request(env, {"node-1": KEY}, guard)


def test_tampered_payload_rejected():
    guard = ReplayGuard()
    env = seal_request({"amount": 1}, KEY, "node-1")
    env["payload"]["amount"] = 999
    with pytest.raises(ReplayDetected, match="tag"):
        open_request(env, {"node-1": KEY}, guard)


def test_tampered_timestamp_rejected():
    guard = ReplayGuard()
    env = seal_request({"a": 1}, KEY, "node-1")
    env["timestamp"] = env["timestamp"] - 10  # backdate, tag breaks too
    with pytest.raises(ReplayDetected):
        open_request(env, {"node-1": KEY}, guard)


def test_stale_timestamp_rejected():
    guard = ReplayGuard(max_age_seconds=1)
    env = seal_request({"a": 1}, KEY, "node-1")
    time.sleep(1.05)
    with pytest.raises(ReplayDetected, match="stale"):
        open_request(env, {"node-1": KEY}, guard)


def test_future_timestamp_rejected():
    guard = ReplayGuard(max_skew_seconds=60)
    env2 = seal_request({"a": 1}, KEY, "node-1")
    # The guard layer directly: a far-future timestamp is rejected
    # even for a fresh nonce.
    with pytest.raises(ReplayDetected, match="future"):
        guard.check(env2["nonce"] + "x", time.time() + 3600)


def test_unknown_key_id_rejected():
    guard = ReplayGuard()
    env = seal_request({"a": 1}, KEY, "node-1")
    with pytest.raises(ReplayDetected, match="unknown key id"):
        open_request(env, {"node-2": KEY}, guard)


def test_wrong_key_rejected():
    guard = ReplayGuard()
    env = seal_request({"a": 1}, KEY, "node-1")
    with pytest.raises(ReplayDetected, match="tag"):
        open_request(env, {"node-1": b"z" * 32}, guard)


def test_malformed_envelope_rejected():
    guard = ReplayGuard()
    with pytest.raises(ReplayDetected, match="malformed"):
        open_request({"nope": True}, {"node-1": KEY}, guard)


def test_unauthenticated_never_pollutes_guard():
    guard = ReplayGuard()
    env = seal_request({"a": 1}, KEY, "node-1")
    env["payload"]["a"] = 2  # breaks tag; guard must not see it
    with pytest.raises(ReplayDetected):
        open_request(env, {"node-1": KEY}, guard)
    assert guard.stats()["tracked_nonces"] == 0


def test_nonce_store_bounded_under_flood():
    guard = ReplayGuard(max_entries=1000)
    for i in range(5000):
        guard.check(f"nonce-{i:06d}")
    assert guard.stats()["tracked_nonces"] == 1000


def test_expired_nonces_purged():
    guard = ReplayGuard(max_age_seconds=0.05)
    guard.check("n1")
    time.sleep(0.08)
    guard.check("n2")
    assert guard.stats()["tracked_nonces"] == 1


def test_empty_nonce_rejected():
    guard = ReplayGuard()
    with pytest.raises(ReplayDetected, match="nonce"):
        guard.check("")


def test_guard_is_thread_safe():
    import threading
    guard = ReplayGuard(max_entries=10_000)

    def worker(n: int) -> None:
        # No error swallowing: a raise in any worker leaves the
        # nonce count short and the final assertion fails.
        for i in range(200):
            guard.check(f"w{n}-{i}")

    threads = [threading.Thread(target=worker, args=(n,)) for n in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert guard.stats()["tracked_nonces"] == 1600


def test_sender_window_bounded_in_node():
    # Slice 418 hardening: the node's per-sender seq map is an LRU
    # capped at _max_senders — a sender-id flood cannot grow memory
    # without bound, and replay protection still works.
    from hugrgate.cluster.auth import ClusterKey, enable_mutual_auth
    from hugrgate.cluster.identity import NodeIdentity
    from hugrgate.cluster.node import ClusterNode
    from hugrgate.cluster.protocol import (
        ClusterMessage,
        MessageType,
        encode_message,
    )
    from hugrgate.server import build_gate
    from hugrgate.spec import DecisionSpec

    node = ClusterNode(NodeIdentity.generate("srv"), build_gate())
    key = ClusterKey.generate()
    provider = enable_mutual_auth(node, key)
    spec = DecisionSpec(type="categorical", options=["ignore", "escalate"])
    for i in range(5000):
        sender = f"{i:064x}"  # 64-char lowercase hex node id
        # Heartbeats pass through the same _check_auth seq window as
        # decide requests but do not engage load shedding.
        msg = ClusterMessage(
            msg_type=MessageType.HEARTBEAT, sender=sender, seq=1,
            trace_id="ee" * 16, payload={})
        raw = encode_message(msg)
        node.dispatch(msg, auth_tag=provider(raw), raw=raw)
    assert len(node._last_seq) <= node._max_senders
    # A legitimate sender still works after the flood.
    sender = NodeIdentity.generate().node_id
    policy = {"remote_inference": True}
    msg = ClusterMessage(
        msg_type=MessageType.DECIDE_REQUEST, sender=sender, seq=1,
        trace_id="ee" * 16,
        payload={"spec": spec.to_dict(), "state": {"text": "escalate"},
                 "policy": policy})
    raw = encode_message(msg)
    reply = node.dispatch(msg, auth_tag=provider(raw), raw=raw)
    assert reply.msg_type is MessageType.DECIDE_RESPONSE
    # ... and its replay is still rejected.
    replay = node.dispatch(msg, auth_tag=provider(raw), raw=raw)
    assert replay.payload["error"]["code"] == "cluster_auth_error"
