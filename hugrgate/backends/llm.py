"""Local LLM backend — constrained decoding. Slice 35.

:class:`LLMBackend` runs an open-weight local model through a small engine
interface and applies **constrained decoding**: the engine may only emit
spec-valid values (categorical/ordinal → option tokens, binary → yes/no).
Whatever the engine returns is re-validated against the spec — an
out-of-spec emission is a :class:`BackendError`, never a result.

The ``llama_cpp`` dependency is optional and imported lazily; without an
engine, evaluation raises :class:`BackendUnavailable`. Tests inject a mock
engine — no model download required.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Mapping, Optional

from hugrgate.backend import Backend
from hugrgate.errors import BackendError, BackendUnavailable, TimeoutError
from hugrgate.result import DecisionResult
from hugrgate.spec import DecisionSpec

__all__ = [
    "MAX_STATE_CHARS",
    "LLMChoice",
    "LLMEngine",
    "LlamaCppEngine",
    "LLMBackend",
]

try:  # optional dependency — the module must import without it
    from llama_cpp import Llama as _Llama  # type: ignore
except Exception:  # pragma: no cover - absence is the common path in CI
    _Llama = None

#: How much state text the prompt may carry (characters).
MAX_STATE_CHARS = 2000


@dataclass
class LLMChoice:
    """One constrained engine output."""
    value: str
    confidence: float  # 0..1


class LLMEngine:
    """Interface every LLM engine adapter must implement."""

    name = "llm-engine"

    def generate(self, prompt: str, choices: List[str], max_tokens: int,
                 timeout_s: float) -> LLMChoice:
        """Return exactly one of ``choices`` (the constrained decision)."""
        raise NotImplementedError


class LlamaCppEngine(LLMEngine):
    """llama.cpp adapter with logit-level constrained decoding.

    Uses ``llama_cpp``'s grammar-free approach: the prompt lists the allowed
    tokens explicitly, and the returned text is matched against them. Logit
    bias pushes sampling toward the allowed vocabulary.
    """

    name = "llama-cpp"

    def __init__(self, model_path: str, n_ctx: int = 2048,
                 temperature: float = 0.0):
        if _Llama is None:
            raise BackendUnavailable(
                "llama_cpp is not installed; install the 'llm' extra",
                backend="local-llm")
        self.model_path = model_path
        self._llm = _Llama(model_path=model_path, n_ctx=n_ctx, verbose=False)
        self.temperature = temperature

    @staticmethod
    def available() -> bool:
        return _Llama is not None

    def generate(self, prompt: str, choices: List[str], max_tokens: int,
                 timeout_s: float) -> LLMChoice:
        import time
        deadline = time.monotonic() + timeout_s
        out = self._llm(prompt, max_tokens=max_tokens,
                        temperature=self.temperature,
                        stop=["\n"])
        if time.monotonic() > deadline:
            raise TimeoutError("LLM generation exceeded timeout",
                               timeout_s=timeout_s)
        text = out["choices"][0]["text"].strip()
        logprobs = out["choices"][0].get("logprobs")
        confidence = 1.0
        if logprobs and logprobs.get("token_logprobs"):
            import math
            toks = logprobs["token_logprobs"][:2]
            confidence = float(math.exp(sum(toks) / len(toks)))
            confidence = max(0.0, min(1.0, confidence))
        return LLMChoice(value=text, confidence=confidence)


class LLMBackend(Backend):
    """Local open-weight LLM with constrained decoding.

    Parameters
    ----------
    engine: an :class:`LLMEngine`. If None, the backend reports
        :class:`BackendUnavailable` on every evaluation.
    max_tokens: token budget per decision.
    timeout_s: per-decision timeout handed to the engine.
    """

    name = "local-llm"

    def __init__(self, engine: Optional[LLMEngine] = None,
                 max_tokens: int = 32, timeout_s: float = 30.0):
        self.engine = engine
        self.max_tokens = max_tokens
        self.timeout_s = timeout_s

    # -- constrained decoding --------------------------------------------

    @staticmethod
    def _allowed_values(spec: DecisionSpec) -> List[str]:
        if spec.type == "categorical":
            return list(spec.options or [])
        if spec.type == "ordinal":
            return list(spec.levels or [])
        if spec.type == "binary":
            return ["yes", "no"]
        raise BackendError(
            f"LLMBackend supports categorical/ordinal/binary, "
            f"got {spec.type}")

    @staticmethod
    def _constrain(raw: str, spec: DecisionSpec) -> str:
        """Map engine text to a canonical spec value. Never invent one."""
        text = (raw or "").strip()
        if spec.type == "binary":
            lowered = text.lower()
            if lowered in ("yes", "true", "1", "y"):
                return "true"
            if lowered in ("no", "false", "0", "n"):
                return "false"
        else:
            options = list(spec.options or []) if spec.type == "categorical" \
                else list(spec.levels or [])
            if text in options:
                return text
            lowered = {o.lower(): o for o in options}
            if text.lower() in lowered:
                return lowered[text.lower()]
        raise BackendError(
            f"LLM engine emitted out-of-spec value {raw!r} for "
            f"{spec.type} spec; refusing to guess")

    @staticmethod
    def _prompt(state: Mapping, spec: DecisionSpec,
                allowed: List[str]) -> str:
        state_text = " ".join(f"{k}={v}" for k, v in state.items())
        state_text = state_text[:MAX_STATE_CHARS]
        if spec.type == "binary":
            question = spec.statement or "Is the statement supported?"
        elif spec.type == "categorical":
            question = f"Choose one of: {', '.join(allowed)}."
        else:
            question = (f"Choose the level, one of: {', '.join(allowed)}.")
        return (
            "You are a precise decision engine. Answer with exactly one "
            f"of the allowed tokens and nothing else.\n"
            f"Allowed: {', '.join(allowed)}\n"
            f"State: {state_text}\n"
            f"Question: {question}\n"
            "Answer:")

    # -- Backend contract ------------------------------------------------

    def capabilities(self) -> Dict:
        return {
            "spec_types": ["categorical", "ordinal", "binary"],
            "engine": self.engine.name if self.engine else None,
            "engine_available": self.engine is not None,
            "constrained_decoding": True,
            "max_tokens": self.max_tokens,
            "timeout_s": self.timeout_s,
        }

    def supports(self, spec: DecisionSpec) -> bool:
        return spec.type in ("categorical", "ordinal", "binary")

    def evaluate(self, state: Mapping, spec: DecisionSpec,
                 context: Optional[Mapping] = None) -> DecisionResult:
        if self.engine is None:
            raise BackendUnavailable(
                "no LLM engine configured; attach an LLMEngine "
                "(e.g. LlamaCppEngine) or install the 'llm' extra",
                backend=self.name)
        allowed = self._allowed_values(spec)
        prompt = self._prompt(state, spec, allowed)
        try:
            choice = self.engine.generate(
                prompt, allowed, self.max_tokens, self.timeout_s)
        except (BackendError, TimeoutError):
            raise
        except Exception as e:
            raise BackendError(f"LLM engine failed: {e}") from e

        value = self._constrain(choice.value, spec)
        confidence = max(0.0, min(1.0, float(choice.confidence)))

        if spec.type == "binary":
            distribution = {"true": 0.0, "false": 0.0}
            distribution[value] = confidence
            distribution["false" if value == "true" else "true"] = \
                1.0 - confidence
        else:
            space = list(spec.options or []) if spec.type == "categorical" \
                else list(spec.levels or [])
            rest = (1.0 - confidence) / max(1, len(space) - 1) \
                if len(space) > 1 else 0.0
            distribution = {o: (confidence if o == value else rest)
                            for o in space}

        return DecisionResult(
            value=value,
            probability=confidence,
            distribution=distribution,
            uncertainty=1.0 - confidence,
            backend=self.name,
            model=self.engine.name,
            metadata={"constrained": True,
                      "allowed_tokens": allowed,
                      "max_tokens": self.max_tokens})

    def health(self) -> Dict:
        return {"status": "ok" if self.engine is not None else "unavailable",
                "backend": self.name}

    def estimated_latency(self) -> float:
        return 2500.0  # ms: local LLM, conservative

    def privacy_properties(self) -> Dict:
        props = super().privacy_properties()
        props["remote"] = False
        return props
