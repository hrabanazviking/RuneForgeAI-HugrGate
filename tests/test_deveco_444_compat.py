"""Slice 444 — compat helpers migrate for real."""

from __future__ import annotations

import pytest

from hugrgate.client import HugrGateClient
from hugrgate.compat import migrate_contract, upgrade_client
from hugrgate.contracts.migration import MigrationReport
from hugrgate.errors import SDKError
from hugrgate.sdk import HugrGateSDK


def test_upgrade_client_preserves_transport_settings():
    old = HugrGateClient("http://127.0.0.1:9999", timeout=5.0,
                         fallback_inprocess=False)
    new = upgrade_client(old, max_retries=5)
    assert isinstance(new, HugrGateSDK)
    assert new.url == "http://127.0.0.1:9999"
    assert new.timeout == 5.0
    assert new.fallback_inprocess is False
    assert new.max_retries == 5
    assert new._http.headers["user-agent"] == "hugrgate-sdk-py/2.0"
    # the v1 instance is untouched and still usable
    assert isinstance(old, HugrGateClient)
    assert not isinstance(old, HugrGateSDK)
    new.close()


def test_upgrade_client_with_inprocess_gate():
    from hugrgate.server import build_gate
    gate = build_gate()
    old = HugrGateClient(gate=gate)
    new = upgrade_client(old)
    assert isinstance(new, HugrGateSDK)
    assert new._direct_gate is True
    new.close()


def test_upgrade_client_is_idempotent_for_sdk():
    sdk = HugrGateSDK("http://127.0.0.1:9999")
    assert upgrade_client(sdk) is sdk
    sdk.close()


def test_upgrade_client_rejects_non_clients():
    with pytest.raises(SDKError):
        upgrade_client(object())  # type: ignore[arg-type]


def test_migrate_contract_v1_spec_dict():
    old = {"type": "categorical", "options": ["a", "b"]}
    contract, report = migrate_contract(old)
    assert isinstance(report, MigrationReport)
    assert report.source_version == "1.0"
    assert report.target_version == "2.0"
    assert contract.to_dict()["schema_version"] == "2.0"


def test_migrate_contract_reports_honestly():
    # v2 dicts pass through with an exact report, not a fabricated one
    v2 = {"schema_version": "2.0", "kind": "contract",
          "contract_id": "c", "name": "c"}
    contract, report = migrate_contract(v2)
    assert report.lossy is False
    assert report.warnings == []
    assert contract.contract_id == "c"


def test_migrate_contract_rejects_garbage():
    from hugrgate.errors import ContractError
    with pytest.raises(ContractError):
        migrate_contract({"type": "nope"})
