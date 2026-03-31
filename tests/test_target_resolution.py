"""
Tests for pipeline target resolution
"""

import yaml

from bbrun.docker import DockerRunner
from bbrun.host import HostRunner


def _write_pipeline(tmp_path, config):
    pipeline_file = tmp_path / "bitbucket-pipelines.yml"
    with open(pipeline_file, "w") as f:
        yaml.dump(config, f)


def test_target_resolution_for_host_and_docker(tmp_path):
    config = {
        "image": "python:3.11",
        "pipelines": {
            "default": [{"step": {"name": "default", "script": ["echo ok"]}}],
            "branches": {"main": [{"step": {"name": "branch", "script": ["echo branch"]}}]},
            "tags": {"v1": [{"step": {"name": "tag", "script": ["echo tag"]}}]},
            "custom": {"build": [{"step": {"name": "custom", "script": ["echo custom"]}}]},
            "pull-requests": {"**": [{"step": {"name": "pr", "script": ["echo pr"]}}]},
        },
    }
    _write_pipeline(tmp_path, config)

    host_runner = HostRunner(tmp_path)
    docker_runner = DockerRunner(tmp_path)

    host_config = host_runner.validator.load()
    docker_config = docker_runner.validator.load()

    assert host_runner._get_steps(host_config, "default")
    assert host_runner._get_steps(host_config, "branches.main")
    assert host_runner._get_steps(host_config, "tags.v1")
    assert host_runner._get_steps(host_config, "custom.build")
    assert host_runner._get_steps(host_config, "pull-requests.**")

    assert docker_runner._get_steps(docker_config, "default")
    assert docker_runner._get_steps(docker_config, "branches.main")
    assert docker_runner._get_steps(docker_config, "tags.v1")
    assert docker_runner._get_steps(docker_config, "custom.build")
    assert docker_runner._get_steps(docker_config, "pull-requests.**")

    assert host_runner._get_steps(host_config, "branches.missing") == []
    assert docker_runner._get_steps(docker_config, "tags.missing") == []
