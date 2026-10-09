"""Tests for slice 201 — node protocol design."""

from __future__ import annotations

import json

import pytest

from hugrgate.cluster.protocol import (
    CLUSTER_RPC_PATH,
    MAX_MESSAGE_BYTES,
    PROTOCOL_VERSION,
    ClusterMessage,
    MessageType,
    decode_message,
    encode_message,
    new_trace_id,
)
from hugrgate.errors import SpecError

SENDER = "ab" * 32
TRACE = "cd" * 16


def _msg(**kw):
    base = {"msg_type": MessageType.HEARTBEAT, "sender": SENDER, "seq": 7,
            "trace_id": TRACE}
    base.update(kw)
    return ClusterMessage(**base)


# --- success ---------------------------------------------------------------

def test_round_trip_preserves_everything():
    msg = _msg(payload={"load": 0.5}, timestamp=1728470000.5)
    back = decode_message(encode_message(msg))
    assert back.to_dict() == msg.to_dict()
    assert back.message_id == f"{SENDER}:7"


def test_encode_is_compact_sorted_json():
    raw = encode_message(_msg(payload={"b": 1, "a": 2}))
    parsed = json.loads(raw)
    assert list(parsed["payload"]) == ["a", "b"]
    assert b" " not in raw and b"\n" not in raw
    assert parsed["protocol_version"] == PROTOCOL_VERSION


def test_new_trace_id_shape():
    tid = new_trace_id()
    assert len(tid) == 32 and all(c in "0123456789abcdef" for c in tid)
    assert new_trace_id() != tid


def test_all_message_types_have_stable_wire_values():
    values = [t.value for t in MessageType]
    assert len(values) == len(set(values))
    assert all(isinstance(v, str) and v for v in values)
    assert CLUSTER_RPC_PATH == "/cluster/rpc"


def test_accepts_current_protocol_version_explicitly():
    d = _msg().to_dict()
    assert ClusterMessage.from_dict(d).protocol_version == PROTOCOL_VERSION


# --- failure -----------------------------------------------------------------

def test_rejects_newer_protocol_version():
    d = _msg().to_dict()
    d["protocol_version"] = PROTOCOL_VERSION + 1
    with pytest.raises(SpecError, match="newer than supported"):
        ClusterMessage.from_dict(d)


def test_rejects_unknown_message_type():
    d = _msg().to_dict()
    d["msg_type"] = "teleport"
    with pytest.raises(SpecError, match="unknown message type"):
        ClusterMessage.from_dict(d)


def test_rejects_non_dict_envelope():
    with pytest.raises(SpecError):
        ClusterMessage.from_dict([1, 2, 3])


def test_rejects_garbage_bytes():
    with pytest.raises(SpecError, match="not valid JSON"):
        decode_message(b"\xff\xfe not json")


def test_rejects_bad_sender():
    with pytest.raises(SpecError, match="sender"):
        _msg(sender="too-short")
    with pytest.raises(SpecError, match="sender"):
        _msg(sender="ZZ" * 32)


def test_rejects_bad_seq_and_trace():
    with pytest.raises(SpecError, match="seq"):
        _msg(seq=-1)
    with pytest.raises(SpecError, match="trace_id"):
        _msg(trace_id="nope")


def test_constructor_rejects_non_message_type():
    with pytest.raises(SpecError, match="msg_type"):
        _msg(msg_type="heartbeat")  # raw string, not the enum


# --- boundary ----------------------------------------------------------------

def test_encode_rejects_oversized_envelope():
    big = "x" * (MAX_MESSAGE_BYTES + 1)
    with pytest.raises(SpecError, match="over the"):
        encode_message(_msg(payload={"blob": big}))


def test_decode_rejects_oversized_bytes_without_parsing():
    with pytest.raises(SpecError, match="over the"):
        decode_message(b" " * (MAX_MESSAGE_BYTES + 1))


def test_decode_accepts_str_input():
    text = encode_message(_msg()).decode("utf-8")
    assert decode_message(text).sender == SENDER


def test_seq_zero_is_valid():
    assert _msg(seq=0).seq == 0
