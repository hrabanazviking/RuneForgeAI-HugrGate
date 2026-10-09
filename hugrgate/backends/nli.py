"""NLI backend — statement entailment as a binary decision. Slice 34.

:class:`NLIBackend` answers one question: *is the spec's statement supported
by the state?* A natural-language-inference model scores
``P(entailment | premise, statement)`` and that becomes the probability of
``"true"``. Constrained to ``binary`` specs only.

The ``transformers`` dependency is optional and imported lazily: without it
(or without a model/engine), evaluation raises :class:`BackendUnavailable`
instead of failing at import time. Tests inject a plain callable
``nli_fn(premise, statement) -> float`` — no downloads required.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping

from hugrgate.backend import Backend
from hugrgate.errors import BackendError, BackendUnavailable
from hugrgate.result import DecisionResult
from hugrgate.spec import DecisionSpec

__all__ = [
    "PREMISE_FIELDS",
    "NLIBackend",
]

try:  # optional dependency — the module must import without it
    from transformers import pipeline as _hf_pipeline
except Exception:  # noqa: BLE001 - any import failure means 'no nli'
    _hf_pipeline = None

#: State keys inspected (in order) for the premise text.
PREMISE_FIELDS = ("premise", "text", "message", "content", "input")


class NLIBackend(Backend):
    """Binary decisions via natural-language inference.

    Parameters
    ----------
    nli_fn: ``(premise, statement) -> float`` entailment probability.
        Injected directly in tests and offline environments.
    model_name: Hugging Face zero-shot model used when ``nli_fn`` is not
        given. Loaded lazily on first use; requires ``transformers`` and
        (once) a network download.
    """

    name = "nli"

    def __init__(self,
                 nli_fn: Callable[[str, str], float] | None = None,
                 model_name: str = "facebook/bart-large-mnli"):
        self.nli_fn = nli_fn
        self.model_name = model_name
        self._pipe = None
        self._engine_error: str | None = None

    # -- engine ----------------------------------------------------------

    @staticmethod
    def engine_available() -> bool:
        """Whether the optional transformers dependency is installed."""
        return _hf_pipeline is not None

    def _ensure_engine(self) -> None:
        if self.nli_fn is not None or self._pipe is not None:
            return
        if _hf_pipeline is None:
            self._engine_error = (
                "transformers is not installed; install the 'nli' extra or "
                "inject nli_fn=(premise, statement) -> float")
            raise BackendUnavailable(self._engine_error,
                                     backend=self.name)
        try:
            self._pipe = _hf_pipeline("zero-shot-classification",
                                      model=self.model_name)
        except Exception as e:
            self._engine_error = f"could not load NLI model: {e}"
            raise BackendUnavailable(self._engine_error,
                                     backend=self.name) from e

    def _entailment(self, premise: str, statement: str) -> float:
        if self.nli_fn is not None:
            try:
                p = float(self.nli_fn(premise, statement))
            except Exception as e:
                raise BackendError(f"nli_fn failed: {e}") from e
            if not 0.0 <= p <= 1.0:
                raise BackendError(
                    f"nli_fn returned out-of-range probability: {p}")
            return p
        self._ensure_engine()
        pipe = self._pipe
        if pipe is None:  # defensive: _ensure_engine raises on failure
            raise BackendUnavailable("NLI engine unavailable",
                                     backend=self.name)
        try:
            out = pipe(premise, candidate_labels=[statement],
                       hypothesis_template="{}")
            return float(out["scores"][0])
        except BackendError:
            raise
        except Exception as e:
            raise BackendError(f"NLI inference failed: {e}") from e

    # -- Backend contract ------------------------------------------------

    def capabilities(self) -> dict:
        return {
            "spec_types": ["binary"],
            "engine": "injected" if self.nli_fn is not None else "transformers",
            "engine_available": self.nli_fn is not None or self.engine_available(),
            "model": self.model_name,
        }

    def supports(self, spec: DecisionSpec) -> bool:
        return spec.type == "binary"

    def _premise(self, state: Mapping) -> str:
        for key in PREMISE_FIELDS:
            value = state.get(key)
            if isinstance(value, str) and value.strip():
                return value
        return " ".join(str(v) for v in state.values())

    def evaluate(self, state: Mapping, spec: DecisionSpec,
                 context: Mapping | None = None) -> DecisionResult:
        if spec.type != "binary":
            raise BackendError(
                f"NLIBackend is constrained to binary specs, got {spec.type}")
        premise = self._premise(state)
        p_entail = self._entailment(premise, spec.statement or "")
        value = "true" if p_entail >= 0.5 else "false"
        return DecisionResult(
            value=value,
            probability=p_entail if value == "true" else 1.0 - p_entail,
            distribution={"true": p_entail, "false": 1.0 - p_entail},
            uncertainty=1.0 - abs(p_entail - 0.5) * 2.0,
            backend=self.name,
            model=self.model_name if self.nli_fn is None else "injected-fn",
            metadata={"entailment_probability": round(p_entail, 4)})

    def health(self) -> dict:
        ready = self.nli_fn is not None or self.engine_available()
        status = "ok" if ready else "unavailable"
        info: dict = {"status": status, "backend": self.name}
        if self._engine_error:
            info["error"] = self._engine_error
        return info

    def estimated_latency(self) -> float:
        return 5.0 if self.nli_fn is not None else 800.0
