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
    assert "Expected KEY=VALUE" in captured.out


def test_cli_rejects_empty_variable_key(monkeypatch, capsys):
    monkeypatch.setattr(sys, "argv", ["bb-run", "-v", "=value"])

    exit_code = cli.main()
    captured = capsys.readouterr()

    assert exit_code == 2
    assert "Key cannot be empty" in captured.out
