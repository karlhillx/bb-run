"""
Tests for DockerRunner behavior
"""

import json
from pathlib import Path

from bbrun.docker import (
    DockerRunner,
    apply_docker_git_filemode,
    docker_cli_env,
    docker_daemon_status,
    missing_docker_credential_helper,
    pull_docker_image,
)


def test_docker_runner_run_step_script(tmp_path, monkeypatch):
    runner = DockerRunner(tmp_path)
    env = {"FOO": "bar"}
    step = {"script": ["echo hello"]}

    recorded = {}

    class DummyProc:
        def wait(self):
            return 0

    def fake_spawn(step_arg, default_image_arg, env_arg, label="", script_key="script"):
        recorded["step"] = step_arg
        recorded["default_image"] = default_image_arg
        recorded["env"] = env_arg
        recorded["label"] = label
        recorded["script_key"] = script_key
        return DummyProc()

    monkeypatch.setattr(runner, "_docker_spawn_step", fake_spawn)

    result = runner._run_step(step, "test", "python:3.11", env)

    assert result is True
    assert recorded["step"] == step
    assert recorded["default_image"] == "python:3.11"
    assert recorded["env"]["FOO"] == "bar"
    assert recorded["label"] == ""


def test_docker_env_does_not_leak_host_askpass(tmp_path, monkeypatch):
    monkeypatch.setenv(
        "GIT_ASKPASS",
        "/Applications/Cursor.app/Contents/Resources/app/extensions/git/dist/askpass.sh",
    )
    monkeypatch.setenv("PATH", "/opt/homebrew/bin:/usr/bin")
    runner = DockerRunner(tmp_path)
    env = runner._build_env("master")
    assert "GIT_ASKPASS" not in env
    assert env.get("PATH") is None
    assert env["CI"] == "true"
    assert env["HOME"] == "/root"
    assert env["BITBUCKET_CLONE_DIR"] == "/opt/atlassian/pipelines/agent/build"


def test_docker_runner_run_step_pipe(tmp_path, monkeypatch):
    runner = DockerRunner(tmp_path)
    env = {"FOO": "bar"}
    step = {"pipe": "atlassian/slack-notify:0.5.0"}

    monkeypatch.setattr(runner, "_docker_spawn_step", lambda *args, **kwargs: None)

    result = runner._run_step(step, "pipe", "python:3.11", env)

    assert result is True


def test_missing_credential_helper_from_config(tmp_path, monkeypatch):
    (tmp_path / "config.json").write_text(
        json.dumps({"credsStore": "desktop"}), encoding="utf-8"
    )
    monkeypatch.setenv("DOCKER_CONFIG", str(tmp_path))
    monkeypatch.setattr(
        "bbrun.docker.shutil.which", lambda name, path=None: None
    )
    assert missing_docker_credential_helper() == "docker-credential-desktop"


def test_missing_credential_helper_ok_when_present(tmp_path, monkeypatch):
    (tmp_path / "config.json").write_text(
        json.dumps({"credsStore": "desktop"}), encoding="utf-8"
    )
    monkeypatch.setenv("DOCKER_CONFIG", str(tmp_path))
    monkeypatch.setattr(
        "bbrun.docker.shutil.which",
        lambda name, path=None: "/bin/docker-credential-desktop",
    )
    assert missing_docker_credential_helper() is None


def test_pull_retries_without_broken_helper(monkeypatch, tmp_path):
    monkeypatch.setattr(
        "bbrun.docker.missing_docker_credential_helper",
        lambda: "docker-credential-desktop",
    )
    monkeypatch.setattr("bbrun.docker._docker_pull_supports_progress_flag", lambda: False)
    calls: list[str | None] = []

    class Proc:
        def __init__(self, code: int) -> None:
            self.returncode = code

        def poll(self) -> int:
            return self.returncode

        def wait(self, timeout: float | None = None) -> int:
            return self.returncode

    def fake_popen(cmd, env=None, **kwargs):
        config = (env or {}).get("DOCKER_CONFIG")
        calls.append(config)
        # First pull uses the real config and fails; anonymous retry succeeds.
        return Proc(0 if config and Path(config).name != Path(tmp_path).name else 1)

    monkeypatch.setenv("DOCKER_CONFIG", str(tmp_path))
    monkeypatch.setattr("bbrun.docker.subprocess.Popen", fake_popen)

    assert pull_docker_image("ghcr.io/astral-sh/uv:0.11-python3.12-trixie") is True
    assert len(calls) == 2
    assert calls[0] == str(tmp_path)
    assert calls[1] != str(tmp_path)
    assert calls[1] is not None


def test_docker_cli_env_sets_anonymous_config(tmp_path):
    env = docker_cli_env(anonymous_config=tmp_path)
    assert env["DOCKER_CONFIG"] == str(tmp_path)


def test_git_filemode_false_on_darwin() -> None:
    env: dict[str, str] = {}
    apply_docker_git_filemode(env, platform="darwin")
    assert env["GIT_CONFIG_COUNT"] == "1"
    assert env["GIT_CONFIG_KEY_0"] == "core.filemode"
    assert env["GIT_CONFIG_VALUE_0"] == "false"


def test_git_filemode_skipped_on_linux() -> None:
    env: dict[str, str] = {}
    apply_docker_git_filemode(env, platform="linux")
    assert env == {}


def test_git_filemode_appends_existing_git_config() -> None:
    env = {
        "GIT_CONFIG_COUNT": "1",
        "GIT_CONFIG_KEY_0": "user.name",
        "GIT_CONFIG_VALUE_0": "bb-run",
    }
    apply_docker_git_filemode(env, platform="win32")
    assert env["GIT_CONFIG_COUNT"] == "2"
    assert env["GIT_CONFIG_KEY_1"] == "core.filemode"
    assert env["GIT_CONFIG_VALUE_1"] == "false"
    assert env["GIT_CONFIG_VALUE_0"] == "bb-run"


def test_git_filemode_idempotent() -> None:
    env: dict[str, str] = {}
    apply_docker_git_filemode(env, platform="darwin")
    apply_docker_git_filemode(env, platform="darwin")
    assert env["GIT_CONFIG_COUNT"] == "1"


def test_daemon_status_when_cli_missing(monkeypatch):
    monkeypatch.setattr("bbrun.docker.shutil.which", lambda name, path=None: None)
    ok, detail = docker_daemon_status()
    assert ok is False
    assert detail == "docker CLI not found"


def test_daemon_status_when_daemon_stopped(monkeypatch):
    monkeypatch.setattr(
        "bbrun.docker.shutil.which",
        lambda name, path=None: "/usr/bin/docker",
    )

    class Result:
        returncode = 1
        stderr = (
            "Cannot connect to the Docker daemon at unix:///Users/me/.docker/run/docker.sock. "
            "Is the docker daemon running?\n"
        )
        stdout = "Client:\n"

    monkeypatch.setattr("bbrun.docker.subprocess.run", lambda *args, **kwargs: Result())
    ok, detail = docker_daemon_status()
    assert ok is False
    assert detail == "Docker daemon is not running"
