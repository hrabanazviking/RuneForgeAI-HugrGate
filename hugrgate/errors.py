"""Error taxonomy for HugrGate. Slice 10."""

from __future__ import annotations

__all__ = [
    "HugrGateError",
    "SpecError",
    "PolicyError",
    "BackendError",
    "BackendUnavailable",
    "CalibrationError",
    "TimeoutError",
    "PrivacyViolation",
    "Abstention",
]


class HugrGateError(Exception):
    """Base for all HugrGate errors."""
    code = "hugrgate_error"
    recoverable = True

    def __init__(self, message: str = "", **details):
        super().__init__(message)
        self.message = message
        self.details = details


class SpecError(HugrGateError):
    code = "spec_error"
    recoverable = False


class PolicyError(HugrGateError):
    code = "policy_error"
    recoverable = False


class BackendError(HugrGateError):
    code = "backend_error"
    recoverable = True


class BackendUnavailable(BackendError):
    code = "backend_unavailable"
    recoverable = True


class CalibrationError(HugrGateError):
    code = "calibration_error"
    recoverable = True


class TimeoutError(BackendError):
    code = "timeout"
    recoverable = True


class PrivacyViolation(HugrGateError):
    code = "privacy_violation"
    recoverable = False


class Abstention(HugrGateError):
    """Raised when the gate abstains — not an error, a decision."""
    code = "abstention"
    recoverable = True

    def __init__(self, message: str = "insufficient confidence",
                 reason: str = "below_threshold", **details):
        super().__init__(message, reason=reason, **details)
        self.reason = reason
