"""FastFlowLM (NPU) judgment engine — HugrGate NPU Phase 2.

Roadmap: the same selective small-fast-model judgment path as
HG-T2 (:mod:`hugrgate.model_backend`), with the model served on the
XDNA2 NPU by FastFlowLM (``flm serve``) instead of a GPU Ollama
endpoint. FastFlowLM is the only NPU LLM runtime proven on the
deployment host (purpleraider: qwen3:0.6b at 81.96 tok/s, 2026-11-12);
it is a tool we *use* through its OpenAI-shaped HTTP API, never a
codebase we build on (its accelerated kernels are proprietary
binaries). The benchmark that re-earns the judge pick on the frozen
HG-T2 case set lives in ``benchmarks/hg_npu_benchmark.py``; its
report is ``campaign/hg_npu_benchmark_report.json``.

Design rules, inherited from HG-T2 and enforced in code:

- **Rules first, unchanged.** This module adds one engine behind the
  existing :class:`SelectiveModelBackend`; the rules layer and the
  selective thresholds are exactly as HG-T2 left them.
- **Model failure never breaks judgment.** Any transport failure
  raises :class:`BackendUnavailable` / :class:`BackendError`, and
  the selective backend returns the rules verdict with
  ``model_error`` recorded — the NPU can vanish mid-call and the
  gate degrades to rules-only, never to silence.
- **Honest confidence.** ``flm serve`` returns per-token
  ``logprobs`` on request. When the first generated token carries a
  logprob, :class:`FlmEngine` reports that token's real probability
  (``exp(logprob)``) as the choice confidence — a genuine model
  probability for the token actually emitted, though not a
  calibrated distribution over the choice set. When logprobs are
  absent, it falls back to the documented
  ``UNCALIBRATED_CONFIDENCE`` of :mod:`hugrgate.model_backend`.
  No invented precision either way.

Stdlib only (urllib), like HG-T1/HG-T2: this must run anywhere
HugrGate runs. Plain library code — the resident service form is
the owner's explicit commission, authored outside this module
(``tools/hugrgate_resident.py``).
"""

from __future__ import annotations

import json
import math
import urllib.error
import urllib.request
from typing import Any

from hugrgate.backends.llm import LLMBackend, LLMChoice, LLMEngine
from hugrgate.errors import BackendError, BackendUnavailable
from hugrgate.model_backend import UNCALIBRATED_CONFIDENCE

__all__ = [
    "DEFAULT_FLM_BASE_URL",
    "DEFAULT_FLM_MODEL",
    "FlmEngine",
    "build_flm_backend",
]

#: ``flm serve`` default port (``flm port``), loopback by default.
DEFAULT_FLM_BASE_URL = "http://127.0.0.1:52625"
#: The control candidate: the model proven on this NPU since
#: 2026-11-12. The resident judge pick is set by benchmark + config,
#: never assumed here.
DEFAULT_FLM_MODEL = "qwen3:0.6b"


class FlmEngine(LLMEngine):
    """LLMEngine over a FastFlowLM ``flm serve`` endpoint (stdlib).

    ``generate()`` POSTs to ``{base_url}/v1/chat/completions`` with
    the HG-T2 prompt as a single user message, temperature 0, and
    ``logprobs`` requested so the emitted token carries its real
    probability. ``flm serve`` hosts exactly one model (the one it
    was started with); ``model`` must name it. Spec-constraining is
    LLMBackend's job, as with every engine. Any transport failure
    raises BackendUnavailable / BackendError — never a fabricated
    choice.
    """

    name = "flm"

    def __init__(self, model: str = DEFAULT_FLM_MODEL,
                 base_url: str = DEFAULT_FLM_BASE_URL,
                 timeout_s: float = 60.0):
        self.model = model
        self.base_url = base_url.rstrip("/")
        self.timeout_s = timeout_s
        self.name = f"flm:{model}"

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
                f"flm endpoint {self.base_url} unreachable: {e}",
                backend="flm") from e

    def list_models(self) -> list[str]:
        reply = self._request("GET", "/v1/models", timeout_s=5.0)
        return [str(m.get("id", "")) for m in reply.get("data", [])]

    def health(self) -> dict[str, Any]:
        try:
            models = self.list_models()
        except BackendUnavailable as e:
            return {"status": "unavailable", "error": str(e)}
        return {"status": "ok", "model": self.model,
                "model_present": self.model in models,
                "models": models}

    @staticmethod
    def _confidence(choice: dict[str, Any]) -> float:
        """Real first-token probability when logprobs are present.

        ``exp(logprob)`` of the first generated token is the model's
        own probability for the token it emitted. Absent or malformed
        logprobs fall back to the documented uncalibrated constant —
        reported as-is, never dressed up as a measurement.
        """
        try:
            content = (choice.get("logprobs") or {}).get("content") \
                or []
            if content:
                lp = float(content[0]["logprob"])
                return max(0.0, min(1.0, math.exp(lp)))
        except (KeyError, TypeError, ValueError):
            pass
        return UNCALIBRATED_CONFIDENCE

    def generate(self, prompt: str, choices: list[str],
                 max_tokens: int, timeout_s: float) -> LLMChoice:
        reply = self._request("POST", "/v1/chat/completions", {
            "model": self.model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.0,
            "max_tokens": max(4, max_tokens),
            "logprobs": True,
            "top_logprobs": 5,
        }, timeout_s=timeout_s)
        options = reply.get("choices") or []
        if not options:
            raise BackendError("flm returned no choices")
        first = options[0]
        text = str((first.get("message") or {}).get("content")
                   or "").strip()
        if not text:
            raise BackendError("flm returned an empty response")
        # First token only: the constrained answer, not the essay.
        value = text.split()[0].strip(".,:;\"'")
        return LLMChoice(value=value,
                         confidence=self._confidence(first))


def build_flm_backend(model: str = DEFAULT_FLM_MODEL,
                      base_url: str = DEFAULT_FLM_BASE_URL
                      ) -> LLMBackend:
    """An LLMBackend backed by a local FastFlowLM (NPU) endpoint."""
    return LLMBackend(engine=FlmEngine(model=model,
                                       base_url=base_url))
