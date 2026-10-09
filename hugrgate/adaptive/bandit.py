"""Contextual bandit adapter. Slice 130.

The learning heart of adaptive routing: :class:`ContextualBanditAdapter`
maps router context features (slice 129) to a choice of backend arm using
**LinUCB** - one ridge-regression model per arm, with an upper-confidence
bound that explores arms whose reward is uncertain.

Design decisions:

- **Pure standard library.** Feature dimensions here are small (tens),
  so the linear solves use Gaussian elimination with partial pivoting
  instead of numpy. This keeps the adaptive package importable on the
  base install, honoring the repo's stdlib-only contract.
- **Deterministic.** No randomness inside the adapter: given the same
  weights and features, ``select`` returns the same arm. Exploration
  policy (epsilon schedules, kill switches) lives in slice 141.
- **Serializable.** :meth:`to_dict` / :meth:`from_dict` round-trip the
  full learned state, which is what policy versioning (slice 146) and
  rollback (slice 145) checkpoint.
- **Numerically guarded.** The ridge term keeps every ``A`` matrix
  positive-definite; the solver raises
  :class:`~hugrgate.errors.BackendError` on a singular system rather
  than returning garbage.

The adapter does not know about backends, policies, or telemetry - it
learns ``features -> reward`` per named arm. Wiring (propensities,
objectives, safety) is layered on top by slices 131-142.
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from hugrgate.errors import BackendError, SpecError

__all__ = [
    "BanditDecision",
    "ContextualBanditAdapter",
]


@dataclass(frozen=True)
class BanditDecision:
    """The adapter's choice for one context."""

    arm: str
    expected_reward: float
    ucb: float
    per_arm: dict[str, float]  # arm -> UCB score at decision time

    def to_dict(self) -> dict[str, Any]:
        return {
            "arm": self.arm,
            "expected_reward": self.expected_reward,
            "ucb": self.ucb,
            "per_arm": dict(self.per_arm),
        }


def _solve(a: list[list[float]], b: list[float]) -> list[float]:
    """Solve ``a x = b`` by Gaussian elimination with partial pivoting."""
    n = len(a)
    if n == 0:
        raise BackendError("cannot solve an empty linear system")
    if any(len(row) != n for row in a) or len(b) != n:
        raise BackendError("linear system has inconsistent dimensions")
    # Augmented matrix.
    m = [[*a[i], b[i]] for i in range(n)]
    for col in range(n):
        pivot = max(range(col, n), key=lambda r: abs(m[r][col]))
        if abs(m[pivot][col]) < 1e-12:
            raise BackendError(
                "singular bandit matrix: ridge regularization failed")
        m[col], m[pivot] = m[pivot], m[col]
        piv = m[col][col]
        for row in range(col + 1, n):
            factor = m[row][col] / piv
            if factor == 0.0:
                continue
            for k in range(col, n + 1):
                m[row][k] -= factor * m[col][k]
    x = [0.0] * n
    for i in range(n - 1, -1, -1):
        s = m[i][n] - sum(m[i][j] * x[j] for j in range(i + 1, n))
        if abs(m[i][i]) < 1e-12:
            raise BackendError("singular bandit matrix in back-substitution")
        x[i] = s / m[i][i]
    return x


def _dot(u: Sequence[float], v: Sequence[float]) -> float:
    return sum(a * b for a, b in zip(u, v, strict=True))


class _ArmState:
    """Ridge-regression sufficient statistics for one arm."""

    __slots__ = ("A", "b", "n", "reward_sum")

    def __init__(self, dim: int, ridge: float) -> None:
        self.A = [[ridge if i == j else 0.0 for j in range(dim)]
                  for i in range(dim)]
        self.b = [0.0] * dim
        self.n = 0
        self.reward_sum = 0.0


@dataclass
class _ScoredArm:
    name: str
    expected: float
    ucb: float


class ContextualBanditAdapter:
    """LinUCB contextual bandit over named backend arms."""

    def __init__(self, feature_names: Sequence[str], *,
                 alpha: float = 1.0, ridge: float = 1.0) -> None:
        names = list(feature_names)
        if not names:
            raise SpecError("bandit needs at least one feature name")
        if len(set(names)) != len(names):
            raise SpecError(f"duplicate feature names: {names}")
        if alpha < 0:
            raise SpecError(f"alpha must be >= 0, got {alpha}")
        if ridge <= 0:
            raise SpecError(f"ridge must be > 0, got {ridge}")
        self.feature_names = names
        self.dim = len(names)
        self.alpha = alpha
        self.ridge = ridge
        self._arms: dict[str, _ArmState] = {}

    # -- core API -------------------------------------------------------

    def _vector(self, features: Mapping[str, float]) -> list[float]:
        try:
            vec = [float(features[name]) for name in self.feature_names]
        except KeyError as exc:
            raise SpecError(
                f"bandit features missing column {exc}; expected "
                f"{self.feature_names}") from exc
        if any(not math.isfinite(v) for v in vec):
            raise SpecError("bandit features must be finite")
        return vec

    def _arm(self, name: str) -> _ArmState:
        arm = self._arms.get(name)
        if arm is None:
            arm = _ArmState(self.dim, self.ridge)
            self._arms[name] = arm
        return arm

    def _theta(self, arm: _ArmState) -> list[float]:
        return _solve([row[:] for row in arm.A], list(arm.b))

    def _score(self, name: str, vec: list[float]) -> _ScoredArm:
        arm = self._arm(name)
        theta = self._theta(arm)
        expected = _dot(theta, vec)
        # x^T A^{-1} x via an auxiliary solve.
        a_inv_x = _solve([row[:] for row in arm.A], list(vec))
        width = math.sqrt(max(_dot(vec, a_inv_x), 0.0))
        return _ScoredArm(name, expected, expected + self.alpha * width)

    def select(self, features: Mapping[str, float],
               arms: Sequence[str]) -> BanditDecision:
        """Choose the arm with the highest UCB. Ties break by arm name."""
        arm_list = list(arms)
        if not arm_list:
            raise SpecError("bandit select needs at least one arm")
        if len(set(arm_list)) != len(arm_list):
            raise SpecError(f"duplicate arms: {arm_list}")
        vec = self._vector(features)
        scored = [self._score(name, vec) for name in arm_list]
        scored.sort(key=lambda s: (-s.ucb, s.name))
        best = scored[0]
        return BanditDecision(
            arm=best.name,
            expected_reward=best.expected,
            ucb=best.ucb,
            per_arm={s.name: s.ucb for s in scored},
        )

    def update(self, arm: str, features: Mapping[str, float],
               reward: float, weight: float = 1.0) -> None:
        """Fold one observed reward into the arm's model."""
        if not math.isfinite(reward):
            raise SpecError(f"bandit reward must be finite, got {reward}")
        if not math.isfinite(weight) or weight <= 0:
            raise SpecError(f"bandit weight must be positive, got {weight}")
        vec = self._vector(features)
        state = self._arm(arm)
        for i in range(self.dim):
            for j in range(self.dim):
                state.A[i][j] += weight * vec[i] * vec[j]
            state.b[i] += weight * reward * vec[i]
        state.n += 1
        state.reward_sum += reward

    def seed_prior(self, arm: str, mean: Sequence[float],
                   strength: float = 1.0) -> None:
        """Cold-start an arm toward a prior mean vector (slice 140).

        Equivalent to ``strength`` pseudo-observations of ``mean`` at the
        unit feature vector's scale: ``b = strength * mean`` while ``A``
        keeps its ridge shape, so real data quickly dominates.
        """
        if len(mean) != self.dim:
            raise SpecError(
                f"prior mean has dim {len(mean)}, expected {self.dim}")
        if not math.isfinite(strength) or strength <= 0:
            raise SpecError(
                f"prior strength must be positive, got {strength}")
        state = self._arm(arm)
        for i in range(self.dim):
            if not math.isfinite(mean[i]):
                raise SpecError("prior mean must be finite")
            state.b[i] += strength * float(mean[i])

    # -- introspection --------------------------------------------------

    def arm_stats(self, arm: str) -> dict[str, Any]:
        state = self._arms.get(arm)
        if state is None:
            return {"arm": arm, "n": 0, "mean_reward": 0.0}
        return {
            "arm": arm,
            "n": state.n,
            "mean_reward": (state.reward_sum / state.n) if state.n else 0.0,
        }

    def arms(self) -> list[str]:
        return sorted(self._arms)

    def expected_reward(self, arm: str,
                        features: Mapping[str, float]) -> float:
        return self._score(arm, self._vector(features)).expected

    # -- persistence ----------------------------------------------------

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": "adaptive-bandit/v1",
            "feature_names": list(self.feature_names),
            "alpha": self.alpha,
            "ridge": self.ridge,
            "arms": {
                name: {
                    "A": [list(row) for row in st.A],
                    "b": list(st.b),
                    "n": st.n,
                    "reward_sum": st.reward_sum,
                }
                for name, st in self._arms.items()
            },
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> ContextualBanditAdapter:
        if data.get("schema") != "adaptive-bandit/v1":
            raise SpecError(
                f"unsupported bandit schema {data.get('schema')!r}")
        adapter = cls(data["feature_names"],
                      alpha=float(data.get("alpha", 1.0)),
                      ridge=float(data.get("ridge", 1.0)))
        for name, st in data.get("arms", {}).items():
            arm = _ArmState(adapter.dim, adapter.ridge)
            arm.A = [list(map(float, row)) for row in st["A"]]
            arm.b = list(map(float, st["b"]))
            arm.n = int(st["n"])
            arm.reward_sum = float(st["reward_sum"])
            adapter._arms[name] = arm
        return adapter
