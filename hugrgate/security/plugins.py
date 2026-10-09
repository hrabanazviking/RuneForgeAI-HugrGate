"""Plugin trust model. Slice 407.

``BackendRegistry.register`` accepts arbitrary ``Backend`` objects —
today there is no distinction between a shipped backend and a
third-party module with the same interface (threat T-15). This module
adds that distinction without changing the registry:

- trust levels: ``builtin`` (shipped with HugrGate), ``signed``
  (manifest signature verifies against the operator keyring),
  ``sandboxed`` (may load but only under a sandbox policy, slice
  408); anything else is denied by default;
- :class:`PluginManifest` — name, version, dotted entry point,
  declared capabilities, and a signature envelope
  (:class:`SignedMetadata`, slice 405) for the ``signed`` level;
- :class:`PluginRegistry` — ``register_manifest`` verifies before
  trusting; ``load`` imports the entry point only from allowlisted
  module prefixes; ``check_capability`` enforces least privilege.

Dangerous capabilities (``network``, ``subprocess``,
``filesystem_write``) are never granted to ``sandboxed`` plugins
and must be explicitly declared even by ``signed`` ones.
"""

from __future__ import annotations

import importlib
import re
from dataclasses import dataclass
from typing import Any

from hugrgate.errors import PluginTrustError, SignatureVerificationFailed
from hugrgate.security.model_signing import ModelSigner, SignedMetadata

__all__ = [
    "BUILTIN_PREFIXES",
    "DANGEROUS_CAPABILITIES",
    "TRUST_LEVELS",
    "PluginManifest",
    "PluginRegistry",
]

#: Trust levels, weakest to strongest.
TRUST_LEVELS = ("denied", "sandboxed", "signed", "builtin")

#: Capabilities that imply real-world effects.
DANGEROUS_CAPABILITIES = frozenset(
    {"network", "subprocess", "filesystem_write"})

#: Entry points may only live under these module prefixes.
BUILTIN_PREFIXES = ("hugrgate.",)

_ENTRY_POINT = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*(\.[A-Za-z_][A-Za-z0-9_]*)+"
                          r":[A-Za-z_][A-Za-z0-9_]*$")


@dataclass(frozen=True)
class PluginManifest:
    """A plugin's identity, code location, and claimed capabilities."""

    name: str
    version: str
    entry_point: str  # "package.module:Attribute"
    trust: str = "denied"
    capabilities: frozenset[str] = frozenset()
    signature: SignedMetadata | None = None

    def __post_init__(self) -> None:
        if self.trust not in TRUST_LEVELS:
            raise ValueError(f"unknown trust level {self.trust!r}")
        if not _ENTRY_POINT.match(self.entry_point):
            raise ValueError(
                f"entry_point must look like 'pkg.mod:Attr', got "
                f"{self.entry_point!r}")

    def payload(self) -> dict[str, Any]:
        """The signed payload: everything the signature covers."""
        return {
            "name": self.name,
            "version": self.version,
            "entry_point": self.entry_point,
            "trust": self.trust,
            "capabilities": sorted(self.capabilities),
        }


def sign_manifest(manifest: PluginManifest,
                  signer: ModelSigner) -> PluginManifest:
    """Return a copy of ``manifest`` with a signature over its payload.

    The signature covers the *final* trust level (``"denied"`` is
    upgraded to ``"signed"`` before signing), so verification
    compares like with like.
    """
    from dataclasses import replace
    final_trust = "signed" if manifest.trust == "denied" else manifest.trust
    staged = replace(manifest, trust=final_trust)
    return replace(staged, signature=signer.sign(staged.payload()))


def _verify_payload(signature: SignedMetadata,
                    keys: dict[str, bytes]) -> dict[str, Any]:
    """Verify an envelope against a keyring (any key may be the signer)."""
    first_id = next(iter(keys))
    return ModelSigner(keys[first_id], first_id).verify(signature, keys)


class PluginRegistry:
    """Verify-before-trust registry for third-party plugins."""

    def __init__(self, keys: dict[str, bytes] | None = None,
                 allowed_prefixes: tuple[str, ...] = BUILTIN_PREFIXES,
                 ) -> None:
        self._keys = dict(keys or {})
        self._allowed_prefixes = allowed_prefixes
        self._manifests: dict[str, PluginManifest] = {}
        self._loaded: dict[str, Any] = {}

    # -- registration ----------------------------------------------------

    def register_manifest(self, manifest: PluginManifest) -> None:
        """Verify the manifest's trust claim before accepting it."""
        if manifest.name in self._manifests:
            raise PluginTrustError(
                f"plugin {manifest.name!r} is already registered",
                plugin=manifest.name)
        if manifest.trust == "signed":
            if manifest.signature is None:
                raise PluginTrustError(
                    f"signed plugin {manifest.name!r} has no signature",
                    plugin=manifest.name)
            if not self._keys:
                raise PluginTrustError(
                    "no verification keys configured for signed plugins",
                    plugin=manifest.name)
            payload = self._verify_envelope(manifest)
            if payload != manifest.payload():
                raise PluginTrustError(
                    f"signed payload mismatch for {manifest.name!r}",
                    plugin=manifest.name)
        elif manifest.trust == "denied":
            raise PluginTrustError(
                f"plugin {manifest.name!r} has trust level 'denied'",
                plugin=manifest.name)
        self._manifests[manifest.name] = manifest

    def register_builtin(self, manifest: PluginManifest) -> None:
        """Register a shipped plugin; must claim ``builtin`` trust."""
        if manifest.trust != "builtin":
            raise PluginTrustError(
                f"builtin registration requires trust='builtin', got "
                f"{manifest.trust!r}", plugin=manifest.name)
        self.register_manifest(manifest)

    def _verify_envelope(self, manifest: PluginManifest) -> dict[str, Any]:
        """Verify the manifest signature; all failures are trust errors."""
        assert manifest.signature is not None
        try:
            return _verify_payload(manifest.signature, self._keys)
        except SignatureVerificationFailed as e:
            raise PluginTrustError(
                f"signed plugin {manifest.name!r} failed verification: "
                f"{e.message}", plugin=manifest.name) from e

    # -- loading ----------------------------------------------------------

    def _check_entry_point(self, manifest: PluginManifest) -> None:
        module_path = manifest.entry_point.split(":")[0]
        if not module_path.startswith(self._allowed_prefixes):
            raise PluginTrustError(
                f"entry point {manifest.entry_point!r} escapes the "
                f"module allowlist {self._allowed_prefixes}",
                plugin=manifest.name)

    def load(self, name: str) -> Any:
        """Import and return the plugin's entry point object."""
        if name in self._loaded:
            return self._loaded[name]
        manifest = self._manifests.get(name)
        if manifest is None:
            raise PluginTrustError(f"unknown plugin {name!r}", plugin=name)
        self._check_entry_point(manifest)
        module_path, attr = manifest.entry_point.split(":")
        try:
            module = importlib.import_module(module_path)
            obj = getattr(module, attr)
        except (ImportError, AttributeError) as e:
            raise PluginTrustError(
                f"cannot load entry point {manifest.entry_point!r}: {e}",
                plugin=name) from e
        self._loaded[name] = obj
        return obj

    # -- capabilities -------------------------------------------------------

    def check_capability(self, name: str, capability: str) -> None:
        """Raise unless ``name``'s trust level grants ``capability``."""
        manifest = self._manifests.get(name)
        if manifest is None:
            raise PluginTrustError(f"unknown plugin {name!r}", plugin=name)
        if manifest.trust == "sandboxed" and \
                capability in DANGEROUS_CAPABILITIES:
            raise PluginTrustError(
                f"sandboxed plugin {name!r} may not claim "
                f"{capability!r}", plugin=name, capability=capability)
        if capability not in manifest.capabilities:
            raise PluginTrustError(
                f"plugin {name!r} did not declare capability "
                f"{capability!r}", plugin=name, capability=capability)

    def granted(self, name: str) -> frozenset[str]:
        manifest = self._manifests.get(name)
        if manifest is None:
            raise PluginTrustError(f"unknown plugin {name!r}", plugin=name)
        if manifest.trust == "sandboxed":
            return manifest.capabilities - DANGEROUS_CAPABILITIES
        return manifest.capabilities

    def __len__(self) -> int:
        return len(self._manifests)
