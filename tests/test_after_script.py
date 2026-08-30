"""after-script and richer Bitbucket environment."""

import yaml

from bbrun.host import HostRunner


def _write(tmp_path, config) -> None:
    (tmp_path / "bitbucket-pipelines.yml").write_text(
        yaml.dump(config), encoding="utf-8"
    )


def test_after_script_runs_on_failure(tmp_path) -> None:
    marker = tmp_path / "after.txt"
    _write(
        tmp_path,
        {
            "pipelines": {
                "default": [
                    {
                        "step": {
                            "name": "fail then cleanup",
                            "script": ["exit 1"],
                            "after-script": [
                                f"printf '%s' \"$BITBUCKET_EXIT_CODE\" > '{marker}'"
                            ],
                        }
                    }
                ]
            }
        },
    )
    runner = HostRunner(tmp_path)
    assert runner.run(target="default") is False
    assert marker.read_text(encoding="utf-8") == "1"


def test_after_script_failure_fails_step(tmp_path) -> None:
    _write(
        tmp_path,
        {
            "pipelines": {
                "default": [
                    {
                        "step": {
                            "name": "ok then fail after",
                            "script": ["echo ok"],
                            "after-script": ["exit 1"],
                        }
                    }
                ]
            }
        },
    )
    runner = HostRunner(tmp_path)
    assert runner.run(target="default") is False


def test_after_script_success(tmp_path) -> None:
    marker = tmp_path / "done.txt"
    _write(
        tmp_path,
        {
            "pipelines": {
                "default": [
                    {
                        "step": {
                            "name": "ok",
                            "script": ["echo ok"],
                            "after-script": [f"echo done > '{marker}'"],
                        }
                    }
                ]
            }
        },
    )
    runner = HostRunner(tmp_path)
    assert runner.run(target="default") is True
    assert marker.exists()


def test_build_env_includes_ci_and_uuids(tmp_path) -> None:
    _write(
        tmp_path,
        {"pipelines": {"default": [{"step": {"name": "t", "script": ["true"]}}]}},
    )
    runner = HostRunner(tmp_path)
    runner.tag = "v1.2.3"
    env = runner._build_env("feature-branch")
    assert env["CI"] == "true"
    assert env["BITBUCKET_TAG"] == "v1.2.3"
    assert env["BITBUCKET_BRANCH"] == "feature-branch"
    assert env["BITBUCKET_PIPELINE_UUID"]
    assert "BITBUCKET_GIT_HTTP_ORIGIN" in env
    assert "BITBUCKET_GIT_SSH_ORIGIN" in env
