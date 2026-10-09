"""Static peer configuration. Slice 205.

For clusters with fixed membership — the common on-prem case — peers
are declared in a file instead of discovered. The file is JSON or YAML::

    peers:
      - host: 10.0.0.2
        port: 8377
        node_id: "<64-hex, optional: learned on first contact>"
        tls: true
        display_name: "norn-2"

:func:`load_static_config` validates the file loudly (unknown keys,
bad ports, duplicate endpoints all raise :class:`SpecError` — a typo
must never silently drop a peer). :class:`StaticDiscovery` turns the
loaded config into a pull-style :class:`Discovery` adapter for the
registry from slice 204.
"""

from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass, field
from typing import Any

import yaml

from hugrgate.cluster.discovery import Discovery, PeerRecord
from hugrgate.errors import SpecError

__all__ = [
    "StaticDiscovery",
    "StaticPeerConfig",
    "example_config",
    "load_static_config",
]


@dataclass
class StaticPeerConfig:
    """Validated static peer file."""

    peers: list[dict[str, Any]] = field(default_factory=list)
    source_path: str = ""

    def __post_init__(self) -> None:
        seen: set[tuple[str, int]] = set()
        for entry in self.peers:
            _validate_peer_entry(entry)
            key = (entry["host"], entry["port"])
            if key in seen:
                raise SpecError(
                    f"duplicate static peer endpoint {key[0]}:{key[1]}")
            seen.add(key)

    def to_records(self, source: str = "static") -> list[PeerRecord]:
        return [
            PeerRecord(
                node_id=entry.get("node_id") or _placeholder_id(entry),
                host=entry["host"],
                port=entry["port"],
                tls=bool(entry.get("tls", False)),
                source=source,
            )
            for entry in self.peers
        ]


def _validate_peer_entry(entry: Any) -> None:
    if not isinstance(entry, dict):
        raise SpecError(
            f"static peer entry must be a mapping, got {type(entry).__name__}")
    known = {"host", "port", "node_id", "tls", "display_name"}
    unknown = set(entry) - known
    if unknown:
        raise SpecError(
            f"unknown static peer key(s): {sorted(unknown)}; "
            f"expected: {sorted(known)}")
    host = entry.get("host")
    if not isinstance(host, str) or not host.strip():
        raise SpecError("static peer needs a non-empty 'host'")
    port = entry.get("port")
    if not isinstance(port, int) or isinstance(port, bool) \
            or not 1 <= port <= 65535:
        raise SpecError(
            f"static peer 'port' must be an int in 1..65535, got {port!r}")
    node_id = entry.get("node_id")
    if node_id is not None and (
            not isinstance(node_id, str) or len(node_id) != 64
            or any(c not in "0123456789abcdef" for c in node_id)):
        raise SpecError("static peer 'node_id' must be 64 hex chars")
    if "tls" in entry and not isinstance(entry["tls"], bool):
        raise SpecError("static peer 'tls' must be a boolean")


def _placeholder_id(entry: dict[str, Any]) -> str:
    """Stand-in node id for peers whose id is not known yet.

    64 hex chars derived from the endpoint; the real node id replaces
    it on first authenticated contact (slice 208). A sha256 of
    ``"host:port"`` cannot equal a real node id (sha256 of a 256-bit
    secret) except by cosmic coincidence.
    """
    return hashlib.sha256(
        f"{entry['host']}:{entry['port']}".encode()).hexdigest()


def load_static_config(path: str | os.PathLike[str]) -> StaticPeerConfig:
    """Load and validate a static peer file (JSON or YAML by extension)."""
    path = os.fspath(path)
    try:
        with open(path, encoding="utf-8") as fh:
            text = fh.read()
    except FileNotFoundError:
        raise SpecError(f"static peer file not found: {path}") from None
    except OSError as e:
        raise SpecError(
            f"static peer file {path} is unreadable: {e}") from e
    suffix = os.path.splitext(path)[1].lower()
    try:
        if suffix in (".yaml", ".yml"):
            data = yaml.safe_load(text)
        elif suffix == ".json" or not suffix:
            data = json.loads(text)
        else:
            raise SpecError(
                f"static peer file {path} has unsupported extension "
                f"{suffix!r}; use .json, .yaml or .yml")
    except yaml.YAMLError as e:
        raise SpecError(
            f"static peer file {path} is not valid YAML: {e}") from e
    except json.JSONDecodeError as e:
        raise SpecError(
            f"static peer file {path} is not valid JSON: {e}") from e
    if not isinstance(data, dict):
        raise SpecError(
            f"static peer file {path} must hold a mapping with a 'peers' key")
    peers = data.get("peers", [])
    if not isinstance(peers, list):
        raise SpecError(
            f"static peer file {path}: 'peers' must be a list")
    unknown = set(data) - {"peers"}
    if unknown:
        raise SpecError(
            f"static peer file {path}: unknown top-level key(s) "
            f"{sorted(unknown)}")
    return StaticPeerConfig(peers=peers, source_path=str(path))


def example_config() -> dict[str, Any]:
    """A minimal valid config operators can copy."""
    return {
        "peers": [
            {"host": "10.0.0.2", "port": 8377, "tls": False,
             "display_name": "norn-2"},
            {"host": "10.0.0.3", "port": 8377, "tls": True,
             "display_name": "norn-3"},
        ]
    }


class StaticDiscovery(Discovery):
    """Pull-style adapter serving a loaded :class:`StaticPeerConfig`."""

    name = "static"

    def __init__(self, config: StaticPeerConfig) -> None:
        if not isinstance(config, StaticPeerConfig):
            raise SpecError(
                f"config must be a StaticPeerConfig, got "
                f"{type(config).__name__}")
        self._config = config

    @classmethod
    def from_file(cls, path: str | os.PathLike[str]) -> StaticDiscovery:
        return cls(load_static_config(path))

    def peers(self) -> list[PeerRecord]:
        # Fresh records each call so last_seen stays current.
        return self._config.to_records(source=self.name)
