"""Developer-facing compatibility helpers. Gjallarbrú slice 444.

Three migrations developers actually face, each with a function and
a prose guide in ``docs/migration.md``:

1. **v1 client → SDK v2** (:func:`upgrade_client`): rebuilds a
   :class:`~hugrgate.client.HugrGateClient` as a
   :class:`~hugrgate.sdk.HugrGateSDK` with identical transport
   settings. v1 is untouched and keeps working; v2 is a strict
   superset (context manager, retries, batch, versioned
   User-Agent).
2. **contract schema v1 → v2** (:func:`migrate_contract`): upgrades
   a v1 contract/spec dict through
   :func:`hugrgate.contracts.migration.migrate` and returns the
   v2 contract plus its :class:`MigrationReport`.
3. **pre-protocol clients** (slice 426): no code needed — the
   server negotiates. Documented in ``docs/migration.md`` only.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any

from hugrgate.client import HugrGateClient
from hugrgate.contracts.migration import (
    MigrationReport,
    migrate,
    migrate_spec_dict,
)
from hugrgate.contracts.schema import DecisionContract
from hugrgate.errors import SDKError

if TYPE_CHECKING:  # httpx must stay out of the base install
    from hugrgate.sdk import HugrGateSDK

__all__ = [
    "migrate_contract",
    "upgrade_client",
]


def upgrade_client(client: HugrGateClient, *,
                   max_retries: int = 3,
                   retry_backoff_s: float = 0.1) -> HugrGateSDK:
    """Rebuild a v1 client as an SDK v2 with identical transport settings.

    The v1 instance is left untouched (and usable); the returned SDK
    talks to the same url / socket / in-process gate with the same
    timeout and fallback behavior, plus retries and a versioned
    User-Agent.
    """
    # Local import: hugrgate.sdk pulls in httpx, which must stay out
    # of the base install (slice 428 layering rule).
    from hugrgate.sdk import HugrGateSDK
    if isinstance(client, HugrGateSDK):
        return client
    if not isinstance(client, HugrGateClient):
        raise SDKError(
            f"upgrade_client needs a HugrGateClient, got "
            f"{type(client).__name__}")
    return HugrGateSDK(
        url=None if client._direct_gate else client.url,
        socket_path=None if client._direct_gate else client.socket_path,
        gate=client._gate if client._direct_gate else None,
        extra_backends=list(client._extra_backends),
        timeout=client.timeout,
        fallback_inprocess=client.fallback_inprocess,
        max_retries=max_retries,
        retry_backoff_s=retry_backoff_s,
    )


def migrate_contract(d: Mapping[str, Any],
                     to_version: str = "2.0"
                     ) -> tuple[DecisionContract, MigrationReport]:
    """Migrate a contract dict to ``to_version`` (default ``"2.0"``).

    Dicts without ``schema_version`` are treated as v1. Returns the
    migrated contract and the :class:`MigrationReport` describing
    what changed; check ``report.lossy`` / ``report.warnings``
    before deploying the result.
    """
    from_version = str(d.get("schema_version", "1.0"))
    if from_version == "1.0" and to_version == "2.0":
        # Keep the real report (warnings, lossy flag) instead of
        # going through the dict registry, which discards it.
        return migrate_spec_dict(
            d, contract_id=d.get("contract_id", "migrated"))
    contract = migrate(d, to_version=to_version)
    return contract, MigrationReport(
        source_version=from_version,
        target_version=to_version,
        result=contract)
