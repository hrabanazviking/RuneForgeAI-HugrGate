"""Filesystem fault simulation. Slices 259-260.

Deterministic disk-failure simulation for code that touches the
filesystem, without needing a real full (or read-only) disk:

- :func:`disk_full` (259) — every ``open()`` for writing raises
  ``OSError`` with ``errno.ENOSPC`` ("No space left on device");
  reads pass through untouched;
- :func:`read_only` (260) — every ``open()`` for writing raises
  ``OSError`` with ``errno.EROFS`` ("Read-only file system").

Both are implemented by patching :func:`builtins.open` for the
duration of the context. They are single-threaded test tools, not
production mechanisms: while active, *all* write-opens in the
process fail, which is exactly the blast radius a full disk has.

The production contract they verify: HugrGate storage code maps
these ``OSError``s to the taxonomy's :class:`StorageError` (see
``hugrgate/edge/storage.py`` — buffer retained, torn temp files
cleaned up), never letting a raw ``OSError`` escape.
"""

from __future__ import annotations

import builtins
import contextlib
import errno
import os
from collections.abc import Callable, Iterator
from typing import Any
from unittest import mock

__all__ = [
    "disk_full",
    "read_only",
]

_WRITE_MODE_CHARS = frozenset("wax+")


def _is_write_mode(mode: str) -> bool:
    return any(c in _WRITE_MODE_CHARS for c in mode)


def _faulty_open_factory(errno_code: int,
                          real_open: Callable[..., Any]) -> Callable[..., Any]:
    def faulty_open(file: Any, mode: str = "r", *args: Any,
                    **kwargs: Any) -> Any:
        if _is_write_mode(mode):
            # Attribute form, like cluster/chaos.py's httpx.ConnectError:
            # this raise IS the simulated OS failure. It must stay a
            # genuine OSError so storage code's OSError->StorageError
            # mapping is exercised; a taxonomy error here would defeat
            # the simulation.
            raise builtins.OSError(errno_code, os.strerror(errno_code),
                                   str(file))
        return real_open(file, mode, *args, **kwargs)
    return faulty_open


@contextlib.contextmanager
def disk_full(errno_code: int = errno.ENOSPC) -> Iterator[None]:
    """Simulate a full disk: write-opens raise ``OSError(ENOSPC)``.

    Reads (and opens in read-only modes) behave normally, so the
    simulation distinguishes "cannot write" from "cannot read".
    """
    real_open = builtins.open
    with mock.patch("builtins.open",
                    _faulty_open_factory(errno_code, real_open)):
        yield


@contextlib.contextmanager
def read_only(errno_code: int = errno.EROFS) -> Iterator[None]:
    """Simulate a read-only filesystem: write-opens raise
    ``OSError(EROFS)``. Reads behave normally."""
    real_open = builtins.open
    with mock.patch("builtins.open",
                    _faulty_open_factory(errno_code, real_open)):
        yield
