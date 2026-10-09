"""Memory privacy controls. Slice 315.

Episodes carry privacy classes; this module decides *who may see
what*. :class:`MemoryAccessPolicy` maps roles to permissions over the
privacy ladder:

- ``owner`` — the runtime itself: full read/write, every class;
- ``analyst`` — reads up to ``sensitive``; ``sensitive`` episodes are
  returned with metadata and tags stripped (outcome *kinds* stay —
  aggregates are the analyst's job); no writes;
- ``auditor`` — reads up to ``standard``; ``standard`` episodes are
  metadata-stripped; no writes.

:class:`GuardedHistory` wraps a history with a role: reads are
filtered and redacted, writes raise :class:`MemoryAccessDenied` for
non-owners. Views are deep copies — redaction can never leak through
a held reference, and mutating a view cannot touch the store.

Denied reads raise; they never return a partial episode silently.
"""

from __future__ import annotations

import copy
from dataclasses import dataclass
from typing import Any

from hugrgate.errors import MemoryAccessDenied
from hugrgate.memory.query import MemoryQuery
from hugrgate.memory.types import EpisodeLike, HistoryLike
from hugrgate.privacy import PRIVACY_CLASS_ORDER, at_least, class_rank

__all__ = [
    "ROLE_PERMISSIONS",
    "GuardedHistory",
    "MemoryAccessPolicy",
    "RolePermission",
]

#: Known roles.
ROLES = ("owner", "analyst", "auditor")


@dataclass(frozen=True)
class RolePermission:
    """What a role may do."""

    #: Most sensitive privacy class the role may read.
    max_class: str
    #: Classes at/above this are metadata-stripped on read (None: never).
    redact_at: str | None
    #: Whether the role may record/attach/clear.
    write: bool


#: Default role table (see module docstring for the rationale).
ROLE_PERMISSIONS: dict[str, RolePermission] = {
    "owner": RolePermission(max_class="forbidden", redact_at=None,
                            write=True),
    "analyst": RolePermission(max_class="sensitive", redact_at="sensitive",
                              write=False),
    "auditor": RolePermission(max_class="standard", redact_at="standard",
                              write=False),
}


def _check_role(role: str) -> RolePermission:
    permission = ROLE_PERMISSIONS.get(role)
    if permission is None:
        raise ValueError(
            f"unknown role: {role!r}; expected one of {sorted(ROLES)}")
    return permission


class MemoryAccessPolicy:
    """Role-based read/write policy over episode privacy classes."""

    def __init__(self,
                 permissions: dict[str, RolePermission] | None = None
                 ) -> None:
        self._permissions = dict(permissions) if permissions is not None \
            else dict(ROLE_PERMISSIONS)
        for role, permission in self._permissions.items():
            if role not in ROLES:
                raise ValueError(f"unknown role in policy: {role!r}")
            if permission.max_class not in PRIVACY_CLASS_ORDER:
                raise ValueError(
                    f"bad max_class for role {role!r}: "
                    f"{permission.max_class!r}")
            if (permission.redact_at is not None
                    and permission.redact_at not in PRIVACY_CLASS_ORDER):
                raise ValueError(
                    f"bad redact_at for role {role!r}: "
                    f"{permission.redact_at!r}")

    def permission_for(self, role: str) -> RolePermission:
        """Return the permission record for ``role`` (``ValueError``)."""
        permission = self._permissions.get(role)
        if permission is None:
            raise ValueError(
                f"unknown role: {role!r}; expected one of "
                f"{sorted(self._permissions)}")
        return permission

    def may_read(self, role: str, privacy_class: str) -> bool:
        """True when ``role`` may read the privacy class at all."""
        permission = self.permission_for(role)
        return class_rank(privacy_class) <= class_rank(permission.max_class)

    def check_read(self, role: str, episode: EpisodeLike) -> EpisodeLike:
        """Return a (possibly redacted) readable copy of ``episode``.

        Raises :class:`MemoryAccessDenied` when the role may not read
        the episode's privacy class.
        """
        permission = self.permission_for(role)
        if not self.may_read(role, episode.privacy_class):
            raise MemoryAccessDenied(
                f"role {role!r} may not read "
                f"{episode.privacy_class!r} episodes",
                role=role, privacy_class=episode.privacy_class)
        view = copy.deepcopy(episode)
        if (permission.redact_at is not None
                and at_least(episode.privacy_class, permission.redact_at)):
            view.record.metadata = {}
            view.tags = ()
            view.annotations = {
                k: v for k, v in view.annotations.items()
                if k in ("redacted", "redact_rule")}
        return view

    def check_write(self, role: str, operation: str) -> None:
        """Raise :class:`MemoryAccessDenied` unless ``role`` may write."""
        permission = self.permission_for(role)
        if not permission.write:
            raise MemoryAccessDenied(
                f"role {role!r} may not perform {operation!r}",
                role=role, operation=operation)


class GuardedHistory:
    """A role-scoped view over a history.

    Reads filter by privacy class and redact where the policy says so;
    every mutating operation requires the ``owner`` role. The wrapped
    history is never exposed.
    """

    def __init__(self, history: HistoryLike, role: str,
                 policy: MemoryAccessPolicy | None = None) -> None:
        self._history = history
        self._role = role
        self._policy = policy if policy is not None else MemoryAccessPolicy()
        self._policy.permission_for(role)  # validate eagerly

    @property
    def role(self) -> str:
        return self._role

    # -- reads ------------------------------------------------------

    def get(self, episode_id: str) -> EpisodeLike:
        return self._policy.check_read(
            self._role, self._history.get(episode_id))

    def recent(self, n: int = 10) -> list[EpisodeLike]:
        """The ``n`` most recent episodes the role may read."""
        if n < 0:
            raise ValueError(f"recent(n) needs n >= 0, got {n}")
        if n == 0:
            return []
        # find() sorts recorded_at descending: walk newest-first and
        # take the first n readable episodes.
        out: list[EpisodeLike] = []
        for episode in self._history.find(MemoryQuery()):
            if self._policy.may_read(self._role, episode.privacy_class):
                out.append(self._policy.check_read(self._role, episode))
                if len(out) == n:
                    break
        return out

    def find(self, query: MemoryQuery) -> list[EpisodeLike]:
        return [self._policy.check_read(self._role, e)
                for e in self._history.find(query)
                if self._policy.may_read(self._role, e.privacy_class)]

    def count(self) -> int:
        """Number of episodes the role may read (not the store total)."""
        return sum(1 for _ in self.find(MemoryQuery()))

    def by_request_hash(self, request_hash: str) -> list[EpisodeLike]:
        episodes = self._history.by_request_hash(request_hash)
        return [self._policy.check_read(self._role, e) for e in episodes
                if self._policy.may_read(self._role, e.privacy_class)]

    # -- writes (owner only) ----------------------------------------

    def record(self, *args: Any, **kwargs: Any) -> Any:
        self._policy.check_write(self._role, "record")
        return self._history.record(*args, **kwargs)

    def attach_outcome(self, *args: Any, **kwargs: Any) -> Any:
        self._policy.check_write(self._role, "attach_outcome")
        return self._history.attach_outcome(*args, **kwargs)

    def attach_ground_truth(self, *args: Any, **kwargs: Any) -> Any:
        self._policy.check_write(self._role, "attach_ground_truth")
        return self._history.attach_ground_truth(*args, **kwargs)

    def clear(self) -> Any:
        self._policy.check_write(self._role, "clear")
        return self._history.clear()
