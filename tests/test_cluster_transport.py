"""Tests for slice 209 — encrypted transport."""

from __future__ import annotations

import os
import shutil
import socket
import ssl
import stat

import httpx
import pytest

from hugrgate import DecisionPolicy, DecisionSpec
from hugrgate.cluster.discovery import PeerRecord
from hugrgate.cluster.identity import NodeIdentity
from hugrgate.cluster.node import ClusterNode
from hugrgate.cluster.rpc import RPCClient
from hugrgate.cluster.transport import (
    TLSServer,
    cert_fingerprint,
    fetch_server_fingerprint,
    make_self_signed_cert,
    trusted_context_for,
    verify_cert_fingerprint,
)
from hugrgate.errors import SpecError
from hugrgate.server import build_gate, create_app

pytestmark = pytest.mark.slow

NEEDS_OPENSSL = shutil.which("openssl") is None
skip_no_openssl = pytest.mark.skipif(
    NEEDS_OPENSSL, reason="openssl CLI not available")


@pytest.fixture
def certs(tmp_path):
    cert = tmp_path / "node.crt"
    key = tmp_path / "node.key"
    make_self_signed_cert(cert, key)
    return cert, key


@pytest.fixture
def server_node():
    return ClusterNode(NodeIdentity.generate("tls-srv"), build_gate())


# --- certificate minting --------------------------------------------------------

@skip_no_openssl
def test_cert_generation(tmp_path):
    cert, key = tmp_path / "c.crt", tmp_path / "k.key"
    make_self_signed_cert(cert, key, hostname="testnode", days=30)
    assert cert.exists() and key.exists()
    assert b"BEGIN CERTIFICATE" in cert.read_bytes()
    assert b"PRIVATE KEY" in key.read_bytes()
    mode = stat.S_IMODE(os.stat(key).st_mode)
    assert mode == 0o600


@skip_no_openssl
def test_cert_fingerprint_shape(certs):
    cert, _ = certs
    fp = cert_fingerprint(cert)
    assert len(fp) == 64
    assert all(c in "0123456789abcdef" for c in fp)


@skip_no_openssl
def test_cert_generation_rejects_bad_days(tmp_path):
    with pytest.raises(SpecError, match=">= 1 day"):
        make_self_signed_cert(tmp_path / "c", tmp_path / "k", days=0)


def test_fingerprint_missing_file(tmp_path):
    with pytest.raises(SpecError, match="cannot read"):
        cert_fingerprint(tmp_path / "nope.crt")


def test_fingerprint_bad_pem(tmp_path):
    path = tmp_path / "bad.crt"
    path.write_text("not a certificate", encoding="utf-8")
    with pytest.raises(SpecError, match="not valid PEM"):
        cert_fingerprint(path)


@skip_no_openssl
def test_verify_cert_fingerprint(certs):
    cert, _ = certs
    fp = cert_fingerprint(cert)
    assert verify_cert_fingerprint(cert, fp)
    assert verify_cert_fingerprint(cert, fp.upper())
    assert not verify_cert_fingerprint(cert, "ab" * 32)
    assert not verify_cert_fingerprint(cert, "not-hex")
    assert not verify_cert_fingerprint(cert, None)
    assert not verify_cert_fingerprint("/nonexistent.crt", fp)


# --- TLS round trip ---------------------------------------------------------------

@skip_no_openssl
def test_tls_health_round_trip(certs, server_node):
    cert, key = certs
    with TLSServer(create_app(node=server_node),
                   certfile=cert, keyfile=key) as server:
        assert server.url.startswith("https://127.0.0.1:")
        ctx = trusted_context_for(cert)
        with httpx.Client(verify=ctx, trust_env=False) as client:
            r = client.get(server.url + "/cluster/health")
            assert r.status_code == 200
            assert r.json()["node_id"] == server_node.node_id


@skip_no_openssl
def test_rpc_decide_over_tls(certs, server_node):
    cert, key = certs
    policy = DecisionPolicy(remote_inference=True)
    spec = DecisionSpec(type="categorical", options=["ignore", "escalate"])
    with TLSServer(create_app(node=server_node),
                   certfile=cert, keyfile=key) as server:
        ctx = trusted_context_for(cert)
        rpc = RPCClient(
            node_id=NodeIdentity.generate().node_id,
            http_client=httpx.Client(verify=ctx, trust_env=False))
        peer = PeerRecord(node_id=server_node.node_id,
                          host="127.0.0.1", port=server.port, tls=True)
        try:
            result = rpc.decide(peer, spec, {"text": "escalate"},
                                policy=policy)
            assert result.value in ("ignore", "escalate")
        finally:
            rpc.close()


@skip_no_openssl
def test_plaintext_to_tls_port_fails(certs, server_node):
    cert, key = certs
    with TLSServer(create_app(node=server_node),
                   certfile=cert, keyfile=key) as server:
        plain_url = server.url.replace("https://", "http://")
        with httpx.Client(trust_env=False) as client:
            with pytest.raises(httpx.TransportError):
                client.get(plain_url + "/cluster/health", timeout=5.0)


@skip_no_openssl
def test_wrong_cert_rejected(certs, server_node, tmp_path):
    cert, key = certs
    other_cert, other_key = tmp_path / "o.crt", tmp_path / "o.key"
    make_self_signed_cert(other_cert, other_key)
    with TLSServer(create_app(node=server_node),
                   certfile=cert, keyfile=key):
        # client pins a DIFFERENT certificate -> handshake must fail
        ctx = trusted_context_for(other_cert)
        with httpx.Client(verify=ctx, trust_env=False) as client:
            with pytest.raises(httpx.ConnectError):
                client.get("https://127.0.0.1:1/", timeout=5.0)


@skip_no_openssl
def test_fetched_fingerprint_matches(certs, server_node):
    cert, key = certs
    with TLSServer(create_app(node=server_node),
                   certfile=cert, keyfile=key) as server:
        fetched = fetch_server_fingerprint("127.0.0.1", server.port)
        assert fetched == cert_fingerprint(cert)


@skip_no_openssl
def test_tls_server_lifecycle(certs, server_node):
    cert, key = certs
    server = TLSServer(create_app(node=server_node),
                       certfile=cert, keyfile=key)
    with pytest.raises(SpecError, match="not running"):
        _ = server.url
    with server:
        assert server.port >= 1
        # raw TLS handshake reaches a real TLS endpoint
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        with socket.create_connection(("127.0.0.1", server.port),
                                     timeout=5.0) as sock:
            with ctx.wrap_socket(sock,
                                 server_hostname="127.0.0.1"):
                pass  # handshake succeeded


# --- validation ---------------------------------------------------------------------

def test_tls_server_rejects_non_loopback(tmp_path):
    with pytest.raises(SpecError, match="loopback"):
        TLSServer(None, host="0.0.0.0", certfile="c", keyfile="k")


def test_tls_server_requires_cert_paths():
    with pytest.raises(SpecError, match="certfile"):
        TLSServer(None)
