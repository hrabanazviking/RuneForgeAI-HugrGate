"""Tokenization / pseudonymization vault. Slice 233.

Reversible redaction: :class:`TokenVault` replaces sensitive values
with opaque random tokens (``hgptok_...``) and keeps the
token→value mapping in memory. Tokens reveal nothing without vault
access; only the vault holder can detokenize. This is the vault
behind :class:`~hugrgate.privacy_redact.TokenRedactor`.

Security properties (documented, tested):

- tokens are 192-bit CSPRNG outputs — unguessable, no structure to
  exploit;
- the mapping (the actual secret) never leaves the vault except via
  explicit ``export``/``import`` for encrypted persistence (slices
  241-242 seal the export);
- namespaces isolate token spaces: a token minted in one namespace
  never detokenizes in another vault;
- values are deep-copied on the way in and out, so callers cannot
  mutate vault contents through a reference.

This is pseudonymization, not anonymization: anyone holding the
vault (or its export) can reverse it. Treat the vault like a key.
"""

from __future__ import annotations

import copy
import pickle
import secrets
from collections.abc import Mapping
from typing import Any

from hugrgate.errors import DeserializationBlocked
from hugrgate.security.serde_guards import restricted_loads

__all__ = [
    "TOKEN_PREFIX",
    "TokenVault",
]

#: Token prefix — lets scanners distinguish tokens from raw values.
TOKEN_PREFIX = "hgptok_"
_TOKEN_BYTES = 24  # 192 bits


class TokenVault:
    """In-memory token→value vault for reversible pseudonymization."""

    def __init__(self, namespace: str = "default"):
        self.namespace = str(namespace)
        self._store: dict[str, Any] = {}

    def _mint(self) -> str:
        for _ in range(8):  # collision retry; 192-bit space, never hits
            token = f"{TOKEN_PREFIX}{self.namespace}_" \
                f"{secrets.token_urlsafe(_TOKEN_BYTES)}"
            if token not in self._store:
                return token
        raise RuntimeError("token collision: CSPRNG failure")  # pragma: no cover

    def tokenize(self, value: Any) -> str:
        """Replace ``value`` with an opaque token; store a deep copy."""
        token = self._mint()
        self._store[token] = copy.deepcopy(value)
        return token

    def detokenize(self, token: str) -> Any:
        """Recover the original value (deep copy).

        Raises
        ------
        KeyError
            Unknown token — including tokens from another namespace or
            vault. No partial information is returned.
        TypeError
            Not a token string at all.
        """
        if not isinstance(token, str) or \
                not token.startswith(TOKEN_PREFIX):
            raise TypeError(f"not a token: {token!r}")
        try:
            return copy.deepcopy(self._store[token])
        except KeyError:
            raise KeyError(f"unknown token: {token[:24]}…") from None

    def revoke(self, token: str) -> bool:
        """Forget one token; True when it existed."""
        if token in self._store:
            del self._store[token]
            return True
        return False

    def clear(self) -> int:
        """Forget all tokens; returns the count removed."""
        count = len(self._store)
        self._store.clear()
        return count

    def tokenize_state(self, state: Mapping[str, Any],
                       fields: list[str]) -> dict[str, Any]:
        """Return a copy of ``state`` with ``fields`` tokenized."""
        out = copy.deepcopy(dict(state))
        for field_name in fields:
            if field_name in out:
                out[field_name] = self.tokenize(out[field_name])
        return out

    def export(self) -> bytes:
        """Serialize the vault for encrypted persistence (seal me!)."""
        return pickle.dumps({"namespace": self.namespace,
                             "store": self._store})

    @classmethod
    def import_vault(cls, blob: bytes) -> TokenVault:
        """Rebuild a vault from :meth:`export` bytes.

        Slice 423: this used ``pickle.loads`` on caller-supplied
        bytes — arbitrary code execution on a hostile blob
        (found by tools/secscan.py). Now decoded through the
        deserialization allowlist, and the structure is validated.
        """
        data = restricted_loads(blob)
        if not isinstance(data, dict) or \
                not isinstance(data.get("namespace"), str) or \
                not isinstance(data.get("store"), dict):
            raise DeserializationBlocked(
                "vault blob has an unexpected structure",
                actual_type=type(data).__name__)
        vault = cls(namespace=data["namespace"])
        vault._store = data["store"]
        return vault

    def __contains__(self, token: object) -> bool:
        return isinstance(token, str) and token in self._store

    def __len__(self) -> int:
        return len(self._store)
