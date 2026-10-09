"""HugrGate Python SDK v2. Slice 428.

:class:`HugrGateSDK` builds on the battle-tested
:class:`~hugrgate.client.HugrGateClient` transport and adds the
ergonomics production integrations actually need:

- context-manager use (``with HugrGateSDK(...) as sdk:``),
- automatic retry with exponential backoff on *recoverable* failures
  (transport errors, HTTP 502/503, taxonomy errors flagged
  recoverable) — never on caller bugs like ``spec_error``,
- HTTP error envelopes mapped back onto the HugrGate error taxonomy
  (``SpecError``, ``BackendUnavailable``, ...) instead of leaking
  ``httpx.HTTPStatusError``,
- ``decide_batch`` for one spec over many states,
- a versioned ``User-Agent`` header so operators can see SDK skew in
  their access logs.

v1 (:mod:`hugrgate.client`) is untouched and keeps working; v2 is a
strict superset.
"""

from __future__ import annotations

import time
from collections.abc import Mapping
from typing import Any

import httpx

from hugrgate.backend import Backend
from hugrgate.client import HugrGateClient
from hugrgate.core import HugrGate
from hugrgate.errors import (
    Abstention,
    BackendError,
    BackendUnavailable,
    HugrGateError,
    SDKError,
    SpecError,
)
from hugrgate.policy import DecisionPolicy
from hugrgate.result import DecisionResult
from hugrgate.serde import result_from_dict
from hugrgate.spec import DecisionSpec

__all__ = [
    "SDK_VERSION",
    "HugrGateSDK",
]

#: SDK v2 protocol marker sent in the User-Agent header.
SDK_VERSION = "2.0"

#: HTTP statuses the SDK treats as retryable (transient service-side).
_RETRYABLE_STATUS = {502, 503, 504}


class HugrGateSDK(HugrGateClient):
    """Production-grade HugrGate client.

    Parameters mirror :class:`HugrGateClient`, plus:

    - ``max_retries``: attempts beyond the first on recoverable
      failures (0 disables retrying).
    - ``retry_backoff_s``: base backoff between attempts; the actual
      wait is ``backoff * 2**attempt``.
    """

    def __init__(self, url: str | None = None,
                 socket_path: str | None = None,
                 gate: HugrGate | None = None,
                 extra_backends: list[Backend] | None = None,
                 timeout: float = 10.0,
                 fallback_inprocess: bool = True,
                 max_retries: int = 3,
                 retry_backoff_s: float = 0.1) -> None:
        super().__init__(url=url, socket_path=socket_path, gate=gate,
                         extra_backends=extra_backends, timeout=timeout,
                         fallback_inprocess=fallback_inprocess)
        if max_retries < 0:
            raise ValueError("max_retries must be >= 0")
        if retry_backoff_s < 0:
            raise ValueError("retry_backoff_s must be >= 0")
        self.max_retries = max_retries
        self.retry_backoff_s = retry_backoff_s
        self._http.headers["user-agent"] = (
            f"hugrgate-sdk-py/{SDK_VERSION}")
        self._closed = False

    # -- resource management ------------------------------------------------
    def __enter__(self) -> HugrGateSDK:
        return self

    def __exit__(self, *exc: Any) -> None:
        self.close()

    def close(self) -> None:
        if not self._closed:
            self._closed = True
            super().close()

    # -- retrying transport ---------------------------------------------------
    def _post_decide(self, payload: dict[str, Any]) -> dict[str, Any]:
        """POST with exponential-backoff retry on recoverable faults."""
        attempt = 0
        while True:
            try:
                return super()._post_decide(payload)
            except (httpx.ConnectError, httpx.TimeoutException,
                    httpx.TransportError, OSError) as e:
                if attempt >= self.max_retries:
                    raise SDKError(
                        f"sdk transport failed after "
                        f"{attempt + 1} attempt(s): {e}") from e
                self._sleep(attempt)
                attempt += 1
            except httpx.HTTPStatusError as e:
                if (e.response.status_code not in _RETRYABLE_STATUS
                        or attempt >= self.max_retries):
                    raise
                self._sleep(attempt)
                attempt += 1

    def _sleep(self, attempt: int) -> None:
        delay = self.retry_backoff_s * (2 ** attempt)
        if delay > 0:
            time.sleep(delay)

    # -- taxonomy error mapping -------------------------------------------------
    @staticmethod
    def _map_http_error(exc: httpx.HTTPStatusError) -> HugrGateError:
        """Map an HTTP error response onto the HugrGate taxonomy."""
        try:
            body = exc.response.json()
            err = body.get("error", {})
            if isinstance(err, dict) and err.get("code"):
                return HugrGateError.from_dict({
                    "code": err.get("code", "hugrgate_error"),
                    "message": err.get("message", str(exc)),
                    "recoverable": err.get("recoverable", True),
                    "details": err.get("details", {}),
                })
        except Exception:  # noqa: BLE001 - unparseable body: generic error
            pass
        status = exc.response.status_code
        if status == 422:
            return SpecError(f"service rejected request: {exc}")
        if status == 503:
            return BackendUnavailable(f"service unavailable: {exc}")
        return BackendError(f"service error {status}: {exc}")

    def decide(self, state: Mapping[str, Any], spec: DecisionSpec,
               policy: DecisionPolicy | None = None,
               backend_name: str | None = None,
               context: Mapping[str, Any] | None = None
               ) -> DecisionResult:
        """Make a decision, retrying recoverable failures.

        Raises taxonomy errors (:class:`SpecError`,
        :class:`BackendUnavailable`, :class:`SDKError`, ...) rather
        than raw httpx exceptions.
        """
        if self._direct_gate:
            return super().decide(state, spec, policy,
                                  backend_name=backend_name,
                                  context=context)
        payload: dict[str, Any] = {
            "protocol_version": "1.0",
            "spec": spec.to_dict(),
            "state": dict(state),
            "backend_name": backend_name,
            "context": dict(context) if context else None,
        }
        if policy is not None:
            from hugrgate.serde import policy_to_dict
            payload["policy"] = policy_to_dict(policy)
        try:
            body = self._post_decide(payload)
        except httpx.HTTPStatusError as e:
            raise self._map_http_error(e) from e
        except (httpx.ConnectError, httpx.TimeoutException,
                httpx.TransportError, OSError) as e:
            # _post_decide already retried; last resort is the
            # in-process fallback (v1 semantics) before giving up.
            if self.fallback_inprocess:
                return self._fallback_decide(state, spec, policy,
                                             backend_name, context)
            raise SDKError(f"sdk transport failed: {e}") from e
        if body.get("abstained"):
            raise Abstention(body.get("message") or "service abstained",
                             reason=body.get("reason") or "below_threshold")
        decision = body.get("decision", body)
        if not isinstance(decision, dict) or "value" not in decision:
            raise SDKError(
                f"service returned no decision: {body.get('error')}")
        result = result_from_dict(decision)
        result.metadata["client_transport"] = (
            "unix-socket" if self.socket_path else "http")
        result.metadata["sdk_version"] = SDK_VERSION
        return result

    def decide_batch(self, states: list[Mapping[str, Any]],
                     spec: DecisionSpec,
                     policy: DecisionPolicy | None = None,
                     backend_name: str | None = None
                     ) -> list[DecisionResult | HugrGateError]:
        """Decide one spec over many states.

        Per-item errors are returned in place (never raised): a batch
        is a report, not a transaction.
        """
        outcomes: list[DecisionResult | HugrGateError] = []
        for state in states:
            try:
                outcomes.append(self.decide(state, spec, policy,
                                            backend_name=backend_name))
            except HugrGateError as e:
                outcomes.append(e)
        return outcomes

    def decide_value(self, state: Mapping[str, Any], spec: DecisionSpec,
                     policy: DecisionPolicy | None = None,
                     backend_name: str | None = None) -> Any:
        """Convenience: just the decided value."""
        return self.decide(state, spec, policy,
                           backend_name=backend_name).value
