"""
Tests for DockerRunner behavior
"""

from bbrun.docker import DockerRunner


def test_docker_runner_run_step_script(tmp_path, monkeypatch):
    runner = DockerRunner(tmp_path)
    env = {"FOO": "bar"}
    step = {"script": ["echo hello"]}

    recorded = {}

    class DummyProc:
        def wait(self):
            return 0

    def fake_spawn(step_arg, default_image_arg, env_arg, label=""):
        recorded["step"] = step_arg
        recorded["default_image"] = default_image_arg
        recorded["env"] = env_arg
        recorded["label"] = label
        return DummyProc()

    monkeypatch.setattr(runner, "_docker_spawn_step", fake_spawn)

    result = runner._run_step(step, "test", "python:3.11", env)

    assert result is True
    assert recorded["step"] == step
    assert recorded["default_image"] == "python:3.11"
    assert recorded["env"]["FOO"] == "bar"
    assert recorded["label"] == ""


def test_docker_runner_run_step_pipe(tmp_path, monkeypatch):
    runner = DockerRunner(tmp_path)
    env = {"FOO": "bar"}
    step = {"pipe": "atlassian/slack-notify:0.5.0"}

    monkeypatch.setattr(runner, "_docker_spawn_step", lambda *args, **kwargs: None)

    result = runner._run_step(step, "pipe", "python:3.11", env)

    assert result is True
