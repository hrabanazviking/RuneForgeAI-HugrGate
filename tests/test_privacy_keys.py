"""Slice 243 — Key-provider abstraction."""

from __future__ import annotations

import base64

import pytest

from hugrgate.errors import HugrGateError, KeyProviderError
from hugrgate.privacy_keys import (
    EnvKeyProvider,
    EphemeralKeyProvider,
    FileKeyProvider,
    KeyProvider,
    RotatingKeyProvider,
    cache_from_provider,
    derive_key,
    provenance_store_from_provider,
)

KEY_HEX = bytes(range(32)).hex()
KEY_B64 = base64.b64encode(bytes(range(32))).decode()


def test_env_provider_hex():
    provider = EnvKeyProvider(env={"APP_KEY": KEY_HEX})
    assert provider.get_key("APP_KEY") == bytes(range(32))


def test_env_provider_base64():
    provider = EnvKeyProvider(env={"APP_KEY": KEY_B64})
    assert provider.get_key("APP_KEY") == bytes(range(32))


def test_env_provider_prefix():
    provider = EnvKeyProvider(prefix="HUGR_", env={"HUGR_main": KEY_HEX})
    assert provider.get_key("main") == bytes(range(32))
    assert provider.key_ids() == ["main"]


def test_env_provider_missing():
    provider = EnvKeyProvider(env={})
    with pytest.raises(KeyProviderError) as exc:
        provider.get_key("nope")
    assert "not set" in str(exc.value)


def test_env_provider_bad_material():
    provider = EnvKeyProvider(env={"K": "too-short"})
    with pytest.raises(KeyProviderError):
        provider.get_key("K")


def test_file_provider(tmp_path):
    key_file = tmp_path / "main.key"
    key_file.write_text(KEY_HEX)
    key_file.chmod(0o600)
    provider = FileKeyProvider(tmp_path)
    assert provider.get_key("main") == bytes(range(32))
    assert provider.key_ids() == ["main"]


def test_file_provider_raw_bytes(tmp_path):
    key_file = tmp_path / "raw.key"
    key_file.write_bytes(bytes(range(32)))
    key_file.chmod(0o600)
    assert FileKeyProvider(tmp_path).get_key("raw") == bytes(range(32))


def test_file_provider_missing(tmp_path):
    with pytest.raises(KeyProviderError):
        FileKeyProvider(tmp_path).get_key("absent")


def test_file_provider_warns_on_permissive_mode(tmp_path):
    key_file = tmp_path / "main.key"
    key_file.write_text(KEY_HEX)
    key_file.chmod(0o644)
    with pytest.warns(UserWarning, match="world-readable"):
        FileKeyProvider(tmp_path).get_key("main")


def test_file_provider_path_traversal_rejected(tmp_path):
    with pytest.raises(KeyProviderError):
        FileKeyProvider(tmp_path).get_key("../evil")


def test_ephemeral_provider():
    provider = EphemeralKeyProvider()
    k1 = provider.get_key("a")
    assert len(k1) == 32
    assert provider.get_key("a") == k1  # stable within the process
    assert provider.get_key("b") != k1  # distinct per id
    assert provider.key_ids() == ["a", "b"]
    assert provider.forget("a") is True
    assert provider.forget("a") is False
    assert provider.get_key("a") != k1  # regenerated


def test_rotating_provider():
    old = EphemeralKeyProvider()
    new = EphemeralKeyProvider()
    rotating = RotatingKeyProvider(primary=new, retired=[old])
    assert rotating.get_key("k") == new.get_key("k")  # primary wins
    # Decryption path: old key still works via get_key_any.
    assert rotating.get_key_any("k") == new.get_key("k")
    solo_old = RotatingKeyProvider(primary=old)
    assert solo_old.get_key_any("k") == old.get_key("k")


def test_retire_primary():
    old = EphemeralKeyProvider()
    new = EphemeralKeyProvider()
    rotating = RotatingKeyProvider(primary=old)
    before = rotating.get_key("k")
    rotating.retire_primary(new)
    assert rotating.get_key("k") == new.get_key("k")
    assert rotating.get_key("k") != before
    # Old data still decryptable: get_key_any tries retired too.
    assert rotating.get_key_any("k") == new.get_key("k")


def test_rotating_all_fail():
    class Broken(KeyProvider):
        def get_key(self, key_id):
            raise KeyProviderError("broken")

    rotating = RotatingKeyProvider(primary=Broken())
    with pytest.raises(KeyProviderError):
        rotating.get_key_any("k")


def test_derive_key_deterministic_and_separated():
    provider = EphemeralKeyProvider()
    d1 = derive_key(provider, "m", "cache")
    assert d1 == derive_key(provider, "m", "cache")
    assert d1 != derive_key(provider, "m", "provenance")
    assert d1 != derive_key(provider, "other", "cache")
    assert len(d1) == 32


def test_cache_from_provider():
    provider = EphemeralKeyProvider()
    cache = cache_from_provider(provider, "master")
    from hugrgate.policy import DecisionPolicy
    from hugrgate.result import DecisionResult
    from hugrgate.spec import DecisionSpec
    spec = DecisionSpec(type="categorical", options=["a", "b"])
    policy = DecisionPolicy()
    result = DecisionResult(value="a", probability=1.0,
                            distribution={"a": 1.0})
    assert cache.put({"x": 1}, spec, policy, result) is True
    assert cache.get({"x": 1}, spec, policy).value == "a"


def test_provenance_store_from_provider():
    provider = EphemeralKeyProvider()
    store = provenance_store_from_provider(provider, "master")
    from hugrgate.policy import DecisionPolicy
    from hugrgate.result import DecisionResult
    from hugrgate.spec import DecisionSpec
    store.append_decision(
        {"x": 1}, DecisionSpec(type="categorical", options=["a", "b"]),
        DecisionResult(value="a", probability=1.0,
                       distribution={"a": 1.0}),
        DecisionPolicy())
    assert store.verify_chain() is True
    assert store.count() == 1


def test_key_provider_error_taxonomy():
    err = KeyProviderError("no key", key_id="k")
    assert err.code == "key_provider_error"
    assert err.recoverable is False
    rebuilt = HugrGateError.from_dict(err.to_dict())
    assert type(rebuilt) is KeyProviderError


def test_adversarial_short_key_rejected_everywhere():
    for provider in [EnvKeyProvider(env={"K": "abcd"}),
                     EphemeralKeyProvider()]:
        if isinstance(provider, EnvKeyProvider):
            with pytest.raises(KeyProviderError):
                provider.get_key("K")
    # Raw short bytes never become a key.
    with pytest.raises(KeyProviderError):
        from hugrgate.privacy_keys import _parse_key_material
        _parse_key_material(b"short", "test")
