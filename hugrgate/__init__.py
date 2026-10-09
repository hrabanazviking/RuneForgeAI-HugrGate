"""HugrGate — local-first, model-agnostic probabilistic decision runtime.

Deterministic where possible. Probabilistic where useful.
Generative only where necessary.
"""

from hugrgate.spec import DecisionSpec
from hugrgate.result import DecisionResult
from hugrgate.policy import DecisionPolicy
from hugrgate.backend import Backend, BackendRegistry
from hugrgate.core import HugrGate
from hugrgate.errors import (
    HugrGateError, SpecError, PolicyError, BackendError,
    BackendUnavailable, CalibrationError, TimeoutError,
    PrivacyViolation, QueueFull, Abstention,
)

__version__ = "0.1.0"
__all__ = [
    "DecisionSpec", "DecisionResult", "DecisionPolicy",
    "Backend", "BackendRegistry", "HugrGate",
    "HugrGateError", "SpecError", "PolicyError", "BackendError",
    "BackendUnavailable", "CalibrationError", "TimeoutError",
    "PrivacyViolation", "QueueFull", "Abstention",
]
