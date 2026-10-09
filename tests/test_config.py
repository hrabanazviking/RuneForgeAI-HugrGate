"""Slice 008 — configuration normalization.

Configs validate on construction, serialize losslessly, and reject
unknown keys loudly: a misspelled key must never silently fall back
to its default.
"""

from __future__ import annotations

import pytest

from hugrgate import DecisionPolicy
from hugrgate.bench import BenchmarkConfig
from hugrgate.client import policy_from_dict, policy_to_dict
from hugrgate.daemon import DaemonConfig
from hugrgate.errors import PolicyError, SpecError
from hugrgate.spec import DecisionSpec

# --- DecisionPolicy ------------------------------------------------------------

def test_policy_rejects_unknown_privacy_class():
    with pytest.raises(PolicyError, match="unknown privacy_class"):
        DecisionPolicy(privacy_class="stirct")  # typo must not -> "standard"


def test_policy_rejects_bad_privacy_class_loudly_not_silently():
    with pytest.raises(PolicyError):
        DecisionPolicy(privacy_class="paranoid")


def test_policy_validates_ranges():
    with pytest.raises(PolicyError, match="maximum_latency_ms"):
        DecisionPolicy(maximum_latency_ms=0)
    with pytest.raises(PolicyError, match="maximum_latency_ms"):
        DecisionPolicy(maximum_latency_ms=-5)
    with pytest.raises(PolicyError, match="max_cost"):
        DecisionPolicy(max_cost=-1.0)
    # valid boundaries are accepted
    DecisionPolicy(maximum_latency_ms=0.5, max_cost=0.0,
                   privacy_class="strict")


def test_policy_round_trip():
    policy = DecisionPolicy(
        minimum_probability=0.8, maximum_latency_ms=120.0,
        remote_inference=True, allowed_backends=["rules"],
        preferred_backends=["rules"], fallback_behavior="escalate",
        privacy_class="strict", max_cost=2.5, review_band=(0.5, 0.8))
    rebuilt = policy_from_dict(policy_to_dict(policy))
    assert rebuilt == policy


def test_policy_from_dict_rejects_unknown_keys():
    with pytest.raises(PolicyError, match="unknown policy key"):
        policy_from_dict({"minimum_probablity": 0.9})  # typo


def test_policy_from_dict_rejects_unknown_keys_even_with_valid_ones():
    with pytest.raises(PolicyError, match="bogus"):
        policy_from_dict({"minimum_probability": 0.5, "bogus": 1})


# --- DecisionSpec -----------------------------------------------------------------

def test_spec_from_dict_rejects_unknown_keys():
    with pytest.raises(SpecError, match="unknown spec key"):
        DecisionSpec.from_dict({
            "type": "categorical",
            "options": ["a", "b"],
            "optoins": ["a", "b"],  # typo
        })


def test_spec_round_trip():
    spec = DecisionSpec(type="ordinal", levels=["low", "high"],
                        metadata={"k": "v"})
    assert DecisionSpec.from_dict(spec.to_dict()) == spec


# --- DaemonConfig -------------------------------------------------------------------

def test_daemon_config_rejects_bad_values():
    with pytest.raises(ValueError, match="port"):
        DaemonConfig(port=0)
    with pytest.raises(ValueError, match="port"):
        DaemonConfig(port=70000)
    with pytest.raises(ValueError, match="batch_window_ms"):
        DaemonConfig(batch_window_ms=0)
    with pytest.raises(ValueError, match="max_batch"):
        DaemonConfig(max_batch=0)
    with pytest.raises(ValueError, match="max_queue"):
        DaemonConfig(max_queue=-1)
    with pytest.raises(ValueError, match="drain_timeout_s"):
        DaemonConfig(drain_timeout_s=-0.5)
    with pytest.raises(ValueError, match="client_id_header"):
        DaemonConfig(client_id_header="  ")


def test_daemon_config_round_trip():
    cfg = DaemonConfig(port=9999, unix_socket="/tmp/hg.sock",
                       client_policies_path="/tmp/p.json")
    rebuilt = DaemonConfig.from_dict(cfg.to_dict())
    assert rebuilt == cfg


def test_daemon_config_from_dict_rejects_unknown_keys():
    with pytest.raises(ValueError, match="unknown daemon config key"):
        DaemonConfig.from_dict({"prt": 8377})  # typo


def test_daemon_config_defaults_are_valid():
    DaemonConfig()  # must not raise


# --- BenchmarkConfig ------------------------------------------------------------------

def test_benchmark_config_round_trip():
    cfg = BenchmarkConfig(backends=["rules"], max_items=10)
    assert cfg.backends == ["rules"] and cfg.max_items == 10


# --- failure / boundary ---------------------------------------------------------------

def test_policy_from_dict_empty_is_default():
    assert policy_from_dict({}) == DecisionPolicy()


def test_spec_from_dict_missing_type_raises_spec_error():
    # Slice 422 (T-16): a missing "type" used to escape as KeyError
    # (fuzz-found); missing required keys are SpecErrors now.
    with pytest.raises(SpecError, match="missing required key 'type'"):
        DecisionSpec.from_dict({"options": ["a", "b"]})
