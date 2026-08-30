"""Tests for repo discovery and auto target selection."""

from pathlib import Path

import yaml

from bbrun.discover import find_repo_root, git_origin_urls, resolve_repo_path
from bbrun.pipeline import resolve_auto_target


def test_find_repo_root_walks_up(tmp_path: Path) -> None:
    nested = tmp_path / "src" / "pkg"
    nested.mkdir(parents=True)
    (tmp_path / "bitbucket-pipelines.yml").write_text("pipelines: {}\n", encoding="utf-8")
    assert find_repo_root(nested) == tmp_path


def test_find_repo_root_missing(tmp_path: Path) -> None:
    assert find_repo_root(tmp_path) is None


def test_resolve_repo_path_walks_default_dot(tmp_path: Path, monkeypatch) -> None:
    nested = tmp_path / "src"
    nested.mkdir()
    (tmp_path / "bitbucket-pipelines.yml").write_text("pipelines: {}\n", encoding="utf-8")
    monkeypatch.chdir(nested)
    assert resolve_repo_path(".") == tmp_path


def test_resolve_repo_path_explicit_stays(tmp_path: Path) -> None:
    nested = tmp_path / "src"
    nested.mkdir()
    (tmp_path / "bitbucket-pipelines.yml").write_text("pipelines: {}\n", encoding="utf-8")
    assert resolve_repo_path(str(nested)) == nested.resolve()


def test_resolve_auto_target_prefers_git_branch() -> None:
    config = {
        "pipelines": {
            "default": [{"step": {"name": "d", "script": ["true"]}}],
            "branches": {"master": [{"step": {"name": "m", "script": ["true"]}}]},
            "pull-requests": {"**": [{"step": {"name": "pr", "script": ["true"]}}]},
        }
    }
    assert resolve_auto_target(config, "master") == "branches.master"


def test_resolve_auto_target_falls_back_to_default() -> None:
    config = {
        "pipelines": {
            "default": [{"step": {"name": "d", "script": ["true"]}}],
            "pull-requests": {"**": [{"step": {"name": "pr", "script": ["true"]}}]},
        }
    }
    assert resolve_auto_target(config, "feature/x") == "default"


def test_resolve_auto_target_pull_requests_without_default() -> None:
    config = {
        "pipelines": {
            "pull-requests": {"**": [{"step": {"name": "pr", "script": ["true"]}}]},
            "branches": {"master": [{"step": {"name": "m", "script": ["true"]}}]},
        }
    }
    assert resolve_auto_target(config, "feature/x") == "pull-requests.**"


def test_resolve_auto_target_wildcard_branch() -> None:
    config = {
        "pipelines": {
            "branches": {
                "feature/*": [{"step": {"name": "f", "script": ["true"]}}],
            }
        }
    }
    assert resolve_auto_target(config, "feature/demo") == "branches.feature/demo"


def test_git_origin_urls_empty_without_git(tmp_path: Path) -> None:
    http, ssh = git_origin_urls(tmp_path)
    assert http == ""
    assert ssh == ""


def test_jacobs_shaped_yaml_anchors_load() -> None:
    fixture = Path(__file__).parent / "fixtures" / "jacobs_shaped.yml"
    config = yaml.safe_load(fixture.read_text(encoding="utf-8"))
    assert resolve_auto_target(config, None) == "pull-requests.**"
    assert resolve_auto_target(config, "master") == "branches.master"
