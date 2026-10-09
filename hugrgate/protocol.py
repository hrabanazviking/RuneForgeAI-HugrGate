"""HugrGate stable wire protocol v1. Slice 426.

This module is the single source of truth for the versioned HTTP wire
protocol between HugrGate clients (Python SDK, TypeScript/Rust/Go/C
SDKs, the CLI) and the service (:mod:`hugrgate.server`).

Protocol v1 rules:

- Every ``POST /decide`` request may carry ``protocol_version``. When
  absent the request is treated as v1 (pre-version clients).
- The service accepts any ``1.x`` version with ``x >= 0`` (minor
  versions stay wire-compatible) and rejects anything else with
  :class:`~hugrgate.errors.ProtocolError` (HTTP 422).
- ``GET /protocol`` advertises the service's protocol versions, so
  clients can fail fast instead of sending doomed requests.
- :class:`Envelope` wraps responses where the caller wants explicit
  version echo; ``/decide`` keeps its legacy bare body for backward
  compatibility and adds the version inside ``metadata`` instead.

Version history:

- ``1.0`` — initial stable protocol: ``/``, ``/health``,
  ``/backends``, ``/models``, ``/decide``, ``/protocol``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from hugrgate.errors import ProtocolError

__all__ = [
    "PROTOCOL_VERSION",
    "SUPPORTED_PROTOCOL_VERSIONS",
    "Envelope",
    "build_envelope",
    "negotiate_version",
    "parse_protocol_version",
]

#: The current stable protocol version spoken by this codebase.
PROTOCOL_VERSION = "1.0"

#: All protocol versions this service accepts. Minor bumps are
#: wire-compatible with 1.0; a future 2.0 would break the envelope.
SUPPORTED_PROTOCOL_VERSIONS = ("1.0",)


def parse_protocol_version(value: Any) -> tuple[int, int]:
    """Parse ``"MAJOR.MINOR"`` into ``(major, minor)``.

    Raises :class:`~hugrgate.errors.ProtocolError` on anything that
    is not a dotted pair of non-negative integers.
    """
    if isinstance(value, str):
        parts = value.split(".")
        if len(parts) == 2 and all(p.isdigit() for p in parts):
            return int(parts[0]), int(parts[1])
    raise ProtocolError(f"malformed protocol_version: {value!r}")


def negotiate_version(requested: Any) -> str:
    """Negotiate a protocol version for a request.

    - ``None`` (field absent) → :data:`PROTOCOL_VERSION` (legacy
      clients are v1 by construction).
    - ``"1.x"`` for any ``x`` → ``"1.0"`` (minor versions are
      wire-compatible; the canonical version is echoed back).
    - anything else → :class:`~hugrgate.errors.ProtocolError`.
    """
    if requested is None:
        return PROTOCOL_VERSION
    major, _minor = parse_protocol_version(requested)
    if major == 1:
        return PROTOCOL_VERSION
    raise ProtocolError(
        f"unsupported protocol_version {requested!r}; this service speaks "
        f"{', '.join(SUPPORTED_PROTOCOL_VERSIONS)}")


@dataclass(frozen=True)
class Envelope:
    """Versioned response envelope for protocol-aware endpoints.

    ``payload`` is the endpoint's native body; the envelope adds the
    negotiated protocol version and the service's canonical version
    so clients can detect skew without a second round trip.
    """

    payload: dict[str, Any]
    protocol_version: str = PROTOCOL_VERSION
    server_version: str = field(default="")

    def to_dict(self) -> dict[str, Any]:
        from hugrgate import __version__ as service_version
        return {
            "protocol_version": self.protocol_version,
            "service_version": self.server_version or service_version,
            "payload": self.payload,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Envelope:
        try:
            return cls(
                payload=dict(data["payload"]),
                protocol_version=str(data.get("protocol_version",
                                              PROTOCOL_VERSION)),
                server_version=str(data.get("service_version", "")),
            )
        except (KeyError, TypeError, ValueError) as e:
            raise ProtocolError(f"malformed protocol envelope: {e}") from e


def build_envelope(payload: dict[str, Any],
                   protocol_version: str = PROTOCOL_VERSION) -> dict[str, Any]:
    """Build a versioned envelope dict for a native payload."""
    return Envelope(payload=payload,
                    protocol_version=protocol_version).to_dict()
