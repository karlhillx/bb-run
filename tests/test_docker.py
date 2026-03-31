"""
Tests for DockerRunner behavior
"""

from types import SimpleNamespace

from bbrun.docker import DockerRunner


def test_docker_runner_run_step_script(tmp_path, monkeypatch):
    runner = DockerRunner(tmp_path)
    env = {"FOO": "bar"}
    step = {"script": ["echo hello"]}

    monkeypatch.setattr(runner, "_image_exists", lambda image: True)

    recorded = {}

    def fake_run(cmd, cwd=None, env=None, **kwargs):
        recorded["cmd"] = cmd
        recorded["cwd"] = cwd
        recorded["env"] = env
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr("bbrun.docker.subprocess.run", fake_run)

    result = runner._run_step(step, "test", "python:3.11", env)

    assert result is True
    assert recorded["cmd"][0] == "docker"
    assert "python:3.11" in recorded["cmd"]
    assert recorded["cwd"] == tmp_path
    assert recorded["env"]["FOO"] == "bar"


def test_docker_runner_run_step_pipe(tmp_path, monkeypatch):
    runner = DockerRunner(tmp_path)
    env = {"FOO": "bar"}
    step = {"pipe": "atlassian/slack-notify:0.5.0"}

    monkeypatch.setattr(runner, "_image_exists", lambda image: True)
    monkeypatch.setattr("bbrun.docker.subprocess.run", lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("unexpected run")))

    result = runner._run_step(step, "pipe", "python:3.11", env)

    assert result is True
