"""Tests for slice 205 — static peer configuration."""

from __future__ import annotations

import json

import pytest
import yaml

from hugrgate.cluster.discovery import DiscoveryRegistry
from hugrgate.cluster.static_config import (
    StaticDiscovery,
    StaticPeerConfig,
    example_config,
    load_static_config,
)
from hugrgate.errors import SpecError

NODE_ID = "ab" * 32


def _write(tmp_path, name, text):
    path = tmp_path / name
    path.write_text(text, encoding="utf-8")
    return path


# --- success ---------------------------------------------------------------

def test_load_json_config(tmp_path):
    path = _write(tmp_path, "peers.json", json.dumps({
        "peers": [
            {"host": "10.0.0.2", "port": 8377, "node_id": NODE_ID,
             "tls": True, "display_name": "norn-2"},
            {"host": "10.0.0.3", "port": 8378},
        ]}))
    cfg = load_static_config(path)
    assert len(cfg.peers) == 2
    records = cfg.to_records()
    assert records[0].node_id == NODE_ID
    assert records[0].tls is True
    assert records[0].address == "https://10.0.0.2:8377"
    assert records[1].tls is False
    # placeholder id is deterministic per endpoint
    assert cfg.to_records()[1].node_id == cfg.to_records()[1].node_id


def test_load_yaml_config(tmp_path):
    path = _write(tmp_path, "peers.yaml", yaml.safe_dump({
        "peers": [{"host": "10.0.0.4", "port": 9000}]}))
    cfg = load_static_config(path)
    assert cfg.to_records()[0].host == "10.0.0.4"


def test_example_config_is_valid(tmp_path):
    path = tmp_path / "example.json"
    path.write_text(json.dumps(example_config()), encoding="utf-8")
    cfg = load_static_config(path)
    assert len(cfg.to_records()) == 2


def test_adapter_plugs_into_registry():
    cfg = StaticPeerConfig(peers=[{"host": "h", "port": 1}])
    reg = DiscoveryRegistry()
    reg.add_adapter(StaticDiscovery(cfg))
    assert len(reg) == 1
    assert reg.peers()[0].source == "static"


def test_from_file_classmethod(tmp_path):
    path = _write(tmp_path, "p.json", '{"peers": [{"host": "h", "port": 2}]}')
    adapter = StaticDiscovery.from_file(path)
    assert len(adapter.peers()) == 1


def test_empty_peers_list_is_valid(tmp_path):
    path = _write(tmp_path, "empty.json", '{"peers": []}')
    assert load_static_config(path).peers == []


# --- failure -----------------------------------------------------------------

def test_missing_file():
    with pytest.raises(SpecError, match="not found"):
        load_static_config("/nonexistent/peers.json")


def test_bad_json(tmp_path):
    path = _write(tmp_path, "bad.json", "{oops")
    with pytest.raises(SpecError, match="not valid JSON"):
        load_static_config(path)


def test_bad_yaml(tmp_path):
    path = _write(tmp_path, "bad.yaml", "peers: [unclosed")
    with pytest.raises(SpecError, match="not valid YAML"):
        load_static_config(path)


def test_unknown_extension(tmp_path):
    path = _write(tmp_path, "peers.toml", 'peers = []')
    with pytest.raises(SpecError, match="unsupported extension"):
        load_static_config(path)


def test_unknown_peer_key_rejected():
    with pytest.raises(SpecError, match="unknown static peer key"):
        StaticPeerConfig(peers=[{"host": "h", "port": 1, "bogus": 2}])


def test_duplicate_endpoint_rejected():
    with pytest.raises(SpecError, match="duplicate static peer"):
        StaticPeerConfig(peers=[{"host": "h", "port": 1},
                                {"host": "h", "port": 1}])


def test_bad_ports_rejected():
    for bad in (0, 70000, "8377", True, None):
        with pytest.raises(SpecError, match="port"):
            StaticPeerConfig(peers=[{"host": "h", "port": bad}])


def test_bad_node_id_rejected():
    with pytest.raises(SpecError, match="node_id"):
        StaticPeerConfig(peers=[{"host": "h", "port": 1,
                                 "node_id": "short"}])


def test_non_bool_tls_rejected():
    with pytest.raises(SpecError, match="tls"):
        StaticPeerConfig(peers=[{"host": "h", "port": 1, "tls": "yes"}])


def test_top_level_must_be_mapping(tmp_path):
    path = _write(tmp_path, "list.json", '[1, 2]')
    with pytest.raises(SpecError, match="mapping"):
        load_static_config(path)


def test_peers_must_be_list(tmp_path):
    path = _write(tmp_path, "p.json", '{"peers": {}}')
    with pytest.raises(SpecError, match="'peers' must be a list"):
        load_static_config(path)


def test_unknown_top_level_key_rejected(tmp_path):
    path = _write(tmp_path, "p.json", '{"peers": [], "zzz": 1}')
    with pytest.raises(SpecError, match="unknown top-level"):
        load_static_config(path)


def test_adapter_rejects_wrong_config_type():
    with pytest.raises(SpecError):
        StaticDiscovery(config={"peers": []})  # type: ignore[arg-type]


# --- boundary ----------------------------------------------------------------

def test_placeholder_ids_differ_per_endpoint():
    cfg = StaticPeerConfig(peers=[{"host": "a", "port": 1},
                                  {"host": "a", "port": 2}])
    ids = [r.node_id for r in cfg.to_records()]
    assert ids[0] != ids[1] and all(len(i) == 64 for i in ids)


def test_missing_host_rejected():
    with pytest.raises(SpecError, match="host"):
        StaticPeerConfig(peers=[{"port": 1}])
