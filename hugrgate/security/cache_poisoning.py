"""Cache-poisoning defenses. Slice 417.

Attack result against :class:`DecisionCache`: the key bound
state+spec+policy, but *not* the tenant or the model generation —
so two tenants sharing a cache, or two model versions behind one
backend name, could read each other's entries (threat T-05). The
fix (in ``hugrgate/cache.py`` and the sealed cache): optional
``namespace`` / ``model_version`` key bindings, defaulting to the
historical behavior.

This module provides:

- :class:`BoundCache` — a cache view with namespace and model
  version pinned: callers cannot forget to pass them.
- :func:`run_poison_suite` — the adversarial battery: cross-tenant
  reads, stale-model reads, type confusion, policy separation,
  and in-memory tamper eviction, each measured as
  contained-or-not.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from hugrgate.cache import DecisionCache
from hugrgate.policy import DecisionPolicy
from hugrgate.result import DecisionResult
from hugrgate.spec import DecisionSpec

__all__ = [
    "BoundCache",
    "PoisonReport",
    "run_poison_suite",
]


class BoundCache:
    """A :class:`DecisionCache` with namespace/version pinned.

    All reads and writes carry the bindings, so a tenant or model
    generation can neither poison nor read another's entries.
    """

    def __init__(self, cache: DecisionCache, *, namespace: str,
                 model_version: str = "") -> None:
        if not namespace:
            raise ValueError("BoundCache requires a non-empty namespace")
        self._cache = cache
        self._namespace = namespace
        self._model_version = model_version

    @property
    def namespace(self) -> str:
        return self._namespace

    @property
    def model_version(self) -> str:
        return self._model_version

    def get(self, state: Mapping[str, Any], spec: DecisionSpec,
            policy: DecisionPolicy) -> DecisionResult | None:
        return self._cache.get(state, spec, policy,
                               namespace=self._namespace,
                               model_version=self._model_version)

    def put(self, state: Mapping[str, Any], spec: DecisionSpec,
            policy: DecisionPolicy,
            result: DecisionResult) -> bool:
        return self._cache.put(state, spec, policy, result,
                               namespace=self._namespace,
                               model_version=self._model_version)

    def invalidate_backend(self, backend_name: str) -> int:
        return self._cache.invalidate_backend(backend_name)


@dataclass
class PoisonReport:
    attack: str
    contained: bool
    detail: str = ""


def _spec(options: tuple[str, ...] = ("yes", "no")) -> DecisionSpec:
    return DecisionSpec(type="categorical", options=list(options))


def _result(value: str, backend: str = "b") -> DecisionResult:
    return DecisionResult(value=value, probability=0.9,
                          backend=backend, model="m")


def run_poison_suite() -> list[PoisonReport]:
    """Attack a shared cache five ways; every attack must be contained."""
    reports: list[PoisonReport] = []
    policy = DecisionPolicy()
    state = {"x": 1}

    # 1. Cross-tenant read: tenant B must not see tenant A's entry.
    shared: DecisionCache = DecisionCache()
    tenant_a = BoundCache(shared, namespace="tenant-a")
    tenant_b = BoundCache(shared, namespace="tenant-b")
    tenant_a.put(state, _spec(), policy, _result("yes"))
    reports.append(PoisonReport(
        "cross_tenant_read",
        contained=tenant_b.get(state, _spec(), policy) is None,
        detail="B reads A's key"))

    # 2. Stale model: v2 must not be served v1's entry.
    shared2: DecisionCache = DecisionCache()
    v1 = BoundCache(shared2, namespace="t", model_version="1")
    v2 = BoundCache(shared2, namespace="t", model_version="2")
    v1.put(state, _spec(), policy, _result("old"))
    hit = v2.get(state, _spec(), policy)
    reports.append(PoisonReport(
        "stale_model_serving",
        contained=hit is None,
        detail="v2 must miss v1's entry"))

    # 3. Type confusion: same state, different spec type must miss.
    shared3: DecisionCache = DecisionCache()
    bound = BoundCache(shared3, namespace="t")
    bound.put(state, _spec(), policy, _result("yes"))
    other = DecisionSpec(type="numeric", minimum=0.0, maximum=1.0)
    reports.append(PoisonReport(
        "spec_type_confusion",
        contained=bound.get({"x": 1}, other, policy) is None,
        detail="categorical entry must not serve numeric spec"))

    # 4. Policy separation: different policy must miss.
    strict = DecisionPolicy(minimum_probability=0.99)
    reports.append(PoisonReport(
        "policy_separation",
        contained=bound.get(state, _spec(), strict) is None,
        detail="entry keyed under a different policy"))

    # 5. In-memory tamper: a corrupted entry is evicted, never served.
    cache = DecisionCache()
    poisoned = BoundCache(cache, namespace="t")
    poisoned.put(state, _spec(), policy, _result("yes"))
    for entry in cache._entries.values():
        entry.result.value = "forged"  # white-box memory tamper
    reports.append(PoisonReport(
        "memory_tamper_eviction",
        contained=poisoned.get(state, _spec(), policy) is None
        and cache.corruptions == 1,
        detail="forged entry evicted, miss returned"))

    return reports
