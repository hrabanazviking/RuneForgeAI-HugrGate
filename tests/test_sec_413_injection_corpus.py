"""Slice 413 — injection test corpus.

Every payload in the corpus is neutralized per its context
invariant; SQLi is detected-for-rejection; prompt payloads are
recorded for slice 414's detector.
"""

from __future__ import annotations

import pytest

from hugrgate.security.injection_corpus import (
    PAYLOADS,
    detect_sqli,
    escape_ldap,
    neutralize,
    run_corpus,
    sanitize_filename,
    sanitize_log,
    shell_quote,
)


def test_corpus_covers_all_categories():
    categories = {p.category for p in PAYLOADS}
    assert {"sqli", "command", "xss", "log_forging", "path", "ldap",
            "prompt"} <= categories
    assert len(PAYLOADS) >= 25


def test_full_corpus_passes():
    results = run_corpus()
    failures = [r for r in results if not r.passed]
    assert failures == [], [
        (r.payload.text, r.payload.handling, r.output) for r in failures]


def test_every_category_passes_individually():
    for category in ("command", "xss", "log_forging", "path", "ldap"):
        results = run_corpus(category)
        assert results, category
        assert all(r.passed for r in results), category


def test_sqli_always_detected():
    results = run_corpus("sqli")
    assert results and all(r.passed for r in results)
    assert all(r.output == "<rejected>" for r in results)


def test_sqli_detector_rejects_benign():
    assert not detect_sqli("select a good restaurant nearby")
    assert not detect_sqli("the union of sets is closed")


def test_prompt_payloads_recorded_for_next_slice():
    prompts = [p for p in PAYLOADS if p.category == "prompt"]
    assert len(prompts) >= 4
    assert all(p.handling == "detect" for p in prompts)


def test_log_sanitizer_adversarial():
    assert sanitize_log("a\nb\rc\x1b[2Kd") == "a\\nb\\rcd"
    assert "\x00" not in sanitize_log("x\x00y")


def test_filename_sanitizer_adversarial():
    assert sanitize_filename("../../etc/passwd") == "etc_passwd"
    assert "/" not in sanitize_filename("/abs/path")
    assert sanitize_filename("...") == "unnamed"
    # Unicode normalization: fullwidth chars collapse safely.
    assert sanitize_filename("\uFF41\uFF42") == "ab"


def test_shell_quote_round_trips():
    evil = "a; rm -rf / $(id)"
    assert shell_quote(evil).startswith("'")
    import shlex
    assert shlex.split(shell_quote(evil)) == [evil]


def test_ldap_escape():
    assert escape_ldap("*)(uid=*") == r"\2a\29\28uid=\2a"


def test_unknown_context_rejected():
    with pytest.raises(ValueError, match="unknown sanitization context"):
        neutralize("x", "nope")


def test_double_encoding_neutralized():
    # %2e%2e%2f is inert once the filename charset applies.
    assert ".." not in sanitize_filename("%2e%2e%2fetc%2fpasswd")
    # Doubled single-quotes do not break shell quoting.
    import shlex
    q = shell_quote("it''s")
    assert shlex.split(q) == ["it''s"]
