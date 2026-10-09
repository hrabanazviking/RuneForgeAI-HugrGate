"""Encrypted transport for cluster RPC. Slice 209.

Cluster traffic crosses node boundaries, so it must be encrypted in
transit — HMAC (slice 208) proves *who* sent a message, TLS keeps its
*contents* (states may carry sensitive fields) off the wire.

The building blocks are deliberately boring and standard:

- :func:`make_self_signed_cert` shells out to the system ``openssl``
  CLI (no new Python dependency) to mint a node certificate; the key
  file lands at 0600.
- :class:`TLSServer` runs any ASGI app (the cluster app, the daemon
  app) over TLS on localhost in a background thread.
- :func:`trusted_context_for` builds a client ``SSLContext`` that
  trusts *exactly* the given self-signed certificate — since the cert
  is its own CA, this is certificate pinning in effect: no other cert,
  however signed, validates.
- :func:`cert_fingerprint` / :func:`verify_cert_fingerprint` give an
  explicit SHA-256 pin operators can compare out of band.

TLS here complements, not replaces, slice 208: TLS encrypts the
channel; the HMAC tag authenticates each envelope even if TLS were
terminated at a middlebox.
"""

from __future__ import annotations

import hashlib
import os
import shutil
import socket
import ssl
import subprocess
import threading
import time
from typing import Any

from hugrgate.errors import SpecError

__all__ = [
    "TLSServer",
    "cert_fingerprint",
    "fetch_server_fingerprint",
    "make_self_signed_cert",
    "trusted_context_for",
    "verify_cert_fingerprint",
]


def _need_openssl() -> str:
    path = shutil.which("openssl")
    if path is None:
        raise SpecError(
            "the 'openssl' CLI is required to mint node certificates "
            "but was not found on PATH")
    return path


def make_self_signed_cert(cert_path: str | os.PathLike[str],
                          key_path: str | os.PathLike[str],
                          hostname: str = "localhost",
                          days: int = 365) -> None:
    """Mint a self-signed certificate via the ``openssl`` CLI.

    Writes ``cert_path`` (PEM certificate) and ``key_path`` (PEM
    private key, chmod 0600). Raises :class:`SpecError` when openssl is
    missing or the command fails — never a half-written pair.
    """
    openssl = _need_openssl()
    if days < 1:
        raise SpecError("certificate lifetime must be >= 1 day")
    cert_path, key_path = os.fspath(cert_path), os.fspath(key_path)
    tmp_key = key_path + ".tmp"
    tmp_cert = cert_path + ".tmp"
    for tmp in (tmp_key, tmp_cert):
        try:
            os.unlink(tmp)
        except FileNotFoundError:
            pass
    cmd = [
        openssl, "req", "-x509", "-newkey", "rsa:2048",
        "-keyout", tmp_key, "-out", tmp_cert,
        "-days", str(days), "-nodes",
        "-subj", f"/CN={hostname}",
        "-addext", f"subjectAltName=DNS:{hostname},IP:127.0.0.1",
    ]
    try:
        subprocess.run(cmd, check=True, capture_output=True, text=True,
                       timeout=60)
    except subprocess.CalledProcessError as e:
        raise SpecError(
            f"openssl failed to mint a certificate: "
            f"{e.stderr.strip()[:300]}") from e
    except subprocess.TimeoutExpired as e:
        raise SpecError("openssl timed out minting a certificate") from e
    os.chmod(tmp_key, 0o600)
    os.replace(tmp_key, key_path)
    os.replace(tmp_cert, cert_path)


def cert_fingerprint(cert_path: str | os.PathLike[str]) -> str:
    """SHA-256 fingerprint (hex) of the DER-encoded certificate."""
    try:
        with open(cert_path, encoding="utf-8") as fh:
            pem = fh.read()
    except OSError as e:
        raise SpecError(
            f"cannot read certificate {cert_path}: {e}") from e
    try:
        der = ssl.PEM_cert_to_DER_cert(pem)
    except (ssl.SSLError, ValueError) as e:
        raise SpecError(
            f"certificate {cert_path} is not valid PEM: {e}") from e
    return hashlib.sha256(der).hexdigest()


def verify_cert_fingerprint(cert_path: str | os.PathLike[str],
                            expected: str) -> bool:
    """True when the certificate's fingerprint equals ``expected``.

    Never raises on a malformed ``expected`` — a bad pin is ``False``.
    """
    if not isinstance(expected, str):
        return False
    try:
        actual = cert_fingerprint(cert_path)
    except SpecError:
        return False
    if len(expected) != 64 or any(
            c not in "0123456789abcdefABCDEF" for c in expected):
        return False
    return actual.lower() == expected.lower()


def trusted_context_for(cert_path: str | os.PathLike[str]) -> ssl.SSLContext:
    """Client context trusting *exactly* this self-signed certificate.

    The cert is loaded as the sole CA: only that exact certificate
    validates — effective pinning without a fingerprint dance on every
    connection. Hostname checking is disabled because node identities
    are key-based (slice 202), not DNS-based; the HMAC layer (208)
    authenticates the peer.
    """
    context = ssl.create_default_context(cafile=os.fspath(cert_path))
    context.check_hostname = False
    return context


#: Reminder for callers: pair the context above with
#: ``httpx.Client(verify=ctx, trust_env=False)`` — proxy environment
#: variables must never reroute cluster traffic, and exotic ``no_proxy``
#: entries can choke httpx's env parser (the same rationale as
#: :class:`HugrGateClient`).


class TLSServer:
    """Run an ASGI app over TLS on localhost, in a background thread.

    Usage::

        with TLSServer(app, certfile=c, keyfile=k) as server:
            httpx.get(server.url + "/cluster/health", verify=ctx)
    """

    def __init__(self, app: Any, host: str = "127.0.0.1", port: int = 0,
                 certfile: str | os.PathLike[str] = "",
                 keyfile: str | os.PathLike[str] = "") -> None:
        if host not in ("127.0.0.1", "::1", "localhost"):
            raise SpecError(
                f"TLSServer binds loopback only, got {host!r}")
        if not certfile or not keyfile:
            raise SpecError("TLSServer needs certfile and keyfile")
        self._app = app
        self._host = host
        self._port = port
        self._certfile = os.fspath(certfile)
        self._keyfile = os.fspath(keyfile)
        self._server: Any = None
        self._thread: threading.Thread | None = None

    @property
    def url(self) -> str:
        if self._server is None:
            raise SpecError("TLSServer is not running")
        return f"https://{self._host}:{self.port}"

    @property
    def port(self) -> int:
        if self._server is None:
            raise SpecError("TLSServer is not running")
        sockets = self._server.servers[0].sockets
        return int(sockets[0].getsockname()[1])

    def __enter__(self) -> TLSServer:
        import uvicorn

        config = uvicorn.Config(
            self._app, host=self._host, port=self._port,
            ssl_certfile=self._certfile, ssl_keyfile=self._keyfile,
            log_level="error")
        self._server = uvicorn.Server(config)
        self._thread = threading.Thread(
            target=self._server.run, name="tls-server", daemon=True)
        self._thread.start()
        deadline = time.time() + 15.0
        while not self._server.started:
            if time.time() > deadline:
                raise SpecError("TLS server did not start in time")
            time.sleep(0.05)
        return self

    def __exit__(self, *exc: Any) -> None:
        server, thread = self._server, self._thread
        self._server, self._thread = None, None
        if server is not None:
            server.should_exit = True
        if thread is not None:
            thread.join(timeout=10.0)


def fetch_server_fingerprint(host: str, port: int,
                             timeout: float = 5.0) -> str:
    """Grab the SHA-256 fingerprint of whatever serves TLS at host:port.

    Useful for TOFU (trust-on-first-use) pinning workflows.
    """
    context = ssl.create_default_context()
    context.check_hostname = False
    context.verify_mode = ssl.CERT_NONE
    with socket.create_connection((host, port), timeout=timeout) as sock:
        with context.wrap_socket(sock, server_hostname=host) as tls:
            der = tls.getpeercert(binary_form=True)
    if der is None:
        raise SpecError("peer presented no certificate")
    return hashlib.sha256(der).hexdigest()
