"""Path traversal defenses. Slice 412.

Audit: file paths in HugrGate come from the operator (CLI args,
config) — no manifest-driven path joins were found in the runtime
pack loaders — but threat T-10 still wants a single choke point
wherever a user-influenced relative path meets the filesystem.
That choke point is :func:`safe_join`:

- null bytes are rejected outright;
- the joined path is fully resolved (``..`` segments *and*
  symlinks) and must stay inside the resolved root;
- anything else raises :class:`PathTraversalBlocked`.

The single invariant is *containment*: absolute paths are allowed
iff they resolve inside the root, because containment — not the
spelling — is the security property.

Integrated into :func:`hugrgate.security.checksums.verified_open`
(slice 406), the model-directory read boundary.
"""

from __future__ import annotations

import os
from pathlib import Path

from hugrgate.errors import PathTraversalBlocked

__all__ = [
    "is_within",
    "safe_join",
    "safe_read_text",
]


def is_within(root: str | Path, candidate: str | Path) -> bool:
    """True when ``candidate`` resolves inside ``root`` (symlinks too)."""
    root_real = os.path.realpath(root)
    cand_real = os.path.realpath(candidate)
    return cand_real == root_real or cand_real.startswith(root_real + os.sep)


def safe_join(root: str | Path, user_path: str | Path) -> Path:
    """Join ``user_path`` onto ``root``; raise unless contained.

    Raises :class:`PathTraversalBlocked` on null bytes, ``..``
    escapes, absolute-path escapes, and symlink escapes.
    """
    text = os.fspath(user_path)
    if "\x00" in text:
        raise PathTraversalBlocked(
            "null byte in path", path=text[:64])
    root_path = Path(root)
    # Resolve the root itself so the containment check compares
    # like with like even when root contains symlinks.
    resolved = Path(os.path.realpath(root_path / text))
    if not is_within(root_path, resolved):
        raise PathTraversalBlocked(
            f"path escapes its jail: {text[:128]!r}",
            path=text[:128], root=os.path.realpath(root_path))
    return resolved


def safe_read_text(root: str | Path, user_path: str | Path,
                   max_bytes: int = 1_000_000) -> str:
    """Read a jailed text file with a size cap."""
    path = safe_join(root, user_path)
    if not path.is_file():
        raise PathTraversalBlocked(
            f"not a file inside the jail: {os.fspath(user_path)[:128]!r}",
            path=os.fspath(user_path)[:128])
    data = path.read_bytes()
    if len(data) > max_bytes:
        raise PathTraversalBlocked(
            f"file exceeds {max_bytes} bytes", path=str(path),
            size=len(data))
    return data.decode("utf-8")
