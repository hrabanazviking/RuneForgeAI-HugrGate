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
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Mapping, Optional

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from hugrgate import (
    Abstention,
    Backend,
    BackendError,
    BackendUnavailable,
    DecisionResult,
    DecisionSpec,
    HugrGate,
    PolicyError,
    SpecError,
)
from hugrgate import __version__ as HUGRGATE_VERSION
from hugrgate.client import policy_from_dict
from hugrgate.errors import HugrGateError

__all__ = [
    "UniformBackend",
    "KeywordBackend",
    "ModelInfo",
    "register_model",
    "list_models",
    "build_gate",
    "create_app",
    "run",
]

_WORD_RE = re.compile(r"[a-z0-9]+")


def _tokens(text: str) -> List[str]:
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


def _softmax(scores: Dict[str, float]) -> Dict[str, float]:
    maximum = max(scores.values())
    exps = {k: math.exp(v - maximum) for k, v in scores.items()}
    total = sum(exps.values())
    return {k: v / total for k, v in exps.items()}


def _normalized_entropy(dist: Dict[str, float]) -> float:
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

    def capabilities(self) -> Dict[str, Any]:
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
                 context: Optional[Mapping[str, Any]] = None
                 ) -> DecisionResult:
        if spec.type == "numeric":
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

    def capabilities(self) -> Dict[str, Any]:
        return {
            "spec_types": ["categorical", "binary", "ordinal"],
            "description": "Keyword overlap + softmax baseline.",
            "deterministic": True,
        }

    def supports(self, spec: DecisionSpec) -> bool:
        return spec.type in ("categorical", "binary", "ordinal")

    def _label_keywords(self, spec: DecisionSpec) -> Dict[str, set]:
        if spec.type == "binary":
            return {
                "true": set(_tokens(spec.statement or "")),
                "false": set(),
            }
        labels = spec.value_space()
        return {label: set(_tokens(label)) for label in labels}

    def evaluate(self, state: Mapping[str, Any], spec: DecisionSpec,
                 context: Optional[Mapping[str, Any]] = None
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
    spec_types: List[str] = field(default_factory=list)
    description: str = ""
    trained_at: Optional[str] = None
    metrics: Dict[str, Any] = field(default_factory=dict)


_MODEL_CATALOG: List[ModelInfo] = [
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


def list_models() -> List[ModelInfo]:
    return list(_MODEL_CATALOG)


def build_gate(extra_backends: Optional[List[Backend]] = None) -> HugrGate:
    """Build a :class:`HugrGate` wired with the built-in backends."""
    gate = HugrGate()
    gate.register(UniformBackend())
    gate.register(KeywordBackend())
    for backend in extra_backends or []:
        gate.register(backend)
    return gate


def _error_response(error: HugrGateError, status: int) -> JSONResponse:
    return JSONResponse(
        status_code=status,
        content={"error": {"code": error.code,
                           "message": error.message,
                           "recoverable": error.recoverable,
                           "details": error.details}},
    )


def create_app(gate: Optional[HugrGate] = None) -> FastAPI:
    """Create the FastAPI application serving ``gate``."""
    gate = gate or build_gate()
    app = FastAPI(title="HugrGate", version=HUGRGATE_VERSION)
    app.state.gate = gate
    started_at = time.time()

    @app.get("/")
    def root() -> Dict[str, Any]:
        return {"service": "hugrgate", "version": HUGRGATE_VERSION,
                "motto": "Deterministic where possible. "
                         "Probabilistic where useful. "
                         "Generative only where necessary."}

    @app.get("/health")
    def health() -> Dict[str, Any]:
        return {"status": "ok", "version": HUGRGATE_VERSION,
                "backends": gate.registry.list(),
                "uptime_s": round(time.time() - started_at, 3),
                "decisions_served": gate.provenance.count()}

    @app.get("/backends")
    def backends() -> List[Dict[str, Any]]:
        infos = []
        for name in gate.registry.list():
            backend = gate.registry.get(name)
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

    @app.get("/models")
    def models() -> List[Dict[str, Any]]:
        return [asdict(m) for m in list_models()]

    @app.post("/decide")
    async def decide(request: Request) -> JSONResponse:
        """Make a decision.

        Success → the DecisionResult JSON directly (HTTP 200).
        Abstention → HTTP 200 with ``{"abstained": true, ...}``.
        Invalid spec/policy → 422; no backend → 503; backend failure → 502.
        """
        try:
            body = await request.json()
        except Exception:
            return JSONResponse(
                status_code=400,
                content={"error": {"code": "bad_request",
                                   "message": "request body must be JSON",
                                   "recoverable": True, "details": {}}})
        try:
            spec = DecisionSpec.from_dict(body["spec"])
        except KeyError:
            return _error_response(
                SpecError("request needs a 'spec' object"), 422)
        except (SpecError, TypeError, ValueError) as e:
            return _error_response(
                e if isinstance(e, HugrGateError)
                else SpecError(f"invalid spec: {e}"), 422)
        state = body.get("state")
        if not isinstance(state, dict):
            return _error_response(
                SpecError("request needs a 'state' object"), 422)
        policy = None
        if body.get("policy") is not None:
            try:
                policy = policy_from_dict(body["policy"])
            except (PolicyError, TypeError, ValueError, KeyError) as e:
                return _error_response(
                    e if isinstance(e, HugrGateError)
                    else PolicyError(f"invalid policy: {e}"), 422)
        backend_name = body.get("backend_name")
        context = body.get("context")
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
        return JSONResponse(status_code=200, content=result.to_dict())

    return app


def run(host: str = "127.0.0.1", port: int = 8377,
        gate: Optional[HugrGate] = None) -> None:
    """Serve the API. Binds localhost only unless told otherwise."""
    import uvicorn
    if host not in ("127.0.0.1", "::1", "localhost"):
        import warnings
        warnings.warn(
            f"HugrGate binding to non-localhost {host!r}; the API has no "
            f"authentication — only do this behind a trusted boundary.")
    uvicorn.run(create_app(gate), host=host, port=port, log_level="warning")
