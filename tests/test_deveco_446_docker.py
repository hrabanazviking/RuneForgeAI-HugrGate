"""Slice 446 — Docker packaging stays structurally sound.

Docker is not installed in this environment, so these tests lint
the packaging as data: the Dockerfile must declare every
directive a production image needs, and the compose file must
parse and wire the service sanely.
"""

from __future__ import annotations

import re
from pathlib import Path

import yaml

DOCKER = Path(__file__).resolve().parent.parent / "deploy" / "docker"


def _dockerfile() -> str:
    return (DOCKER / "Dockerfile").read_text(encoding="utf-8")


def test_dockerfile_has_required_directives():
    text = _dockerfile()
    for directive in ("FROM", "WORKDIR", "COPY", "RUN", "USER",
                      "EXPOSE", "HEALTHCHECK", "ENTRYPOINT", "CMD"):
        assert re.search(rf"^{directive}\b", text, re.MULTILINE), directive


def test_dockerfile_is_multistage_and_nonroot():
    text = _dockerfile()
    assert len(re.findall(r"^FROM\b", text, re.MULTILINE)) >= 2
    user = re.search(r"^USER\s+(\S+)", text, re.MULTILINE)
    assert user is not None
    assert user.group(1) != "root"


def test_dockerfile_installs_server_extra():
    assert '".[server]"' in _dockerfile() or ".[server]" in _dockerfile()


def test_dockerfile_healthcheck_hits_health():
    m = re.search(r"HEALTHCHECK.*", _dockerfile(), re.DOTALL)
    assert m and "/health" in m.group(0)


def test_dockerfile_exposes_daemon_port():
    assert re.search(r"^EXPOSE\s+8377", _dockerfile(), re.MULTILINE)


def test_dockerignore_exists_and_covers_secrets():
    text = (DOCKER / ".dockerignore").read_text(encoding="utf-8")
    for pattern in (".git", "venv/", "*.pem", ".env"):
        assert pattern in text, pattern


def test_compose_parses_and_defines_service():
    compose = yaml.safe_load(
        (DOCKER / "docker-compose.yml").read_text(encoding="utf-8"))
    svc = compose["services"]["hugrgate"]
    assert svc["build"]["dockerfile"] == "deploy/docker/Dockerfile"
    assert "8377:8377" in svc["ports"]
    assert svc["healthcheck"]["test"][0] == "CMD"
    assert svc["restart"] == "unless-stopped"


def test_container_config_validates():
    from hugrgate.configgen import load_daemon_config
    cfg = load_daemon_config(str(DOCKER / "hugrgate.yaml"))
    assert cfg.host == "0.0.0.0"  # reachable from outside the container
    assert cfg.port == 8377
