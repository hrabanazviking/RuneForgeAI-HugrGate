"""Slice 14 — config-explain.

``explain_daemon_config`` reports every known daemon config key with
its effective value and where that value came from: the config file
or the daemon defaults.
"""

from __future__ import annotations

import pytest

from hugrgate.configgen import explain_daemon_config
from hugrgate.errors import ConfigError


def _write(path, text):
    path.write_text(text, encoding="utf-8")
    return path


def test_explain_daemon_config_source_attribution(tmp_path):
    """Sample config with two keys set: those report 'file',
    everything else reports 'default' with the default value."""
    cfg = _write(tmp_path / "hugrgate.yaml",
                 "host: 0.0.0.0\nport: 9999\n")
    explained = explain_daemon_config(cfg)
    assert explained["host"] == {"value": "0.0.0.0", "source": "file"}
    assert explained["port"] == {"value": 9999, "source": "file"}
    assert explained["max_batch"] == {"value": 32, "source": "default"}
    assert explained["max_queue"] == {"value": 1024, "source": "default"}
    assert explained["batch_window_ms"] == {"value": 5.0, "source": "default"}
    assert explained["client_id_header"] == {
        "value": "x-client-id", "source": "default"}
    assert explained["drain_timeout_s"] == {"value": 10.0, "source": "default"}
    assert explained["unix_socket"] == {"value": None, "source": "default"}
    assert explained["client_policies_path"] == {
        "value": None, "source": "default"}
    # one entry per known key, no extras
    assert set(explained) == {
        "host", "port", "unix_socket", "batch_window_ms", "max_batch",
        "max_queue", "client_policies_path", "client_id_header",
        "drain_timeout_s",
    }
    for entry in explained.values():
        assert set(entry) == {"value", "source"}
        assert entry["source"] in ("file", "default")


def test_explain_daemon_config_empty_file_is_all_defaults(tmp_path):
    cfg = _write(tmp_path / "hugrgate.yaml", "{}\n")
    explained = explain_daemon_config(cfg)
    assert all(entry["source"] == "default"
               for entry in explained.values())
    assert explained["port"]["value"] == 8377  # default port


def test_explain_daemon_config_keeps_defaults_file_source(tmp_path):
    """A key explicitly set to its default value still comes from the file."""
    cfg = _write(tmp_path / "hugrgate.yaml", "port: 8377\n")
    explained = explain_daemon_config(cfg)
    assert explained["port"] == {"value": 8377, "source": "file"}


def test_explain_daemon_config_missing_file_raises(tmp_path):
    with pytest.raises(ConfigError):
        explain_daemon_config(tmp_path / "nope.yaml")


def test_explain_daemon_config_invalid_file_raises(tmp_path):
    cfg = _write(tmp_path / "hugrgate.yaml", "port: 99999\n")
    with pytest.raises(ConfigError):
        explain_daemon_config(cfg)


def test_explain_daemon_config_rejects_unknown_keys(tmp_path):
    cfg = _write(tmp_path / "hugrgate.yaml", "bogus_key: 1\n")
    with pytest.raises(ConfigError):
        explain_daemon_config(cfg)
