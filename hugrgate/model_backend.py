"""Small-fast-model judgment backend — Tviheimr readiness slice HG-T2.

Roadmap: a local-model backend for the judgments rules/classifiers
cannot settle, using a small fast model served locally through an
Ollama-shaped endpoint. The model pick is by benchmark (latency +
judgment accuracy on a fixed case set), recorded with numbers in
``campaign/hg_t2_benchmark_report.json`` (see
``benchmarks/hg_t2_benchmark.py``).

Design rules, all enforced in code:

- **Rules first.** :class:`SelectiveModelBackend` runs the deterministic
  primary backend (keyword classifier by default) on every judgment.
- **Model only where it earns its cost.** The model is consulted ONLY
  when the primary result is low-confidence (probability below
  ``CONFIDENCE_THRESHOLD`` or top-two margin below
  ``MARGIN_THRESHOLD``) — exactly the cases the benchmark case set
  shows the rules cannot settle. Confident rules verdicts never pay
  model latency.
- **Model failure never breaks judgment.** If the endpoint is down,
  times out, or emits an out-of-spec value, the primary verdict is
  returned with ``model_error`` recorded in its metadata.
- **Honest confidence.** Ollama's generate endpoint returns no
  calibrated probability, so :class:`OllamaEngine` reports the fixed,
  documented ``UNCALIBRATED_CONFIDENCE`` and the backend metadata
  says ``confidence_calibrated: False``. No invented precision.

Stdlib only (urllib), like the HG-T1 decision server: this must run
anywhere HugrGate runs. Plain process / library code — no service
form is assumed or created.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from collections.abc import Mapping
from typing import Any

from hugrgate.backend import Backend
from hugrgate.backends.llm import LLMBackend, LLMChoice, LLMEngine
from hugrgate.decision_server import KeywordBackend
from hugrgate.errors import BackendError, BackendUnavailable
from hugrgate.result import DecisionResult
from hugrgate.spec import DecisionSpec

__all__ = [
    "CONFIDENCE_THRESHOLD",
    "MARGIN_THRESHOLD",
    "UNCALIBRATED_CONFIDENCE",
    "OllamaEngine",
    "SelectiveModelBackend",
    "build_model_backend",
    "needs_model",
]

#: Primary verdicts at/above this probability stay rules-only.
CONFIDENCE_THRESHOLD = 0.55
#: Primary verdicts whose top-two distribution margin is below this
#: are unsettled even if the top probability clears the threshold.
MARGIN_THRESHOLD = 0.20
#: Ollama generate returns no calibrated probability; this fixed value
#: is reported instead, flagged uncalibrated in backend metadata.
UNCALIBRATED_CONFIDENCE = 0.6

DEFAULT_BASE_URL = "http://127.0.0.1:11434"
DEFAULT_MODEL = "gemma4viking4b:latest"


class OllamaEngine(LLMEngine):
    """LLMEngine over an Ollama-shaped local endpoint (stdlib urllib).

    ``generate()`` POSTs to ``{base_url}/api/generate`` with
    temperature 0 and a tiny token budget; the reply text is returned
    as the choice. Requests set ``think: False``: thinking models
    otherwise spend the whole judgment token budget on hidden
    reasoning and return an empty answer (measured on
    gemma4viking4b, HG-T2 benchmark). Spec-constraining is
    LLMBackend's job, as with
    every engine. Any transport failure raises BackendUnavailable /
    BackendError — never a fabricated choice.
    """

    name = "ollama"

    def __init__(self, model: str = DEFAULT_MODEL,
                 base_url: str = DEFAULT_BASE_URL,
                 timeout_s: float = 60.0):
        self.model = model
        self.base_url = base_url.rstrip("/")
        self.timeout_s = timeout_s
        self.name = f"ollama:{model}"

    def _request(self, method: str, path: str,
                 body: dict[str, Any] | None = None,
                 timeout_s: float | None = None) -> dict[str, Any]:
        data = json.dumps(body).encode() if body is not None else None
        req = urllib.request.Request(
            f"{self.base_url}{path}", data=data, method=method)
        if data is not None:
            req.add_header("Content-Type", "application/json")
        try:
            with urllib.request.urlopen(
                    req, timeout=timeout_s or self.timeout_s) as resp:
                return json.loads(resp.read().decode())
        except (urllib.error.URLError, OSError, ValueError) as e:
            raise BackendUnavailable(
                f"ollama endpoint {self.base_url} unreachable: {e}",
                backend="ollama") from e

    def list_models(self) -> list[str]:
        tags = self._request("GET", "/api/tags", timeout_s=5.0)
        return [m.get("name", "") for m in tags.get("models", [])]

    def health(self) -> dict[str, Any]:
        try:
            models = self.list_models()
        except BackendUnavailable as e:
            return {"status": "unavailable", "error": str(e)}
        return {"status": "ok", "model": self.model,
                "model_present": self.model in models,
                "models": models}

    def generate(self, prompt: str, choices: list[str], max_tokens: int,
                 timeout_s: float) -> LLMChoice:
        reply = self._request("POST", "/api/generate", {
            "model": self.model, "prompt": prompt, "stream": False,
            "think": False,
            "options": {"temperature": 0.0,
                        "num_predict": max(4, max_tokens)},
        }, timeout_s=timeout_s)
        text = str(reply.get("response") or "").strip()
        if not text:
            raise BackendError("ollama returned an empty response")
        # First token only: the constrained answer, not the essay.
        value = text.split()[0].strip(".,:;\"'")
        return LLMChoice(value=value,
                         confidence=UNCALIBRATED_CONFIDENCE)


def needs_model(result: DecisionResult) -> bool:
    """True when the primary backend did not settle the judgment."""
    if result.probability < CONFIDENCE_THRESHOLD:
        return True
    dist = sorted(result.distribution.values(), reverse=True)
    if len(dist) >= 2 and (dist[0] - dist[1]) < MARGIN_THRESHOLD:
        return True
    return False


class SelectiveModelBackend(Backend):
    """Rules-first backend that escalates unsettled cases to a model.

    ``primary`` is any deterministic Backend (keyword by default);
    ``model_backend`` is an LLMBackend (OllamaEngine by default via
    :func:`build_model_backend`). Every result carries routing
    metadata: ``route`` is ``rules``, ``model``, or
    ``rules-fallback`` (model was needed but failed/unavailable).
    """

    name = "model-assisted"

    def __init__(self, primary: Backend | None = None,
                 model_backend: LLMBackend | None = None):
        self.primary = primary or KeywordBackend()
        self.model_backend = model_backend or build_model_backend()

    def capabilities(self) -> dict[str, Any]:
        return {
            "spec_types": ["categorical", "binary", "ordinal"],
            "primary": self.primary.name,
            "model_backend": self.model_backend.name,
            "model_engine": (self.model_backend.engine.name
                             if self.model_backend.engine else None),
            "selective": True,
            "confidence_threshold": CONFIDENCE_THRESHOLD,
            "margin_threshold": MARGIN_THRESHOLD,
            "confidence_calibrated": False,
        }

    def supports(self, spec: DecisionSpec) -> bool:
        return self.primary.supports(spec) and \
            self.model_backend.supports(spec)

    def evaluate(self, state: Mapping[str, Any], spec: DecisionSpec,
                 context: Mapping[str, Any] | None = None
                 ) -> DecisionResult:
        primary_result = self.primary.evaluate(state, spec, context)
        if not needs_model(primary_result):
            primary_result.metadata = {
                **primary_result.metadata, "route": "rules",
                "model_used": False,
                "slice": "HG-T2"}
            return primary_result
        try:
            model_result = self.model_backend.evaluate(
                state, spec, context)
        except Exception as e:  # noqa: BLE001 - fallback is the contract
            primary_result.metadata = {
                **primary_result.metadata, "route": "rules-fallback",
                "model_used": False,
                "model_error": f"{type(e).__name__}: {e}",
                "slice": "HG-T2"}
            return primary_result
        model_result.metadata = {
            **model_result.metadata, "route": "model",
            "model_used": True,
            "rules_value": primary_result.value,
            "rules_probability": primary_result.probability,
            "confidence_calibrated": False,
            "slice": "HG-T2"}
        return model_result

    def health(self) -> dict[str, Any]:
        engine = self.model_backend.engine
        model_health = (engine.health()  # type: ignore[attr-defined]
                        if isinstance(engine, OllamaEngine)
                        else {"status": "unknown"})
        return {"status": "ok", "backend": self.name,
                "primary": self.primary.health(),
                "model": model_health}

    def estimated_latency(self) -> float:
        # Rules path dominates; model path is the rare exception.
        return self.primary.estimated_latency()


def build_model_backend(model: str = DEFAULT_MODEL,
                        base_url: str = DEFAULT_BASE_URL
                        ) -> LLMBackend:
    """An LLMBackend backed by a local Ollama-shaped endpoint."""
    return LLMBackend(engine=OllamaEngine(model=model,
                                          base_url=base_url))
