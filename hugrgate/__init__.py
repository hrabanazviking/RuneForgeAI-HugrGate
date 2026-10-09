"""HugrGate — local-first, model-agnostic probabilistic decision runtime.

Deterministic where possible. Probabilistic where useful.
Generative only where necessary.
"""

from hugrgate.backend import Backend, BackendRegistry
from hugrgate.core import HugrGate
from hugrgate.errors import (
    Abstention,
    BackendError,
    BackendUnavailable,
    CalibrationError,
    GGUFError,
    HugrGateError,
    PolicyError,
    PrivacyViolation,
    QueueFull,
    SpecError,
    TimeoutError,
)
from hugrgate.policy import DecisionPolicy
from hugrgate.result import DecisionResult
from hugrgate.spec import DecisionSpec

__version__ = "1.0.0"
__all__ = [
    "Abstention",
    "Backend",
    "BackendError",
    "BackendRegistry",
    "BackendUnavailable",
    "CalibrationError",
    "DecisionPolicy",
    "DecisionResult",
    "DecisionSpec",
    "GGUFError",
    "HugrGate",
    "HugrGateError",
    "PolicyError",
    "PrivacyViolation",
    "QueueFull",
    "SpecError",
    "TimeoutError",
]
