"""
Tests for bb-run CLI
"""

import json
import sys
from pathlib import Path

import yaml

from bbrun import cli


def _write_pipeline(tmp_path: Path, config: dict) -> None:
    pipeline_file = tmp_path / "bitbucket-pipelines.yml"
    with open(pipeline_file, "w") as f:
        yaml.dump(config, f)


def test_cli_list_targets_json(tmp_path, monkeypatch, capsys):
    config = {
        "image": "python:3.11",
        "pipelines": {
            "default": [{"step": {"name": "test", "script": ["echo ok"]}}],
            "branches": {"main": [{"step": {"name": "build", "script": ["echo build"]}}]},
            "tags": {"v1": [{"step": {"name": "tag", "script": ["echo tag"]}}]},
            "custom": {"build": [{"step": {"name": "custom", "script": ["echo custom"]}}]},
            "pull-requests": {"**": [{"step": {"name": "pr", "script": ["echo pr"]}}]},
        },
    }
    _write_pipeline(tmp_path, config)

    monkeypatch.setattr(sys, "argv", [
        "bb-run",
        "--repo",
        str(tmp_path),
        "--list-targets",
        "--json",
    ])

    exit_code = cli.main()
    captured = capsys.readouterr()
    data = json.loads(captured.out)

    assert exit_code == 0
    assert data["default_image"] == "python:3.11"
    assert data["targets"] == [
        "default",
        "branches.main",
        "tags.v1",
        "custom.build",
        "pull-requests.**",
    ]


def test_cli_validate_json(tmp_path, monkeypatch, capsys):
    config = {
        "image": "python:3.11",
        "pipelines": {
            "default": [{"step": {"name": "test", "script": ["echo ok"]}}],
        },
    }
    _write_pipeline(tmp_path, config)

    monkeypatch.setattr(sys, "argv", [
        "bb-run",
        "--repo",
        str(tmp_path),
        "--validate",
        "--json",
    ])

    exit_code = cli.main()
    captured = capsys.readouterr()
    data = json.loads(captured.out)

    assert exit_code == 0
    assert data["valid"] is True
    assert data["default_image"] == "python:3.11"
    assert data["targets"] == ["default"]


def test_cli_rejects_invalid_variable(monkeypatch, capsys):
    monkeypatch.setattr(sys, "argv", ["bb-run", "-v", "NOVALUE"])

    exit_code = cli.main()
    captured = capsys.readouterr()

    assert exit_code == 2
    assert "Expected KEY=VALUE" in captured.err


def test_cli_rejects_empty_variable_key(monkeypatch, capsys):
    monkeypatch.setattr(sys, "argv", ["bb-run", "-v", "=value"])

    exit_code = cli.main()
    captured = capsys.readouterr()

    assert exit_code == 2
    assert "Key cannot be empty" in captured.err


def test_cli_dry_run_text(tmp_path, monkeypatch, capsys):
    config = {
        "image": "python:3.11",
        "pipelines": {
            "default": [
                {"step": {"name": "install", "script": ["pip install -e ."]}},
                {
                    "parallel": {
                        "fail-fast": True,
                        "steps": [
                            {"step": {"name": "tests", "script": ["pytest"]}},
                            {"step": {"name": "lint", "script": ["ruff check ."]}},
                        ],
                    }
                },
            ]
        },
    }
    _write_pipeline(tmp_path, config)

    monkeypatch.setattr(sys, "argv", ["bb-run", "--repo", str(tmp_path), "--dry-run"])

    exit_code = cli.main()
    captured = capsys.readouterr()

    assert exit_code == 0
    assert "Dry run" in captured.out
    assert "install" in captured.out
    assert "parallel (2 steps, fail-fast)" in captured.out
    assert "tests" in captured.out
    assert "lint" in captured.out


def test_cli_dry_run_json(tmp_path, monkeypatch, capsys):
    config = {
        "image": "python:3.11",
        "pipelines": {
            "branches": {
                "feature/*": [{"step": {"name": "feature branch", "script": ["echo ok"]}}]
            }
        },
    }
    _write_pipeline(tmp_path, config)

    monkeypatch.setattr(
        sys,
        "argv",
        [
            "bb-run",
            "--repo",
            str(tmp_path),
            "--target",
            "branches.feature/demo",
            "--branch",
            "feature/demo",
            "--dry-run",
            "--json",
        ],
    )

    exit_code = cli.main()
    captured = capsys.readouterr()
    data = json.loads(captured.out)

    assert exit_code == 0
    assert data["target"] == "branches.feature/demo"
    assert data["branch"] == "feature/demo"
    assert data["steps"][0]["name"] == "feature branch"
    assert data["steps"][0]["type"] == "step"
    assert data["steps"][0]["script"] == ["echo ok"]
    assert data["steps"][0]["services"] == []
    assert data["steps"][0]["caches"] == []


def test_cli_auto_target_no_default(tmp_path, monkeypatch, capsys):
    config = {
        "image": "python:3.11",
        "pipelines": {
            "pull-requests": {
                "**": [{"step": {"name": "pr", "script": ["echo pr"]}}],
            }
        },
    }
    _write_pipeline(tmp_path, config)
    monkeypatch.setattr(
        sys,
        "argv",
        ["bb-run", "--repo", str(tmp_path), "--dry-run", "--json"],
    )
    exit_code = cli.main()
    data = json.loads(capsys.readouterr().out)
    assert exit_code == 0
    assert data["target"] == "pull-requests.**"


def test_cli_step_filter_dry_run(tmp_path, monkeypatch, capsys):
    config = {
        "pipelines": {
            "default": [
                {"step": {"name": "Unit tests", "script": ["pytest"]}},
                {"step": {"name": "Code quality", "script": ["ruff"]}},
            ]
        }
    }
    _write_pipeline(tmp_path, config)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "bb-run",
            "--repo",
            str(tmp_path),
            "--step",
            "Unit tests",
            "--dry-run",
            "--json",
        ],
    )
    exit_code = cli.main()
    data = json.loads(capsys.readouterr().out)
    assert exit_code == 0
    assert len(data["steps"]) == 1
    assert data["steps"][0]["name"] == "Unit tests"


def test_cli_mode_auto_without_docker(tmp_path, monkeypatch, capsys):
    config = {
        "pipelines": {
            "default": [{"step": {"name": "t", "script": ["echo ok"]}}],
        }
    }
    _write_pipeline(tmp_path, config)
    monkeypatch.setattr(
        "bbrun.cli.docker_daemon_status",
        lambda: (False, "docker CLI not found"),
    )
    monkeypatch.setattr(
        sys,
        "argv",
        ["bb-run", "--repo", str(tmp_path), "--dry-run", "--json"],
    )
    exit_code = cli.main()
    data = json.loads(capsys.readouterr().out)
    assert exit_code == 0
    assert data["mode"] == "host"
    assert "host" in data["mode_reason"].lower()


def test_resolve_mode_auto_when_daemon_stopped(monkeypatch):
    monkeypatch.setattr(
        "bbrun.cli.docker_daemon_status",
        lambda: (False, "Docker daemon is not running"),
    )
    mode, reason = cli.resolve_mode("auto")
    assert mode == "host"
    assert reason == "Docker daemon is not running; using host"


def test_cli_uv_anchored_dry_run(tmp_path, monkeypatch, capsys):
    fixture = Path(__file__).parent / "fixtures" / "uv_anchored.yml"
    (tmp_path / "bitbucket-pipelines.yml").write_text(
        fixture.read_text(encoding="utf-8"), encoding="utf-8"
    )
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "bb-run",
            "--repo",
            str(tmp_path),
            "--target",
            "pull-requests.**",
            "--dry-run",
            "--json",
        ],
    )
    exit_code = cli.main()
    data = json.loads(capsys.readouterr().out)
    assert exit_code == 0
    assert data["target"] == "pull-requests.**"
    assert data["default_image"].startswith("ghcr.io/astral-sh/uv")
    assert data["steps"][0]["type"] == "parallel"
    names = [child["name"] for child in data["steps"][0]["steps"]]
    assert "Code quality" in names
    assert "Unit tests" in names
    integration = data["steps"][1]["steps"]
    rabbit = [s for s in integration if s["name"] == "Integration tests"][0]
    assert rabbit["services"] == ["rabbitmq"]
    assert rabbit["caches"] == ["uv"]
    quality = [s for s in data["steps"][0]["steps"] if s["name"] == "Code quality"][0]
    assert quality["after_script"] == ['echo "quality done"']
    assert "pre-commit" in quality["caches"]


def test_cli_run_host_success(tmp_path, monkeypatch, capsys):
    config = {
        "pipelines": {
            "default": [{"step": {"name": "hello", "script": ["echo hello"]}}],
        }
    }
    _write_pipeline(tmp_path, config)
    monkeypatch.setattr(
        sys,
        "argv",
        ["bb-run", "--repo", str(tmp_path), "--mode", "host"],
    )
    exit_code = cli.main()
    captured = capsys.readouterr()
    assert exit_code == 0
    assert "Pipeline passed" in captured.out
    assert "Step 1/1" in captured.out
    assert "hello" in captured.out


def test_cli_quiet_hides_banners(tmp_path, monkeypatch, capsys):
    config = {
        "pipelines": {
            "default": [{"step": {"name": "hello", "script": ["echo hello"]}}],
        }
    }
    _write_pipeline(tmp_path, config)
    monkeypatch.setattr(
        sys,
        "argv",
        ["bb-run", "--repo", str(tmp_path), "--mode", "host", "--quiet"],
    )
    exit_code = cli.main()
    captured = capsys.readouterr()
    assert exit_code == 0
    assert "Step 1/1" not in captured.out
    assert "Pipeline passed" in captured.out


def test_cli_env_file_and_cli_override(tmp_path, monkeypatch, capsys):
    _write_pipeline(
        tmp_path,
        {
            "pipelines": {
                "default": [
                    {
                        "step": {
                            "name": "show",
                            "script": ['echo "ENV=$ENVIRONMENT"'],
                        }
                    }
                ]
            }
        },
    )
    env_file = tmp_path / ".env"
    env_file.write_text("ENVIRONMENT=fromfile\nAPI_KEY=file-secret\n", encoding="utf-8")
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "bb-run",
            "--repo",
            str(tmp_path),
            "--mode",
            "host",
            "--env-file",
            str(env_file),
            "-v",
            "ENVIRONMENT=fromcli",
            "--verbose",
        ],
    )
    exit_code = cli.main()
    captured = capsys.readouterr()
    assert exit_code == 0
    assert "ENVIRONMENT=fromcli" in captured.out
    assert "API_KEY=***" in captured.out
    assert "file-secret" not in captured.out


def test_cli_doctor_json(tmp_path, monkeypatch, capsys):
    _write_pipeline(
        tmp_path,
        {"pipelines": {"default": [{"step": {"name": "t", "script": ["true"]}}]}},
    )
    monkeypatch.setattr(
        "bbrun.doctor.docker_daemon_status",
        lambda: (False, "docker CLI not found"),
    )
    monkeypatch.setattr(
        sys,
        "argv",
        ["bb-run", "--repo", str(tmp_path), "--doctor", "--json"],
    )
    exit_code = cli.main()
    data = json.loads(capsys.readouterr().out)
    assert exit_code == 0
    assert data["ok"] is True
    assert data["valid"] is True
    assert data["mode"] == "host"
    assert data["auto_target"] == "default"
    assert data["cred_helper_missing"] is None


def test_cli_doctor_missing_pipeline(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(
        sys,
        "argv",
        ["bb-run", "--repo", str(tmp_path), "--doctor"],
    )
    exit_code = cli.main()
    captured = capsys.readouterr()
    assert exit_code == 1
    assert "No bitbucket-pipelines.yml" in captured.out


def test_cli_validate_json_includes_error(tmp_path, monkeypatch, capsys):
    (tmp_path / "bitbucket-pipelines.yml").write_text("image: python:3.12\n", encoding="utf-8")
    monkeypatch.setattr(
        sys,
        "argv",
        ["bb-run", "--repo", str(tmp_path), "--validate", "--json"],
    )
    exit_code = cli.main()
    data = json.loads(capsys.readouterr().out)
    assert exit_code == 1
    assert data["valid"] is False
    assert "pipelines" in (data["error"] or "").lower()


def test_cli_check_alias(tmp_path, monkeypatch, capsys):
    _write_pipeline(
        tmp_path,
        {"pipelines": {"default": [{"step": {"name": "t", "script": ["true"]}}]}},
    )
    monkeypatch.setattr(
        sys,
        "argv",
        ["bb-run", "--repo", str(tmp_path), "--check"],
    )
    assert cli.main() == 0
    assert "Valid bitbucket-pipelines.yml" in capsys.readouterr().out

