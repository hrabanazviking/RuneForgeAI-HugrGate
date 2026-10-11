"""HugrGate local HTTP API — FastAPI service. Slice 41.

Exposes the in-process :class:`HugrGate` runtime over HTTP:

- ``POST /decide`` — spec + state + policy JSON → result JSON
- ``GET  /health`` — liveness probe
- ``GET  /backends`` — registered backend capabilities
- ``GET  /models`` — known model catalogue entries

Localhost-only by default: :func:`run` binds ``127.0.0.1`` unless the
operator explicitly passes a different host.

This module also ships two small deterministic built-in backends
(``uniform`` and ``keyword``) so the service, CLI, daemon and benchmark
harness are usable end to end with zero ML dependencies. They are honest
baselines — not intelligent — and richer backends register through the
same :class:`BackendRegistry` contract.
"""

from __future__ import annotations

import math
import re
import time
import uuid
from collections.abc import Mapping
from dataclasses import asdict, dataclass, field
from typing import TYPE_CHECKING, Any

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from hugrgate import __version__ as HUGRGATE_VERSION
from hugrgate.backend import Backend
from hugrgate.core import HugrGate
from hugrgate.errors import (
    Abstention,
    BackendError,
    BackendUnavailable,
    HugrGateError,
    PolicyError,
    ProtocolError,
    SpecError,
)
from hugrgate.log import get_logger
from hugrgate.protocol import (
    PROTOCOL_VERSION,
    SUPPORTED_PROTOCOL_VERSIONS,
    negotiate_version,
)
from hugrgate.result import DecisionResult
from hugrgate.serde import policy_from_dict
from hugrgate.spec import DecisionSpec

if TYPE_CHECKING:
    from hugrgate.cluster.node import ClusterNode

__all__ = [
    "DecideRequest",
    "ErrorBody",
    "KeywordBackend",
    "ModelInfo",
    "ProtocolBody",
    "UniformBackend",
    "build_gate",
    "create_app",
    "dump_openapi_schema",
    "list_models",
    "register_model",
    "run",
]

logger = get_logger(__name__)

# Slice 15 (dusk, Wave C): request-ID propagation.
REQUEST_ID_HEADER = "X-Request-ID"

_WORD_RE = re.compile(r"[a-z0-9]+")


def _tokens(text: str) -> list[str]:
    return _WORD_RE.findall(text.lower())


def _overlap(state_tokens: set, keywords: set) -> int:
    """Count state tokens matching keywords, with prefix stemming.

    A token matches a keyword on equality, or when one is a prefix of the
    other (both length >= 4), e.g. "bill" matches "billing".
    """
    score = 0
    for tok in state_tokens:
        for kw in keywords:
            if tok == kw:
                score += 1
                break
            if len(tok) >= 4 and len(kw) >= 4 and (
                tok.startswith(kw) or kw.startswith(tok)
            ):
                score += 1
                break
    return score


def _softmax(scores: dict[str, float]) -> dict[str, float]:
    maximum = max(scores.values())
    exps = {k: math.exp(v - maximum) for k, v in scores.items()}
    total = sum(exps.values())
    return {k: v / total for k, v in exps.items()}


def _normalized_entropy(dist: dict[str, float]) -> float:
    n = len(dist)
    if n <= 1:
        return 0.0
    ent = -sum(p * math.log(p) for p in dist.values() if p > 0.0)
    return ent / math.log(n)


class UniformBackend(Backend):
    """Maximum-ignorance baseline: uniform distribution over the spec space.

    Useful as a calibration/accuracy floor in benchmarks and as a
    always-available fallback backend.
    """

    name = "uniform"

    def capabilities(self) -> dict[str, Any]:
        return {
            "spec_types": ["categorical", "binary", "ordinal", "numeric",
                           "multilabel"],
            "description": "Uniform distribution baseline (no intelligence).",
            "deterministic": True,
        }

    def supports(self, spec: DecisionSpec) -> bool:
        return spec.type in ("categorical", "binary", "ordinal", "numeric",
                             "multilabel")

    def evaluate(self, state: Mapping[str, Any], spec: DecisionSpec,
                 context: Mapping[str, Any] | None = None
                 ) -> DecisionResult:
        if spec.type == "numeric":
            # _validate_numeric guarantees both bounds are set.
            assert spec.minimum is not None and spec.maximum is not None
            mid = (spec.minimum + spec.maximum) / 2.0
            return DecisionResult(value=mid, probability=0.5, distribution={},
                                  uncertainty=1.0, backend=self.name,
                                  model="uniform-1.0")
        space = spec.value_space()
        dist = {v: 1.0 / len(space) for v in space}
        if spec.type == "multilabel":
            value: Any = []
        else:
            value = space[0]
        return DecisionResult(value=value, probability=dist[value] if value in dist else 0.0,
                              distribution=dist, uncertainty=1.0,
                              backend=self.name, model="uniform-1.0",
                              metadata={"baseline": True})


class KeywordBackend(Backend):
    """Deterministic keyword-overlap classifier.

    Scores each candidate label by token overlap between the state's text
    and the label's own words (with light prefix stemming), then applies a
    softmax to form a distribution. Transparent, offline, dependency-free.
    A real baseline for benchmarks — and genuinely useful for routing-style
    decisions where the labels name the thing being detected.
    """

    name = "keyword"

    def capabilities(self) -> dict[str, Any]:
        return {
            "spec_types": ["categorical", "binary", "ordinal"],
            "description": "Keyword overlap + softmax baseline.",
            "deterministic": True,
        }

    def supports(self, spec: DecisionSpec) -> bool:
        return spec.type in ("categorical", "binary", "ordinal")

    def _label_keywords(self, spec: DecisionSpec) -> dict[str, set]:
        if spec.type == "binary":
            return {
                "true": set(_tokens(spec.statement or "")),
                "false": set(),
            }
        labels = spec.value_space()
        return {label: set(_tokens(label)) for label in labels}

    def evaluate(self, state: Mapping[str, Any], spec: DecisionSpec,
                 context: Mapping[str, Any] | None = None
                 ) -> DecisionResult:
        text = " ".join(
            str(v) for v in state.values()
            if isinstance(v, (str, int, float, bool)))
        state_toks = set(_tokens(text))
        label_kws = self._label_keywords(spec)
        scores = {label: float(_overlap(state_toks, kws))
                  for label, kws in label_kws.items()}
        if sum(scores.values()) <= 0.0:
            n = len(scores)
            dist = {label: 1.0 / n for label in scores}
        else:
            dist = _softmax(scores)
        value = max(dist, key=lambda k: dist[k])
        return DecisionResult(
            value=value,
            probability=dist[value],
            distribution=dist,
            uncertainty=_normalized_entropy(dist),
            backend=self.name,
            model="keyword-1.0",
            metadata={"scores": scores,
                      "matched": sum(scores.values()) > 0.0},
        )


@dataclass
class ModelInfo:
    """A catalogue entry describing a servable model."""
    name: str
    version: str = "1.0"
    backend: str = "unknown"
    spec_types: list[str] = field(default_factory=list)
    description: str = ""
    trained_at: str | None = None
    metrics: dict[str, Any] = field(default_factory=dict)


_MODEL_CATALOG: list[ModelInfo] = [
    ModelInfo(name="uniform-1.0", backend="uniform",
              spec_types=["categorical", "binary", "ordinal", "numeric",
                          "multilabel"],
              description="Uniform baseline — no trained weights."),
    ModelInfo(name="keyword-1.0", backend="keyword",
              spec_types=["categorical", "binary", "ordinal"],
              description="Deterministic keyword-overlap baseline."),
]


def register_model(info: ModelInfo) -> None:
    """Add a model entry to the ``/models`` catalogue."""
    _MODEL_CATALOG.append(info)


def list_models() -> list[ModelInfo]:
    return list(_MODEL_CATALOG)


def build_gate(extra_backends: list[Backend] | None = None) -> HugrGate:
    """Build a :class:`HugrGate` wired with the built-in backends."""
    gate = HugrGate()
    gate.register(UniformBackend())
    gate.register(KeywordBackend())
    for backend in extra_backends or []:
        gate.register(backend)
    return gate


# --- OpenAPI stabilization (slice 427) ---------------------------------------
#
# The ``/decide`` handler still parses its body defensively (the raw-dict
# path is what guarantees our 422 taxonomy codes), but these models are
# the *documented* contract: they drive the generated OpenAPI schema,
# power ``hugrgate openapi``, and validate the request envelope before
# spec/policy parsing runs.


class DecideRequest(BaseModel):
    """Documented ``POST /decide`` request body (protocol v1)."""

    model_config = ConfigDict(extra="allow", json_schema_extra={
        "example": {
            "protocol_version": "1.0",
            "spec": {"type": "categorical", "options": ["a", "b"]},
            "state": {"signal": 0.7},
            "backend_name": None,
            "context": None,
            "policy": None,
        }})

    protocol_version: str | None = Field(
        default=None,
        description="Wire-protocol version; any 1.x is accepted.")
    spec: dict[str, Any] = Field(
        description="DecisionSpec JSON (see hugrgate.spec).")
    state: dict[str, Any] = Field(
        description="Feature state the decision is conditioned on.")
    backend_name: str | None = Field(
        default=None, description="Pin one backend by registry name.")
    context: dict[str, Any] | None = Field(
        default=None, description="Caller context (provenance, privacy).")
    policy: dict[str, Any] | None = Field(
        default=None, description="DecisionPolicy JSON.")


class ErrorBody(BaseModel):
    """Documented error envelope returned with 4xx/5xx statuses."""

    model_config = ConfigDict(json_schema_extra={
        "example": {"error": {"code": "spec_error",
                              "message": "categorical spec needs ≥2 options",
                              "recoverable": False, "details": {}}}})

    error: dict[str, Any]


class ProtocolBody(BaseModel):
    """Documented ``GET /protocol`` response body."""

    protocol_version: str = Field(description="Canonical protocol version.")
    supported_versions: list[str] = Field(
        description="Every protocol version this service accepts.")
    service_version: str = Field(description="HugrGate package version.")


def dump_openapi_schema() -> dict[str, Any]:
    """Return the stabilized OpenAPI schema for the service app.

    Used by ``hugrgate openapi`` and by the snapshot test; the schema
    is generated from the live route table so it can never drift from
    the implementation.

    The ``/decide`` handler reads the raw request body (so malformed
    envelopes get our taxonomy 422s instead of FastAPI's default
    422s), which means FastAPI cannot infer its request schema. We
    document it explicitly here with the *same*
    :class:`DecideRequest` model the handler validates against, so
    the published contract and the runtime validation are one
    object, not two.
    """
    schema = create_app().openapi()
    components = schema.setdefault("components", {}).setdefault(
        "schemas", {})
    components.setdefault(
        "DecideRequest",
        DecideRequest.model_json_schema(
            ref_template="#/components/schemas/{model}"))
    decide_op = schema["paths"]["/decide"]["post"]
    decide_op["requestBody"] = {
        "required": True,
        "content": {"application/json": {
            "schema": {"$ref": "#/components/schemas/DecideRequest"}}},
    }
    return schema


def _error_response(error: HugrGateError, status: int) -> JSONResponse:
    return JSONResponse(
        status_code=status,
        content={"error": {"code": error.code,
                           "message": error.message,
                           "recoverable": error.recoverable,
                           "details": error.details}},
    )


def create_app(gate: HugrGate | None = None,
               node: ClusterNode | None = None) -> FastAPI:
    """Create the FastAPI application serving ``gate``.

    When ``node`` is given, the ``/cluster/*`` routes are mounted so
    this process also serves as a cluster peer (slice 207). The import
    stays function-local so importing ``hugrgate.server`` never drags
    in the cluster stack unless it is used.
    """
    gate = gate or build_gate()
    app = FastAPI(title="HugrGate", version=HUGRGATE_VERSION)
    app.state.gate = gate
    started_at = time.time()

    # --- Request-ID propagation (slice 15, dusk Wave C) ----------------------
    #
    # Echo a client-supplied ``X-Request-ID`` back on the response; when
    # the client sent none, mint a uuid4 hex and report that instead.
    # The ID is stored on ``request.state`` for handlers and included
    # in the per-request log line (the service's access-log emission
    # point) so entries correlate across client, server, and logs.
    # Per the log-privacy rule: method/path/status/id only, never body.
    @app.middleware("http")
    async def request_id_middleware(request: Request, call_next) -> Any:
        request_id = request.headers.get(REQUEST_ID_HEADER) or uuid.uuid4().hex
        request.state.request_id = request_id
        response = await call_next(request)
        response.headers[REQUEST_ID_HEADER] = request_id
        logger.info("%s %s status=%d request_id=%s",
                    request.method, request.url.path,
                    response.status_code, request_id)
        return response

    @app.get("/", tags=["meta"], summary="Service identity",
              description="Returns the service name, package version, and "
                          "the HugrGate motto.")
    def root() -> dict[str, Any]:
        return {"service": "hugrgate", "version": HUGRGATE_VERSION,
                "motto": "Deterministic where possible. "
                         "Probabilistic where useful. "
                         "Generative only where necessary."}

    @app.get("/health", tags=["meta"], summary="Liveness probe",
              description="Never requires auth. Reports status, uptime, "
                          "registered backends, and decisions served.")
    def health() -> dict[str, Any]:
        return {"status": "ok", "version": HUGRGATE_VERSION,
                "backends": gate.registry.list(),
                "uptime_s": round(time.time() - started_at, 3),
                "decisions_served": gate.provenance.count()}

    @app.get("/backends", tags=["introspection"],
              summary="List registered backends",
              description="Capabilities, latency/cost estimates, "
                          "calibration, privacy properties, and health "
                          "for every registered backend.")
    def backends() -> list[dict[str, Any]]:
        infos = []
        for name in gate.registry.list():
            backend = gate.registry.get(name)
            if backend is None:  # defensive: list/get disagree
                continue
            infos.append({
                "name": backend.name,
                "is_remote": backend.is_remote,
                "capabilities": backend.capabilities(),
                "estimated_latency_ms": backend.estimated_latency(),
                "estimated_cost": backend.estimated_cost(),
                "calibration": backend.calibration_info(),
                "privacy": backend.privacy_properties(),
                "health": backend.health(),
            })
        return infos

    @app.get("/models", tags=["introspection"],
              summary="List known models",
              description="The model catalogue (see "
                          ":func:`register_model`).")
    def models() -> list[dict[str, Any]]:
        return [asdict(m) for m in list_models()]

    @app.get("/protocol", tags=["meta"], summary="Protocol advertisement",
              response_model=ProtocolBody,
              description="Advertise the wire-protocol versions this "
                          "service speaks (slice 426). Clients call this "
                          "first and fail fast on version skew.")
    def protocol() -> dict[str, Any]:
        """Advertise the wire-protocol versions this service speaks.

        Slice 426: clients call this first and fail fast on version
        skew instead of sending doomed requests.
        """
        return {
            "protocol_version": PROTOCOL_VERSION,
            "supported_versions": list(SUPPORTED_PROTOCOL_VERSIONS),
            "service_version": HUGRGATE_VERSION,
        }

    @app.post("/decide", tags=["decisions"], summary="Make a decision",
               description="Evaluate a spec against a state with an "
                           "optional policy. The request envelope is "
                           "validated against the documented schema "
                           "first; spec/policy problems return 422 "
                           "with a HugrGate taxonomy error code.",
               responses={400: {"model": ErrorBody,
                                 "description": "Malformed request envelope"},
                          422: {"model": ErrorBody,
                                "description": "Invalid spec, policy, or "
                                               "protocol version"},
                          502: {"model": ErrorBody,
                                "description": "Backend failure"},
                          503: {"model": ErrorBody,
                                "description": "No backend available"}})
    async def decide(request: Request) -> JSONResponse:
        """Make a decision.

        Success → the DecisionResult JSON directly (HTTP 200).
        Abstention → HTTP 200 with ``{"abstained": true, ...}``.
        Invalid envelope/spec/policy → 422; no backend → 503;
        backend failure → 502.
        """
        try:
            body = await request.json()
        except Exception:  # noqa: BLE001 - any parse failure is bad_request
            return JSONResponse(
                status_code=400,
                content={"error": {"code": "bad_request",
                                   "message": "request body must be JSON",
                                   "recoverable": True, "details": {}}})
        # Slice 427: validate the envelope against the documented
        # schema before any domain parsing, so malformed requests get
        # a structured 422 instead of an accidental 500.
        if not isinstance(body, dict):
            return JSONResponse(
                status_code=400,
                content={"error": {"code": "bad_request",
                                   "message": "request body must be a "
                                              "JSON object",
                                   "recoverable": True, "details": {}}})
        try:
            envelope = DecideRequest.model_validate(body)
        except ValidationError as e:
            return JSONResponse(
                status_code=422,
                content={"error": {"code": "bad_request",
                                   "message": "malformed decide request: "
                                   + "; ".join(
                                       f"{'.'.join(map(str, err['loc']))}: "
                                       f"{err['msg']}"
                                       for err in e.errors()),
                                   "recoverable": True, "details": {}}})
        # Slice 426: protocol-version negotiation runs before any
        # spec/policy parsing — skew is a caller bug, not a data bug.
        try:
            negotiated = negotiate_version(envelope.protocol_version)
        except ProtocolError as e:
            return _error_response(e, 422)
        try:
            spec = DecisionSpec.from_dict(envelope.spec)
        except KeyError:
            return _error_response(
                SpecError("request needs a 'spec' object"), 422)
        except (SpecError, TypeError, ValueError) as e:
            return _error_response(
                e if isinstance(e, HugrGateError)
                else SpecError(f"invalid spec: {e}"), 422)
        state = envelope.state
        policy = None
        if envelope.policy is not None:
            try:
                policy = policy_from_dict(envelope.policy)
            except (PolicyError, TypeError, ValueError, KeyError) as e:
                return _error_response(
                    e if isinstance(e, HugrGateError)
                    else PolicyError(f"invalid policy: {e}"), 422)
        backend_name = envelope.backend_name
        context = envelope.context
        try:
            result = gate.decide(state, spec, policy,
                                 context=context,
                                 backend_name=backend_name)
        except Abstention as e:
            return JSONResponse(
                status_code=200,
                content={"decision": None, "abstained": True,
                         "reason": e.reason, "message": e.message,
                         "code": e.code})
        except BackendUnavailable as e:
            return _error_response(e, 503)
        except BackendError as e:
            return _error_response(e, 502)
        except (SpecError, PolicyError) as e:
            return _error_response(e, 422)
        except HugrGateError as e:
            return _error_response(e, 500)
        result.metadata["protocol_version"] = negotiated
        return JSONResponse(status_code=200, content=result.to_dict())

    if node is not None:
        # Cluster peer mode (slice 207): mount /cluster/* routes.
        # Function-local import keeps hugrgate.server import-light.
        from hugrgate.cluster.routes import build_cluster_router
        app.include_router(build_cluster_router(node))

    return app


def run(host: str = "127.0.0.1", port: int = 8377,
        gate: HugrGate | None = None) -> None:
    """Serve the API. Binds localhost only unless told otherwise."""
    import uvicorn
    if host not in ("127.0.0.1", "::1", "localhost"):
        import warnings
        warnings.warn(
            f"HugrGate binding to non-localhost {host!r}; the API has no "
            f"authentication — only do this behind a trusted boundary.",
            stacklevel=2)
    uvicorn.run(create_app(gate), host=host, port=port, log_level="warning")
