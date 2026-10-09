"""Gjallarbrú slice 027 — contract version negotiation."""

from __future__ import annotations

import pytest

from hugrgate.contracts.negotiation import (
    ContractEndpoint,
    NegotiationResult,
    SessionAgreement,
    VersionOffer,
    negotiate_session,
    negotiate_version,
    parse_version,
)
from hugrgate.errors import ContractError


def offer(party, *versions):
    return VersionOffer(party=party, versions=tuple(versions))


# --- success ---------------------------------------------------------------

def test_single_party_picks_its_top_choice():
    r = negotiate_version(offer("a", "2.0", "1.0"))
    assert r.version == "2.0"
    assert r.common == ("2.0", "1.0")
    assert r.parties == ("a",)


def test_identical_offers_agree():
    r = negotiate_version(offer("a", "2.0"), offer("b", "2.0"))
    assert r.version == "2.0"


def test_preference_rank_sum_decides():
    # a prefers 2.0 (rank 0), b prefers 1.5 (rank 0): tie on rank sum
    # (1+1=2 for both 2.0 and 1.5? no:) 2.0 -> 0+1=1, 1.5 -> 1+0=1 -> tie
    # -> highest version wins: 2.0
    r = negotiate_version(offer("a", "2.0", "1.5"), offer("b", "1.5", "2.0"))
    assert r.version == "2.0"


def test_rank_sum_beats_version_height():
    # both rank 1.0 first: rank sum 0 beats 2.0's rank sum 2
    r = negotiate_version(offer("a", "1.0", "2.0"), offer("b", "1.0", "2.0"))
    assert r.version == "1.0"


def test_three_parties():
    r = negotiate_version(
        offer("a", "2.0", "1.0"),
        offer("b", "2.0", "1.0"),
        offer("c", "1.0", "2.0"),
    )
    assert r.version == "2.0"
    assert r.parties == ("a", "b", "c")


def test_result_round_trips_to_dict():
    r = negotiate_version(offer("a", "2.0"))
    d = r.to_dict()
    assert d["version"] == "2.0" and d["parties"] == ["a"]


def test_session_negotiation_happy_path():
    client = ContractEndpoint(party="client", schema_versions=("2.0",),
                              kinds=("contract", "ordinal"))
    server = ContractEndpoint(party="server", schema_versions=("2.0", "1.0"),
                              kinds=("ordinal", "contract", "numeric"))
    s = negotiate_session(client, server)
    assert isinstance(s, SessionAgreement)
    assert s.schema_version == "2.0"
    assert s.kinds == ("contract", "ordinal")  # client preference order
    assert s.supports_kind("ordinal")
    assert not s.supports_kind("numeric")
    assert s.to_dict()["client"] == "client"


def test_local_endpoint_uses_supported_versions():
    ep = ContractEndpoint.local(["contract"])
    assert "2.0" in ep.schema_versions


def test_endpoint_offer_matches():
    ep = ContractEndpoint(party="p", schema_versions=("2.0",), kinds=("k",))
    assert ep.offer() == VersionOffer(party="p", versions=("2.0",))


# --- failure ---------------------------------------------------------------

def test_disjoint_versions_raise():
    with pytest.raises(ContractError) as ei:
        negotiate_version(offer("a", "2.0"), offer("b", "1.0"))
    assert ei.value.details["code"] == "no_common_version"


def test_disjoint_kinds_raise():
    client = ContractEndpoint(party="c", schema_versions=("2.0",), kinds=("a",))
    server = ContractEndpoint(party="s", schema_versions=("2.0",), kinds=("b",))
    with pytest.raises(ContractError) as ei:
        negotiate_session(client, server)
    assert ei.value.details["code"] == "no_common_kind"


def test_no_offers_raise():
    with pytest.raises(ContractError):
        negotiate_version()


def test_duplicate_parties_raise():
    with pytest.raises(ContractError):
        negotiate_version(offer("a", "2.0"), offer("a", "2.0"))


def test_malformed_version_rejected():
    with pytest.raises(ContractError):
        parse_version("2.x")
    with pytest.raises(ContractError):
        parse_version("")
    with pytest.raises(ContractError):
        offer("a", "2.0", "bogus")


def test_empty_version_list_rejected():
    with pytest.raises(ContractError):
        VersionOffer(party="a", versions=())


def test_duplicate_versions_in_offer_rejected():
    with pytest.raises(ContractError):
        offer("a", "2.0", "2.0")


def test_empty_party_rejected():
    with pytest.raises(ContractError):
        VersionOffer(party="", versions=("2.0",))


def test_negotiated_unreadable_version_flagged():
    # Two peers agree on 9.9, which this codebase cannot read.
    client = ContractEndpoint(party="c", schema_versions=("9.9",), kinds=("k",))
    server = ContractEndpoint(party="s", schema_versions=("9.9",), kinds=("k",))
    with pytest.raises(ContractError) as ei:
        negotiate_session(client, server)
    assert ei.value.details["code"] == "negotiated_version_unreadable"


# --- boundary ----------------------------------------------------------------

def test_version_ordering_patch_levels():
    assert parse_version("2.0.10") > parse_version("2.0.9")
    r = negotiate_version(offer("a", "2.0.9", "2.0.10"),
                          offer("b", "2.0.10", "2.0.9"))
    assert r.version == "2.0.10"  # rank-sum tie -> highest


def test_duplicate_kinds_rejected():
    with pytest.raises(ContractError):
        ContractEndpoint(party="p", schema_versions=("2.0",),
                         kinds=("k", "k"))


def test_session_needs_endpoints():
    with pytest.raises(ContractError):
        negotiate_session("nope", ContractEndpoint.local([]))  # type: ignore[arg-type]
