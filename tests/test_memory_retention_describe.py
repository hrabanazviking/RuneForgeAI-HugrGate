"""Slice D5 — describe_quota: human-readable per-field quota description."""

from __future__ import annotations

from hugrgate.memory import MemoryQuota
from hugrgate.memory.retention import describe_quota


def test_describe_quota_set_limits():
    quota = MemoryQuota(max_episodes=1000, max_bytes=1_048_576,
                        warn_bytes=655_360)
    d = describe_quota(quota)
    assert d["max_episodes"] == {"value": 1000, "unit": "episodes"}
    assert d["max_bytes"] == {"value": 1_048_576, "unit": "bytes"}
    assert d["warn_bytes"] == {"value": 655_360, "unit": "bytes"}
    assert d["ttl_overrides"] == {
        "value": None, "unit": "seconds per privacy class",
        "unlimited": True,
    }


def test_describe_quota_unlimited_fields_marked():
    quota = MemoryQuota()
    d = describe_quota(quota)
    for field, unit in (("max_episodes", "episodes"),
                        ("max_bytes", "bytes"),
                        ("warn_bytes", "bytes")):
        assert d[field]["value"] is None
        assert d[field]["unit"] == unit
        assert d[field]["unlimited"] is True


def test_describe_quota_ttl_overrides():
    quota = MemoryQuota(ttl_overrides={"standard": 60.0, "public": None})
    d = describe_quota(quota)
    entry = d["ttl_overrides"]
    assert entry["unit"] == "seconds per privacy class"
    assert entry["value"] == {"standard": 60.0, "public": None}
    assert "unlimited" not in entry


def test_describe_quota_is_read_only():
    quota = MemoryQuota(max_episodes=50, max_bytes=1024)
    d = describe_quota(quota)
    d["max_episodes"]["value"] = 9999  # mutating the description...
    assert quota.max_episodes == 50  # ...must not affect the quota
    assert describe_quota(quota)["max_episodes"]["value"] == 50
