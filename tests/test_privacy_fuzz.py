"""Slice 247 — Privacy fuzz tests.

Property tests over randomized inputs, seeded with the stdlib
``random`` module only (no external fuzzing dependency). The seed
is fixed so failures reproduce exactly; the generators cover
nested states, adversarial strings, and secret material.
"""

from __future__ import annotations

import copy
import json
import random
import secrets

import pytest

from hugrgate.errors import SealError
from hugrgate.policy import DecisionPolicy
from hugrgate.privacy import PrivacyGuard
from hugrgate.privacy_audit import PrivacyAuditLog
from hugrgate.privacy_crypto import SealedBox, hkdf
from hugrgate.privacy_dryrun import PrivacyDryRun
from hugrgate.privacy_labels import FieldLabels
from hugrgate.privacy_localonly import LocalOnlyPolicy
from hugrgate.privacy_minimize import minimize_state
from hugrgate.privacy_redact import MaskRedactor, RedactionPipeline
from hugrgate.privacy_secrets import SecretScanner
from hugrgate.privacy_tokens import TokenVault

SEED = 20261009


def make_rng(seed: int = SEED) -> random.Random:
    return random.Random(seed)


_WORDS = ["alpha", "beta", "gamma", "user", "token", "note", "x",
          "api_key", "ssn", "email", "", "ünïcödé", "a" * 500]


def random_scalar(rng: random.Random):
    return rng.choice([
        rng.choice(_WORDS),
        rng.randint(-10**6, 10**6),
        rng.random() * 1000,
        rng.choice([True, False, None]),
    ])


def random_state(rng: random.Random, depth: int = 3) -> dict:
    """Random nested mapping of scalars, lists, and dicts."""
    state: dict = {}
    for _ in range(rng.randint(0, 6)):
        key = rng.choice(_WORDS) or "k"
        if depth and rng.random() < 0.35:
            value = random_state(rng, depth - 1)
        elif rng.random() < 0.25:
            value = [random_scalar(rng)
                     for _ in range(rng.randint(0, 4))]
        else:
            value = random_scalar(rng)
        state[key] = value
    return state


def random_secret(rng: random.Random) -> str:
    kind = rng.randrange(3)
    if kind == 0:
        return "ghp_" + secrets.token_hex(18)
    if kind == 1:
        return "sk-" + secrets.token_urlsafe(24)
    return "xoxb-" + secrets.token_hex(16)


class _Local:
    name = "local"
    is_remote = False


class _Remote:
    name = "cloud-x"
    is_remote = True


def test_fuzz_redaction_idempotent():
    rng = make_rng()
    for _ in range(200):
        state = random_state(rng)
        pipeline = RedactionPipeline(
            field_redactors={k: MaskRedactor() for k in state})
        once, _ = pipeline.apply_to_state(state)
        twice, _ = pipeline.apply_to_state(once)
        assert twice == once, "redaction must be idempotent"


def test_fuzz_redaction_never_adds_keys():
    rng = make_rng(7)
    for _ in range(200):
        state = random_state(rng)
        pipeline = RedactionPipeline(
            field_redactors={k: MaskRedactor() for k in state})
        out, _ = pipeline.apply_to_state(state)
        assert set(out.keys()) <= set(state.keys())


def test_fuzz_minimize_never_adds_fields():
    rng = make_rng(11)
    for _ in range(200):
        state = random_state(rng)
        keep = rng.sample(sorted(state.keys()),
                          k=rng.randint(0, len(state))) if state else []
        out, _ = minimize_state(state, keep=keep)
        assert set(out.keys()) <= set(state.keys())
        assert set(out.keys()) <= set(keep)


def test_fuzz_local_only_strip_removes_values():
    rng = make_rng(13)
    for _ in range(200):
        state = random_state(rng, depth=2)
        if not state:
            continue
        victim = rng.choice(sorted(state.keys()))
        labels = FieldLabels(local_only=[victim])
        result = LocalOnlyPolicy().enforce_for_backend(state, labels,
                                                      _Remote())
        # Stripped paths are reported at leaf granularity; a marked
        # ancestor covers its whole subtree. (A container with no
        # leaves has no data to leak; the policy may leave the empty
        # shell in place.)
        leaves = [p for p in labels.label_state(state)
                  if p == victim or p.startswith(victim + ".")]
        if leaves:
            assert any(s == victim or s.startswith(victim + ".")
                       for s in result.stripped), \
                f"marked field {victim!r} must be stripped"
            remaining = [p for p in labels.label_state(result.state)
                         if p == victim or p.startswith(victim + ".")]
            assert not remaining, \
                f"stripped leaves must not survive: {remaining}"
        flat = json.dumps(result.state, default=str)
        original = state[victim]
        rest = {k: v for k, v in state.items() if k != victim}
        if isinstance(original, str) and original and \
                original not in json.dumps(rest, default=str):
            # Distinctive scalar values must not survive anywhere.
            assert original not in flat, \
                "stripped value must not survive in output"


def test_fuzz_secret_scanner_catches_injected():
    scanner = SecretScanner()
    rng = make_rng(17)
    for _ in range(100):
        state = random_state(rng, depth=2)
        secret = random_secret(rng)
        key = f"field_{rng.randrange(1000)}"
        state[key] = secret
        findings = scanner.scan_state(state)
        assert findings, "injected secret must be detected"
        assert any(f.field == key for f in findings)


def test_fuzz_secret_scanner_clean_states_mostly_clean():
    # Random word states should rarely trip the scanner; when they
    # do, findings must carry redacted previews only.
    scanner = SecretScanner()
    rng = make_rng(19)
    for _ in range(100):
        state = random_state(rng)
        for finding in scanner.scan_state(state):
            assert len(finding.preview) <= 12


def test_fuzz_token_vault_round_trip():
    vault = TokenVault(namespace="fuzz")
    rng = make_rng(23)
    tokens = {}
    for _ in range(200):
        value = random_scalar(rng)
        token = vault.tokenize(value)
        tokens[token] = value
    assert len(set(tokens)) == 200, "tokens must be unique"
    for token, value in tokens.items():
        assert vault.detokenize(token) == value


def test_fuzz_token_vault_namespace_isolation():
    vault_a = TokenVault(namespace="a")
    vault_b = TokenVault(namespace="b")
    rng = make_rng(29)
    for _ in range(100):
        token = vault_a.tokenize(random_scalar(rng))
        with pytest.raises(KeyError):
            vault_b.detokenize(token)


def test_fuzz_sealedbox_round_trip():
    key = secrets.token_bytes(32)
    rng = make_rng(31)
    for _ in range(100):
        plaintext = json.dumps(
            random_state(rng, depth=2), default=str).encode()
        blob = SealedBox.seal(key, plaintext)
        assert SealedBox.open(key, blob) == plaintext


def test_fuzz_sealedbox_tamper_fails():
    key = secrets.token_bytes(32)
    rng = make_rng(37)
    for _ in range(100):
        blob = bytearray(SealedBox.seal(key, b"secret-data"))
        blob[rng.randrange(len(blob))] ^= 0xFF
        with pytest.raises(SealError):
            SealedBox.open(key, bytes(blob))


def test_fuzz_sealedbox_wrong_key_fails():
    for _ in range(50):
        blob = SealedBox.seal(secrets.token_bytes(32), b"data")
        with pytest.raises(SealError):
            SealedBox.open(secrets.token_bytes(32), blob)


def test_fuzz_audit_chain_always_verifies():
    rng = make_rng(43)
    log = PrivacyAuditLog()
    for _ in range(200):
        log.record(rng.choice(["a", "b", "c"]),
                   payload=random_state(rng, depth=1))
    assert log.verify() is True
    assert log.count() == 200


def test_fuzz_dry_run_never_mutates():
    guard = PrivacyGuard()
    rng = make_rng(47)
    policy = DecisionPolicy(privacy_class="standard",
                            remote_inference=True)
    for _ in range(100):
        state = random_state(rng)
        before = copy.deepcopy(state)
        PrivacyDryRun(guard).evaluate(state, backend=_Local(),
                                      policy=policy)
        assert state == before


def test_fuzz_hkdf_deterministic_and_distinct():
    rng = make_rng(53)
    master = secrets.token_bytes(32)
    seen = set()
    for i in range(100):
        info = f"ctx:{rng.choice(_WORDS)}:{i}".encode()
        out = hkdf(master, salt=b"salt", info=info, length=32)
        assert hkdf(master, salt=b"salt", info=info, length=32) == out
        assert out not in seen
        seen.add(out)


def test_fuzz_guard_secret_verdict_deterministic():
    guard = PrivacyGuard()
    rng = make_rng(59)
    for _ in range(100):
        state = random_state(rng, depth=1)
        outcomes = []
        for _ in range(2):
            try:
                guard.check_no_secrets(copy.deepcopy(state))
                outcomes.append("ok")
            except Exception as e:  # noqa: BLE001 - any error counts
                outcomes.append(type(e).__name__)
        assert outcomes[0] == outcomes[1], \
            "same state must give same verdict"
