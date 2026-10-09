"""Slice 233 — Tokenization / pseudonymization."""

from __future__ import annotations

import pytest

from hugrgate.privacy_redact import RedactionPipeline, TokenRedactor
from hugrgate.privacy_tokens import TOKEN_PREFIX, TokenVault


def test_tokenize_detokenize_round_trip():
    vault = TokenVault()
    token = vault.tokenize("secret-value")
    assert token.startswith(TOKEN_PREFIX)
    assert token != "secret-value"
    assert vault.detokenize(token) == "secret-value"


def test_tokens_are_opaque_and_unique():
    vault = TokenVault()
    t1 = vault.tokenize("same")
    t2 = vault.tokenize("same")
    assert t1 != t2
    assert "same" not in t1 and "same" not in t2


def test_non_string_values():
    vault = TokenVault()
    token = vault.tokenize({"nested": [1, 2, 3]})
    assert vault.detokenize(token) == {"nested": [1, 2, 3]}


def test_unknown_token_raises_keyerror():
    vault = TokenVault()
    with pytest.raises(KeyError):
        vault.detokenize(f"{TOKEN_PREFIX}default_nonexistent")


def test_non_token_raises_typeerror():
    vault = TokenVault()
    with pytest.raises(TypeError):
        vault.detokenize("plain-string")
    with pytest.raises(TypeError):
        vault.detokenize(12345)


def test_namespace_isolation():
    a = TokenVault(namespace="a")
    b = TokenVault(namespace="b")
    token = a.tokenize("x")
    assert token not in b
    with pytest.raises(KeyError):
        b.detokenize(token)


def test_revoke():
    vault = TokenVault()
    token = vault.tokenize("x")
    assert vault.revoke(token) is True
    assert vault.revoke(token) is False
    with pytest.raises(KeyError):
        vault.detokenize(token)


def test_clear():
    vault = TokenVault()
    vault.tokenize("a")
    vault.tokenize("b")
    assert vault.clear() == 2
    assert len(vault) == 0


def test_deep_copy_isolation():
    vault = TokenVault()
    original = {"k": [1]}
    token = vault.tokenize(original)
    original["k"].append(999)  # mutate after tokenizing
    assert vault.detokenize(token) == {"k": [1]}
    out = vault.detokenize(token)
    out["k"].append(999)  # mutate the returned copy
    assert vault.detokenize(token) == {"k": [1]}


def test_tokenize_state():
    vault = TokenVault()
    state = {"ssn": "123", "name": "n"}
    out = vault.tokenize_state(state, ["ssn"])
    assert out["name"] == "n"
    assert out["ssn"].startswith(TOKEN_PREFIX)
    assert vault.detokenize(out["ssn"]) == "123"
    assert state["ssn"] == "123"  # input untouched


def test_export_import_round_trip():
    vault = TokenVault(namespace="prod")
    token = vault.tokenize("secret")
    blob = vault.export()
    assert isinstance(blob, bytes)
    rebuilt = TokenVault.import_vault(blob)
    assert rebuilt.namespace == "prod"
    assert rebuilt.detokenize(token) == "secret"


def test_redactor_integration():
    vault = TokenVault()
    pipeline = RedactionPipeline(
        field_redactors={"ssn": TokenRedactor(vault)})
    state = {"ssn": "123-45-6789", "name": "n"}
    out, applied = pipeline.apply_to_state(state)
    assert out["ssn"].startswith(TOKEN_PREFIX)
    assert vault.detokenize(out["ssn"]) == "123-45-6789"
    assert applied == [("ssn", "token")]


def test_adversarial_token_guessing():
    # Tokens carry no structure: truncating or flipping characters
    # yields unknown tokens, never another valid one.
    vault = TokenVault()
    token = vault.tokenize("x")
    tampered = token[:-2] + ("ab" if not token.endswith("ab") else "cd")
    with pytest.raises(KeyError):
        vault.detokenize(tampered)


def test_adversarial_cross_vault_replay():
    # A token exfiltrated from one vault is useless in another, even
    # with the same namespace.
    a = TokenVault(namespace="shared")
    b = TokenVault(namespace="shared")
    token = a.tokenize("x")
    with pytest.raises(KeyError):
        b.detokenize(token)
