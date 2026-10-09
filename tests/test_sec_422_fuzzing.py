"""Slice 422 — fuzzing campaign.

Threat T-16: malformed JSON/compact encodings must raise taxonomy
errors, never crash the parsers. The campaign fuzzes the real
entry points (spec/policy/result codecs, state validation, the
security detectors) and asserts zero crashes and zero hangs.
"""

from __future__ import annotations

import json
import random

from hugrgate.security.fuzzing import (
    FuzzTarget,
    hostile_json_texts,
    hostile_states,
    hostile_values,
    run_campaign,
)
from hugrgate.security.injection_corpus import detect_sqli, sanitize_log
from hugrgate.security.prompt_injection import detect_override
from hugrgate.serde import (
    policy_from_compact,
    policy_from_dict,
    result_from_compact,
    result_from_dict,
)
from hugrgate.spec import DecisionSpec
from hugrgate.validation import validate_state

N_CASES = 400


def _dict_cases(rng: random.Random):
    value = hostile_values(rng)
    return value if isinstance(value, dict) else {"k": value}


def _seq_cases(rng: random.Random):
    value = hostile_values(rng)
    if isinstance(value, (list, tuple)):
        return value
    return [value]


def _json_to_dict(text: str):
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError as e:
        raise _ExpectedJsonError(str(e)) from e
    return parsed


class _ExpectedJsonError(Exception):
    """Malformed JSON text: an allowed, non-crash outcome."""


def test_campaign_spec_from_dict():
    target = FuzzTarget("DecisionSpec.from_dict", DecisionSpec.from_dict)
    report = run_campaign(target, _dict_cases, n_cases=N_CASES)
    assert report.unique_crashes == [], \
        [c.signature for c in report.unique_crashes]
    assert report.hangs == 0
    assert report.taxonomy_errors > 0  # the fuzzer found rejections


def test_campaign_policy_result_dict_codecs():
    for name, fn in (("policy_from_dict", policy_from_dict),
                     ("result_from_dict", result_from_dict)):
        report = run_campaign(FuzzTarget(name, fn), _dict_cases,
                              n_cases=N_CASES)
        assert report.unique_crashes == [], \
            [(name, c.signature) for c in report.unique_crashes]
        assert report.hangs == 0


def test_campaign_compact_codecs():
    for name, fn in (("policy_from_compact", policy_from_compact),
                     ("result_from_compact", result_from_compact)):
        report = run_campaign(FuzzTarget(name, fn), _seq_cases,
                              n_cases=N_CASES)
        assert report.unique_crashes == [], \
            [(name, c.signature) for c in report.unique_crashes]
        assert report.hangs == 0


def test_campaign_validate_state():
    target = FuzzTarget("validate_state", validate_state)
    report = run_campaign(target, hostile_states, n_cases=N_CASES)
    assert report.unique_crashes == [], \
        [c.signature for c in report.unique_crashes]
    assert report.hangs == 0
    assert report.taxonomy_errors > 0


def test_campaign_json_texts_through_spec():
    def parse_then_spec(text: str):
        return DecisionSpec.from_dict(_json_to_dict(text))

    target = FuzzTarget("json->spec", parse_then_spec,
                        allowed=(_ExpectedJsonError,))
    report = run_campaign(target, hostile_json_texts, n_cases=N_CASES)
    assert report.unique_crashes == [], \
        [c.signature for c in report.unique_crashes]
    assert report.hangs == 0


def _string_cases(rng: random.Random) -> str:
    value = hostile_values(rng)
    return value if isinstance(value, str) else repr(value)


def test_campaign_security_detectors_never_crash():
    for name, fn in (("detect_sqli", detect_sqli),
                     ("detect_override", detect_override),
                     ("sanitize_log", sanitize_log)):
        report = run_campaign(FuzzTarget(name, fn), _string_cases,
                              n_cases=N_CASES)
        assert report.unique_crashes == [], \
            [(name, c.signature) for c in report.unique_crashes]
        assert report.hangs == 0
