"""Slice 407 — plugin trust model.

Trust levels (builtin/signed/sandboxed/denied), manifest signature
verification, entry-point allowlisting, and least-privilege
capability grants.
"""

from __future__ import annotations

import pytest

from hugrgate.errors import HugrGateError, PluginTrustError
from hugrgate.security.model_signing import ModelSigner
from hugrgate.security.plugins import (
    PluginManifest,
    PluginRegistry,
    sign_manifest,
)

KEY = b"k" * 32


def _manifest(**kw):
    base = {
        "name": "myplugin",
        "version": "1.0",
        "entry_point": "hugrgate.policy:DecisionPolicy",
    }
    base.update(kw)
    return PluginManifest(**base)


def test_denied_by_default():
    registry = PluginRegistry({"k1": KEY})
    with pytest.raises(PluginTrustError, match="denied"):
        registry.register_manifest(_manifest())


def test_signed_plugin_loads_with_valid_signature():
    registry = PluginRegistry({"k1": KEY})
    manifest = sign_manifest(_manifest(), ModelSigner(KEY, "k1"))
    assert manifest.trust == "signed"
    registry.register_manifest(manifest)
    assert registry.load("myplugin") is not None
    assert len(registry) == 1


def test_tampered_signed_manifest_rejected():
    registry = PluginRegistry({"k1": KEY})
    signed = sign_manifest(_manifest(), ModelSigner(KEY, "k1"))
    # Attacker swaps the entry point after signing.
    from dataclasses import replace
    tampered = replace(signed, entry_point="hugrgate.errors:SpecError")
    with pytest.raises(PluginTrustError):
        registry.register_manifest(tampered)


def test_signature_from_unknown_key_rejected():
    registry = PluginRegistry({"k1": KEY})
    signed = sign_manifest(_manifest(), ModelSigner(b"z" * 32, "evil"))
    with pytest.raises(PluginTrustError):
        registry.register_manifest(signed)


def test_entry_point_outside_allowlist_rejected():
    registry = PluginRegistry(
        {"k1": KEY}, allowed_prefixes=("hugrgate.",))
    # Malformed entry points never become manifests.
    with pytest.raises(ValueError, match="entry_point"):
        PluginManifest(name="x", version="1", entry_point="os:getcwd")
    manifest = sign_manifest(
        _manifest(entry_point="xml.etree:parse"),
        ModelSigner(KEY, "k1"))
    registry.register_manifest(manifest)
    with pytest.raises(PluginTrustError, match="allowlist"):
        registry.load("myplugin")


def test_sandboxed_plugin_denied_dangerous_capabilities():
    registry = PluginRegistry({"k1": KEY})
    manifest = _manifest(trust="sandboxed",
                        capabilities=frozenset({"network", "read_config"}))
    registry.register_manifest(manifest)
    with pytest.raises(PluginTrustError, match="may not claim"):
        registry.check_capability("myplugin", "network")
    registry.check_capability("myplugin", "read_config")  # benign: ok
    assert registry.granted("myplugin") == frozenset({"read_config"})


def test_undeclared_capability_denied():
    registry = PluginRegistry({"k1": KEY})
    registry.register_manifest(
        sign_manifest(_manifest(capabilities=frozenset({"read_config"})),
                      ModelSigner(KEY, "k1")))
    with pytest.raises(PluginTrustError, match="did not declare"):
        registry.check_capability("myplugin", "network")


def test_builtin_registration_requires_builtin_trust():
    registry = PluginRegistry({"k1": KEY})
    with pytest.raises(PluginTrustError, match="builtin"):
        registry.register_builtin(_manifest(trust="signed"))
    registry.register_builtin(_manifest(trust="builtin"))
    assert len(registry) == 1


def test_duplicate_registration_rejected():
    registry = PluginRegistry({"k1": KEY})
    registry.register_manifest(_manifest(trust="builtin"))
    with pytest.raises(PluginTrustError, match="already registered"):
        registry.register_manifest(_manifest(trust="builtin"))


def test_unknown_plugin_load_rejected():
    registry = PluginRegistry({"k1": KEY})
    with pytest.raises(PluginTrustError, match="unknown plugin"):
        registry.load("ghost")


def test_error_wire_round_trip():
    err = PluginTrustError("denied", plugin="x")
    rebuilt = HugrGateError.from_dict(err.to_dict())
    assert isinstance(rebuilt, PluginTrustError)
    assert rebuilt.code == "plugin_trust_error"
