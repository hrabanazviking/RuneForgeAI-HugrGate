"""Agent Nervous System (Campaign XVI) — notification gating.

Slice 382.  An agentic loop that notifies on everything notifies
about nothing — operators go blind and paging budgets burn.
:class:`NotificationGate` is the single choke point for
outbound notifications:

- per-channel :class:`ChannelConfig`: enable/disable, minimum
  severity, per-minute rate limit;
- severity ladder shared with the observability alerting layer
  (:data:`hugrgate.observability.alerts.SEVERITIES`) — one
  vocabulary for "how urgent is this" across the system;
- dedup keys suppress repeat notifications inside a window (the
  escalation policy in slice 384 re-fires through here, so a
  flapping agent pages once, not fifty times);
- every decision is recorded with a machine-readable reason and
  per-channel stats.

``notify()`` decides; a pluggable ``sender`` callable performs the
actual delivery (the gate never touches the network — same
separation as the memory gates).
"""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from hugrgate.agents.types import AgentSignal
from hugrgate.observability.alerts import SEVERITIES

__all__ = [
    "NOTIFY_REASONS",
    "ChannelConfig",
    "Notification",
    "NotificationGate",
    "NotifyDecision",
]

#: Machine-readable notify decision reasons.
NOTIFY_REASONS: tuple[str, ...] = (
    "sent",
    "channel_unknown",
    "channel_disabled",
    "severity_filtered",
    "duplicate",
    "rate_limited",
    "sender_failed",
)

_SEVERITY_RANK = {s: i for i, s in enumerate(SEVERITIES)}


@dataclass(frozen=True)
class Notification:
    """One outbound notification request."""

    channel: str
    title: str
    body: str = ""
    severity: str = "info"
    dedup_key: str = ""
    trace_id: str = ""

    def __post_init__(self) -> None:
        if not self.channel or not self.channel.strip():
            raise ValueError("channel must be non-empty")
        if not self.title or not self.title.strip():
            raise ValueError("title must be non-empty")
        if self.severity not in _SEVERITY_RANK:
            raise ValueError(f"unknown severity {self.severity!r}")


@dataclass(frozen=True)
class ChannelConfig:
    """Delivery policy for one channel."""

    rate_per_minute: int = 10
    min_severity: str = "info"
    enabled: bool = True
    dedup_window_s: float = 300.0

    def __post_init__(self) -> None:
        if self.rate_per_minute < 1:
            raise ValueError("rate_per_minute must be >= 1")
        if self.min_severity not in _SEVERITY_RANK:
            raise ValueError(f"unknown severity {self.min_severity!r}")
        if self.dedup_window_s < 0:
            raise ValueError("dedup_window_s must be >= 0")


@dataclass(frozen=True)
class NotifyDecision:
    """Outcome of a notify request."""

    sent: bool
    reason: str
    channel: str
    severity: str


class _Bucket:
    def __init__(self, rate_per_s: float, capacity: int,
                 clock: Callable[[], float]) -> None:
        self._rate = rate_per_s
        self._capacity = capacity
        self._clock = clock
        self._tokens = float(capacity)
        self._last = clock()

    def take(self) -> bool:
        now = self._clock()
        self._tokens = min(
            float(self._capacity),
            self._tokens + (now - self._last) * self._rate,
        )
        self._last = now
        if self._tokens >= 1.0:
            self._tokens -= 1.0
            return True
        return False


class NotificationGate:
    """Decides whether a notification goes out, and sends it."""

    def __init__(
        self,
        *,
        sender: Callable[[Notification], None] | None = None,
        bus: Any = None,
        clock: Callable[[], float] | None = None,
    ) -> None:
        self._sender = sender or (lambda n: None)
        self._bus = bus
        self._clock = clock or time.monotonic
        self._channels: dict[str, ChannelConfig] = {}
        self._buckets: dict[str, _Bucket] = {}
        self._dedup: dict[tuple[str, str], float] = {}
        self._stats: dict[str, Any] = {
            "requests": 0, "sent": 0, "suppressed": 0,
            "by_reason": {r: 0 for r in NOTIFY_REASONS},
            "by_channel": {},
        }

    def configure(self, channel: str, config: ChannelConfig) -> None:
        """Install (or replace) a channel's delivery policy."""
        if not channel or not channel.strip():
            raise ValueError("channel must be non-empty")
        self._channels[channel] = config
        self._buckets.pop(channel, None)  # reset rate state on reconfig

    def notify(self, notification: Notification) -> NotifyDecision:
        """Gate and (via sender) deliver one notification."""
        self._stats["requests"] += 1
        now = self._clock()

        def decide(reason: str, sent: bool = False) -> NotifyDecision:
            decision = NotifyDecision(
                sent=sent, reason=reason,
                channel=notification.channel,
                severity=notification.severity,
            )
            self._record(decision)
            return decision

        config = self._channels.get(notification.channel)
        if config is None:
            return decide("channel_unknown")
        if not config.enabled:
            return decide("channel_disabled")
        if _SEVERITY_RANK[notification.severity] < \
                _SEVERITY_RANK[config.min_severity]:
            return decide("severity_filtered")
        if notification.dedup_key:
            seen = self._dedup.get(
                (notification.channel, notification.dedup_key)
            )
            if seen is not None and now - seen < config.dedup_window_s:
                return decide("duplicate")
        bucket = self._buckets.get(notification.channel)
        if bucket is None:
            bucket = _Bucket(
                rate_per_s=config.rate_per_minute / 60.0,
                capacity=config.rate_per_minute,
                clock=self._clock,
            )
            self._buckets[notification.channel] = bucket
        if not bucket.take():
            return decide("rate_limited")
        try:
            self._sender(notification)
        except Exception:  # noqa: BLE001 - sender failure is a decision
            return decide("sender_failed")
        if notification.dedup_key:
            self._dedup[(notification.channel, notification.dedup_key)] = now
        if self._bus is not None:
            self._bus.publish(AgentSignal(
                topic="notify.sent",
                payload={"channel": notification.channel,
                         "severity": notification.severity,
                         "title": notification.title[:120]},
                priority="low",
                trace_id=notification.trace_id,
                source="notify",
            ))
        return decide("sent", sent=True)

    def _record(self, decision: NotifyDecision) -> None:
        if decision.sent:
            self._stats["sent"] += 1
        else:
            self._stats["suppressed"] += 1
        self._stats["by_reason"][decision.reason] += 1
        by_ch = self._stats["by_channel"]
        ch = by_ch.setdefault(decision.channel,
                              {"sent": 0, "suppressed": 0})
        ch["sent" if decision.sent else "suppressed"] += 1

    def stats(self) -> dict[str, Any]:
        """Cumulative gate counters (copy)."""
        import copy

        return copy.deepcopy(self._stats)

