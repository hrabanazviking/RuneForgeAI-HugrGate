"""Dusk slice D2 — cache-errors-taxonomy.

The two bare ``ValueError`` raises in ``DecisionCache.__init__`` were
migrated to ``CacheConfigError`` (a ``PolicyError`` + ``ValueError``
dual-inheritance class, following the RoutingError precedent), so
existing ``except ValueError`` callers keep working while the HugrGate
taxonomy carries the structured code/details.
"""

import ast
import pathlib

import pytest

from hugrgate.cache import DecisionCache
from hugrgate.errors import (
    CacheConfigError,
    HugrGateError,
    PolicyError,
)


def test_cache_config_error_in_taxonomy():
    assert issubclass(CacheConfigError, PolicyError)
    assert issubclass(CacheConfigError, HugrGateError)
    assert issubclass(CacheConfigError, ValueError)  # catch-compat
    assert CacheConfigError.code == "cache_config_error"
    assert CacheConfigError.recoverable is False


def test_bad_ttl_raises_cache_config_error():
    with pytest.raises(CacheConfigError) as exc_info:
        DecisionCache(ttl_seconds=0)
    assert "ttl_seconds must be positive" in str(exc_info.value)
    assert exc_info.value.code == "cache_config_error"


def test_bad_max_size_raises_cache_config_error():
    with pytest.raises(CacheConfigError) as exc_info:
        DecisionCache(max_size=0)
    assert "max_size must be >= 1" in str(exc_info.value)


def test_valueerror_catch_compat_preserved():
    # Existing callers doing ``except ValueError`` keep working.
    with pytest.raises(ValueError):
        DecisionCache(ttl_seconds=-1.0)
    with pytest.raises(ValueError):
        DecisionCache(max_size=-5)


def test_valid_config_still_works():
    cache = DecisionCache(ttl_seconds=60.0, max_size=10)
    assert cache.ttl_seconds == 60.0
    assert cache.max_size == 10


def test_no_bare_valueerror_raises_remain_in_cache_module():
    path = pathlib.Path(__file__).resolve().parent.parent / "hugrgate" / "cache.py"
    tree = ast.parse(path.read_text(encoding="utf-8"))
    bare = [
        node.lineno
        for node in ast.walk(tree)
        if isinstance(node, ast.Raise)
        and isinstance(node.exc, ast.Call)
        and getattr(node.exc.func, "id", "") == "ValueError"
    ]
    assert bare == [], f"bare ValueError raises remain at lines {bare}"
