"""Tests for service spec resolution and session helpers."""

from unittest.mock import MagicMock

import pytest

from bbrun.docker import docker_daemon_available
from bbrun.services import (
    ServiceSession,
    ServiceSpec,
    image_exposed_ports,
    resolve_service_specs,
    wait_tcp,
)


def _config() -> dict:
    return {
        "definitions": {
            "services": {
                "rabbitmq": {
                    "image": "rabbitmq:4.2",
                    "variables": {"RABBITMQ_DEFAULT_USER": "guest"},
                }
            }
        }
    }


def test_resolve_service_specs() -> None:
    step = {"services": ["rabbitmq"]}
    specs = resolve_service_specs(_config(), step)
    assert len(specs) == 1
    assert specs[0].name == "rabbitmq"
    assert specs[0].image == "rabbitmq:4.2"
    assert specs[0].variables["RABBITMQ_DEFAULT_USER"] == "guest"


def test_resolve_skips_unknown_and_docker() -> None:
    step = {"services": ["docker", "nope"]}
    assert resolve_service_specs(_config(), step) == []


def test_no_services_is_empty() -> None:
    assert resolve_service_specs(_config(), {"name": "lint"}) == []


def test_wait_tcp_timeout() -> None:
    assert wait_tcp("127.0.0.1", 1, timeout=0.2) is False


def test_image_exposed_ports_parses(monkeypatch) -> None:
    monkeypatch.setattr(
        "bbrun.services.subprocess.run",
        lambda *a, **k: MagicMock(
            returncode=0,
            stdout='{"5672/tcp":{},"15672/tcp":{}}\n',
        ),
    )
    assert image_exposed_ports("rabbitmq:4.2") == [5672, 15672]


def test_session_skip_when_disabled() -> None:
    session = ServiceSession(enabled=False, docker_mode=False, run_id="t")
    assert session.start([ServiceSpec("rabbitmq", "rabbitmq:4.2")]) is True


def test_session_fails_without_docker(monkeypatch) -> None:
    monkeypatch.setattr("bbrun.docker.docker_daemon_available", lambda: False)
    session = ServiceSession(enabled=True, docker_mode=False, run_id="t")
    ok = session.start([ServiceSpec("rabbitmq", "rabbitmq:4.2")])
    assert ok is False


def test_session_start_and_stop_mocked(monkeypatch) -> None:
    calls: list[list[str]] = []

    def fake_run(cmd, **kwargs):
        calls.append(list(cmd))
        result = MagicMock()
        result.returncode = 0
        result.stdout = ""
        result.stderr = ""
        if cmd[:3] == ["docker", "image", "inspect"]:
            if "--format" in cmd:
                result.stdout = '{"5672/tcp":{}}\n'
            return result
        return result

    monkeypatch.setattr("bbrun.docker.docker_daemon_available", lambda: True)
    monkeypatch.setattr("bbrun.services.subprocess.run", fake_run)
    monkeypatch.setattr("bbrun.services.wait_tcp", lambda *a, **k: True)
    monkeypatch.setattr("bbrun.services._ensure_image", lambda image: True)

    session = ServiceSession(enabled=True, docker_mode=True, run_id="abc")
    ok = session.start([ServiceSpec("rabbitmq", "rabbitmq:4.2")])
    assert ok is True
    assert any(cmd[:3] == ["docker", "network", "create"] for cmd in calls)
    assert session.docker_run_args() == ["--network", "bb-run-abc"]
    session.stop()
    assert any(cmd[:3] == ["docker", "rm", "-f"] for cmd in calls)


@pytest.mark.skipif(not docker_daemon_available(), reason="Docker daemon not available")
def test_optional_live_docker_info() -> None:
    assert docker_daemon_available() is True
