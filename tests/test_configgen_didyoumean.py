"""Slice configgen-did-you-mean: unknown daemon config keys get
difflib "did you mean" suggestions in the ConfigError message."""

import pytest

from hugrgate.configgen import generate_daemon_config
from hugrgate.errors import ConfigError


def test_typo_port_suggests_port():
    with pytest.raises(ConfigError) as exc_info:
        generate_daemon_config(porrt=9999)
    message = str(exc_info.value)
    assert "porrt" in message
    assert "did you mean 'port'" in message


def test_typo_hostname_suggests_host():
    with pytest.raises(ConfigError) as exc_info:
        generate_daemon_config(hostnme="10.0.0.1")
    assert "did you mean 'host'" in str(exc_info.value)


def test_garbage_key_has_no_suggestion():
    with pytest.raises(ConfigError) as exc_info:
        generate_daemon_config(zzzqxjk_no_such_key=1)
    message = str(exc_info.value)
    assert "zzzqxjk_no_such_key" in message
    assert "did you mean" not in message


def test_multiple_unknown_keys_each_get_suggestion():
    with pytest.raises(ConfigError) as exc_info:
        generate_daemon_config(porrt=9999, hosst="10.0.0.1")
    message = str(exc_info.value)
    assert "did you mean 'port'" in message
    assert "did you mean 'host'" in message


def test_valid_config_still_loads():
    doc = generate_daemon_config(port=9999, host="10.0.0.1")
    assert "port: 9999" in doc
    assert "host: 10.0.0.1" in doc


def test_defaults_still_load_without_overrides():
    doc = generate_daemon_config()
    assert "port: 8377" in doc
