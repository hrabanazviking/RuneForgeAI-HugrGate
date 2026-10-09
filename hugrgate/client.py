"""HugrGate Python SDK — client for the HTTP service. Slice 43.

:class:`HugrGateClient` mirrors the in-process :class:`HugrGate` ``decide``
interface over HTTP, with automatic fallback to an in-process gate when
the service is unreachable.

The JSON serde helpers (:func:`policy_to_dict`,
:func:`policy_from_dict`, :func:`result_from_dict`) live in
:mod:`hugrgate.serde` and are re-exported here for backward
compatibility.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import httpx

from hugrgate.backend import Backend
from hugrgate.core import HugrGate
from hugrgate.errors import Abstention, BackendError
from hugrgate.policy import DecisionPolicy
from hugrgate.result import DecisionResult
from hugrgate.serde import (
    policy_from_dict,
    policy_to_dict,
    result_from_dict,
)
from hugrgate.spec import DecisionSpec

__all__ = [
    "HugrGateClient",
    "policy_from_dict",
    "policy_to_dict",
    "result_from_dict",
]


class HugrGateClient:
    """Client for a HugrGate service, with in-process fallback.

    Usage:
        client = HugrGateClient("http://127.0.0.1:8377")
        result = client.decide(state, spec, policy)

    If the service cannot be reached and ``fallback_inprocess`` is true,
    the decision is made by a local gate with the built-in backends and
    the result carries ``metadata["client_fallback"] = "inprocess"``.
    """

    def __init__(self, url: str | None = None,
                 socket_path: str | None = None,
                 gate: HugrGate | None = None,
                 extra_backends: list[Backend] | None = None,
                 timeout: float = 10.0,
                 fallback_inprocess: bool = True) -> None:
        """Create a client.

        - ``gate``: decide directly against this in-process gate (no HTTP).
        - ``url`` / ``socket_path``: talk to a service; on connection
          failure fall back to an in-process gate when
          ``fallback_inprocess`` is true.
        """
        if gate is not None and (url or socket_path):
            raise ValueError("pass gate or url/socket_path, not both")
        if gate is not None and extra_backends:
            raise ValueError("pass gate or extra_backends, not both")
        if url and socket_path:
            raise ValueError("pass url or socket_path, not both")
        self.url = (url or "http://127.0.0.1:8377").rstrip("/")
        self.socket_path = socket_path
        self.timeout = timeout
        self.fallback_inprocess = fallback_inprocess
        self._extra_backends = extra_backends or []
        self._gate: HugrGate | None = gate
        self._direct_gate = gate is not None
        # trust_env=False: this client talks to a local daemon; proxy
        # environment variables must never reroute loopback IPC. (It also
        # avoids httpx choking on exotic no_proxy entries.)
        self._http = httpx.Client(timeout=timeout, trust_env=False)

    # -- in-process fallback ------------------------------------------------
    def _inprocess_gate(self) -> HugrGate:
        if self._gate is None:
            # Lazy: importing server at module level would drag the
            # FastAPI/uvicorn server dependencies into the lightweight
            # SDK import (slice 021).
            from hugrgate.server import build_gate
            self._gate = build_gate(self._extra_backends)
        return self._gate

    def _direct(self) -> HugrGate:
        """The caller-supplied in-process gate.

        Invariant: ``_direct_gate`` is true exactly when ``_gate`` was
        given at construction; the assert makes that visible to checkers.
        """
        gate = self._gate
        assert gate is not None, "direct-gate client without a gate"
        return gate

    def _fallback_decide(self, state: Mapping[str, Any], spec: DecisionSpec,
                         policy: DecisionPolicy | None,
                         backend_name: str | None,
                         context: Mapping[str, Any] | None) -> DecisionResult:
        result = self._inprocess_gate().decide(
            state, spec, policy, context=context, backend_name=backend_name)
        result.metadata["client_fallback"] = "inprocess"
        return result

    # -- HTTP transport -----------------------------------------------------
    def _post_decide(self, payload: dict[str, Any]) -> dict[str, Any]:
        if self.socket_path:
            transport = httpx.HTTPTransport(uds=self.socket_path)
            client = httpx.Client(transport=transport, timeout=self.timeout,
                                  trust_env=False)
        else:
            client = self._http
        try:
            response = client.post(f"{self.url}/decide", json=payload)
        finally:
            if self.socket_path:
                client.close()
        response.raise_for_status()
        return response.json()

    def decide(self, state: Mapping[str, Any], spec: DecisionSpec,
               policy: DecisionPolicy | None = None,
               backend_name: str | None = None,
               context: Mapping[str, Any] | None = None
               ) -> DecisionResult:
        """Make a decision via the service (or the in-process fallback)."""
        if self._direct_gate:
            # Caller-supplied in-process gate: no HTTP at all.
            gate = self._direct()
            result = gate.decide(state, spec, policy,
                                 context=context,
                                 backend_name=backend_name)
            result.metadata["client_transport"] = "inprocess"
            return result
        payload: dict[str, Any] = {
            "spec": spec.to_dict(),
            "state": dict(state),
            "backend_name": backend_name,
            "context": dict(context) if context else None,
        }
        if policy is not None:
            payload["policy"] = policy_to_dict(policy)
        try:
            body = self._post_decide(payload)
        except (httpx.ConnectError, httpx.TimeoutException,
                httpx.TransportError, OSError) as e:
            if self.fallback_inprocess:
                return self._fallback_decide(state, spec, policy,
                                             backend_name, context)
            raise BackendError(f"hugrgate service unreachable: {e}") from e
        if body.get("abstained"):
            raise Abstention(body.get("message") or "service abstained",
                             reason=body.get("reason") or "below_threshold")
        # Success is the DecisionResult JSON directly (may be enveloped
        # as {"decision": {...}} by older services).
        decision = body.get("decision", body)
        if not isinstance(decision, dict) or "value" not in decision:
            raise BackendError(
                f"service returned no decision: {body.get('error')}")
        result = result_from_dict(decision)
        result.metadata["client_transport"] = (
            "unix-socket" if self.socket_path else "http")
        return result

    def health(self) -> dict[str, Any]:
        """Liveness probe. Never raises: reports reachability."""
        if self._direct_gate:
            gate = self._direct()
            return {"reachable": True, "status": "ok",
                    "backends": gate.registry.list(),
                    "mode": "inprocess"}
        try:
            response = self._http.get(f"{self.url}/health")
            response.raise_for_status()
            data = response.json()
            data["reachable"] = True
            return data
        except Exception as e:  # noqa: BLE001 - reachability probe
            return {"reachable": False, "error": str(e)}

    def backends(self) -> list[dict[str, Any]]:
        """List backends known to the service (or the in-process gate)."""
        if self._direct_gate:
            gate = self._direct()
            infos = []
            for n in gate.registry.list():
                backend = gate.registry.get(n)
                if backend is None:  # defensive: list/get disagree
                    continue
                infos.append({"name": n, "is_remote": False,
                              "capabilities": backend.capabilities()})
            return infos
        try:
            response = self._http.get(f"{self.url}/backends")
            response.raise_for_status()
            body = response.json()
            # /backends returns a bare list (older services: {"backends": [...]})
            return body if isinstance(body, list) else body["backends"]
        except Exception:
            if self.fallback_inprocess:
                gate = self._inprocess_gate()
                infos = []
                for n in gate.registry.list():
                    backend = gate.registry.get(n)
                    if backend is None:  # defensive: list/get disagree
                        continue
                    infos.append({"name": n, "is_remote": False,
                                  "capabilities": backend.capabilities()})
                return infos
            raise

    def close(self) -> None:
        self._http.close()
