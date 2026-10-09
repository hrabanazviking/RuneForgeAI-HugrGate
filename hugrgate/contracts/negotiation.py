"""Contract version negotiation. Gjallarbrú slice 027.

Two parties (a contract producer and consumer, client and server, two
services) each support a set of contract schema versions. This module
lets them agree on one version — and, for full sessions, on the
contract kinds they both understand — without silent downgrades.

Selection rule: among the versions every party supports, the winner
minimizes the sum of preference ranks across parties (each party lists
versions most-preferred first); ties break toward the highest version.
The rule is deterministic and symmetric — no party is privileged.

Failure is loud: disjoint version sets raise :class:`ContractError`
(``no_common_version``); disjoint kind sets raise ``no_common_kind``.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field

from hugrgate.contracts.schema import (
    SUPPORTED_SCHEMA_VERSIONS,
    is_supported_version,
)
from hugrgate.errors import ContractError

__all__ = [
    "ContractEndpoint",
    "NegotiationResult",
    "SessionAgreement",
    "VersionOffer",
    "negotiate_session",
    "negotiate_version",
    "parse_version",
]


def parse_version(version: str) -> tuple[int, ...]:
    """Parse ``"major.minor[.patch...]"`` into a comparable int tuple."""
    if not isinstance(version, str):
        raise ContractError(f"version must be a string, got {type(version).__name__}",
                            code="bad_version_type")
    parts = version.strip().split(".")
    if not parts or any(not p.isdigit() for p in parts):
        raise ContractError(f"malformed version string: {version!r}",
                            code="malformed_version")
    return tuple(int(p) for p in parts)


def _check_versions(versions: Sequence[str], *, what: str) -> tuple[str, ...]:
    vs = tuple(versions)
    if not vs:
        raise ContractError(f"{what} must list at least one version",
                            code="empty_version_list")
    if len(set(vs)) != len(vs):
        raise ContractError(f"{what} lists duplicate versions: {list(vs)}",
                            code="duplicate_versions")
    for v in vs:
        parse_version(v)  # validates shape
    return vs


@dataclass(frozen=True)
class VersionOffer:
    """One party's ordered offer: schema versions, most-preferred first."""
    party: str
    versions: tuple[str, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        if not isinstance(self.party, str) or not self.party:
            raise ContractError("offer party must be a non-empty string",
                                code="bad_offer_party")
        object.__setattr__(self, "versions",
                           _check_versions(self.versions, what=f"offer from {self.party!r}"))

    def rank_of(self, version: str) -> int:
        """Preference rank (0 = most preferred); unknown versions rank last."""
        try:
            return self.versions.index(version)
        except ValueError:
            return len(self.versions)


@dataclass(frozen=True)
class NegotiationResult:
    """The outcome of a successful version negotiation."""
    version: str
    common: tuple[str, ...]  # every mutually supported version, best first
    parties: tuple[str, ...]

    def to_dict(self) -> dict[str, object]:
        return {"version": self.version, "common": list(self.common),
                "parties": list(self.parties)}


def negotiate_version(*offers: VersionOffer) -> NegotiationResult:
    """Agree on one schema version across all ``offers``.

    The winner minimizes total preference rank; ties break to the
    highest version number. Raises ContractError when the parties share
    no version.
    """
    if not offers:
        raise ContractError("negotiation needs at least one offer",
                            code="no_offers")
    parties = tuple(o.party for o in offers)
    if len(set(parties)) != len(parties):
        raise ContractError(f"duplicate parties in negotiation: {list(parties)}",
                            code="duplicate_parties")
    common = [v for v in offers[0].versions
              if all(v in o.versions for o in offers[1:])]
    if not common:
        raise ContractError(
            "no common contract schema version: " +
            "; ".join(f"{o.party} offers {list(o.versions)}" for o in offers),
            code="no_common_version",
            offers=[{"party": o.party, "versions": list(o.versions)}
                    for o in offers])

    def score(v: str) -> tuple[int, tuple[int, ...]]:
        # Lower total rank wins; on ties the higher version wins, hence
        # the negated version tuple as the second key.
        return (sum(o.rank_of(v) for o in offers),
                tuple(-n for n in parse_version(v)))

    ordered = tuple(sorted(common, key=score))
    return NegotiationResult(version=ordered[0], common=ordered, parties=parties)


@dataclass(frozen=True)
class ContractEndpoint:
    """Everything one party brings to a contract session."""
    party: str
    schema_versions: tuple[str, ...] = field(default_factory=tuple)
    kinds: tuple[str, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        if not isinstance(self.party, str) or not self.party:
            raise ContractError("endpoint party must be a non-empty string",
                                code="bad_endpoint_party")
        object.__setattr__(self, "schema_versions",
                           _check_versions(self.schema_versions,
                                           what=f"endpoint {self.party!r}"))
        kinds = tuple(self.kinds)
        if len(set(kinds)) != len(kinds):
            raise ContractError("endpoint kinds must be unique",
                                code="duplicate_kinds")
        if any(not isinstance(k, str) or not k for k in kinds):
            raise ContractError("endpoint kinds must be non-empty strings",
                                code="bad_kind_name")
        object.__setattr__(self, "kinds", kinds)

    @classmethod
    def local(cls, kinds: Sequence[str],
              party: str = "local") -> ContractEndpoint:
        """An endpoint for this codebase: supported versions + given kinds."""
        return cls(party=party,
                   schema_versions=SUPPORTED_SCHEMA_VERSIONS,
                   kinds=tuple(kinds))

    def offer(self) -> VersionOffer:
        """This endpoint's version offer for negotiation."""
        return VersionOffer(party=self.party, versions=self.schema_versions)


@dataclass(frozen=True)
class SessionAgreement:
    """A negotiated contract session: one version, shared kinds."""
    schema_version: str
    kinds: tuple[str, ...]  # shared kinds, in client preference order
    client: str
    server: str

    def supports_kind(self, kind: str) -> bool:
        return kind in self.kinds

    def to_dict(self) -> dict[str, object]:
        return {"schema_version": self.schema_version,
                "kinds": list(self.kinds),
                "client": self.client, "server": self.server}


def negotiate_session(client: ContractEndpoint,
                      server: ContractEndpoint) -> SessionAgreement:
    """Negotiate a full contract session between client and server.

    Version via :func:`negotiate_version`; kinds are the intersection,
    ordered by client preference. Raises ContractError when either the
    versions or the kinds are disjoint.
    """
    if not isinstance(client, ContractEndpoint) or not isinstance(
            server, ContractEndpoint):
        raise ContractError("negotiate_session needs ContractEndpoints",
                            code="bad_endpoint_type")
    version = negotiate_version(client.offer(), server.offer()).version
    kinds = tuple(k for k in client.kinds if k in server.kinds)
    if not kinds:
        raise ContractError(
            f"no common contract kind between {client.party!r} "
            f"({list(client.kinds)}) and {server.party!r} "
            f"({list(server.kinds)})",
            code="no_common_kind")
    if not is_supported_version(version):
        # Negotiation may settle on a version this codebase cannot read
        # (e.g. two remote peers agreeing on 3.0). Say so explicitly.
        raise ContractError(
            f"negotiated version {version!r} is not readable by this "
            f"codebase (supports {list(SUPPORTED_SCHEMA_VERSIONS)})",
            code="negotiated_version_unreadable", version=version)
    return SessionAgreement(schema_version=version, kinds=kinds,
                            client=client.party, server=server.party)
