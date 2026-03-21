"""Tests for pipeline artifacts."""

from pathlib import Path

import yaml

from bbrun.artifacts import (
    ArtifactSession,
    expand_artifact_files,
    iter_upload_specs,
    parse_download_rule,
    should_capture,
    _ALL_DOWNLOAD,
)
from bbrun.host import HostRunner


def test_iter_upload_specs_list_form():
    step = {"artifacts": ["dist/**", "*.txt"]}
    specs = iter_upload_specs(step)
    assert len(specs) == 1
    assert specs[0].paths == ["dist/**", "*.txt"]
    assert specs[0].type == "shared"


def test_iter_upload_specs_upload_block():
    step = {
        "artifacts": {
            "upload": [
                {
                    "name": "reports",
                    "type": "shared",
                    "paths": ["r/**/*.xml"],
                    "capture-on": "success",
                }
            ]
        }
    }
    specs = iter_upload_specs(step)
    assert len(specs) == 1
    assert specs[0].name == "reports"
    assert specs[0].capture_on == "success"


def test_parse_download_rule():
    assert parse_download_rule({}) is _ALL_DOWNLOAD
    assert parse_download_rule({"artifacts": {"download": False}}) is False
    assert parse_download_rule({"artifacts": {"download": ["A", "B"]}}) == [
        "A",
        "B",
    ]


def test_should_capture():
    assert should_capture("success", True) is True
    assert should_capture("success", False) is False
    assert should_capture("failed", False) is True
    assert should_capture("always", False) is True


def test_expand_artifact_files(tmp_path: Path):
    (tmp_path / "a").mkdir()
    (tmp_path / "a" / "x.txt").write_text("hi", encoding="utf-8")
    found = expand_artifact_files(tmp_path, ["a/*.txt"], [])
    assert len(found) == 1
    assert found[0].name == "x.txt"


def test_host_artifacts_restore_between_steps(tmp_path: Path):
    pipeline = {
        "pipelines": {
            "default": [
                {
                    "step": {
                        "name": "write",
                        "script": [
                            "mkdir -p out",
                            "echo hello > out/greeting.txt",
                        ],
                        "artifacts": ["out/greeting.txt"],
                    }
                },
                {
                    "step": {
                        "name": "read",
                        "script": [
                            "test -f out/greeting.txt",
                            "grep -q hello out/greeting.txt",
                        ],
                    }
                },
            ]
        }
    }
    (tmp_path / "bitbucket-pipelines.yml").write_text(
        yaml.dump(pipeline), encoding="utf-8"
    )
    assert HostRunner(tmp_path).run() is True


def test_capture_on_failed(tmp_path: Path):
    pipeline = {
        "pipelines": {
            "default": [
                {
                    "step": {
                        "name": "fail_with_log",
                        "script": [
                            "mkdir -p logs",
                            "echo oops > logs/err.txt",
                            "exit 1",
                        ],
                        "artifacts": {
                            "upload": [
                                {
                                    "name": "err",
                                    "type": "shared",
                                    "paths": ["logs/err.txt"],
                                    "capture-on": "failed",
                                }
                            ]
                        },
                    }
                },
                {
                    "step": {
                        "name": "consume",
                        "script": [
                            "test -f logs/err.txt",
                            "grep -q oops logs/err.txt",
                        ],
                    }
                },
            ]
        }
    }
    (tmp_path / "bitbucket-pipelines.yml").write_text(
        yaml.dump(pipeline), encoding="utf-8"
    )
    assert HostRunner(tmp_path).run() is False
    # Pipeline stops on first step failure — second step never runs.
    # Session still captured the failed-step artifact on disk under .bb-run.
    sess_dir = tmp_path / ".bb-run" / "artifacts"
    assert sess_dir.exists()
    assert any(sess_dir.rglob("err.txt"))


def test_scoped_saved_under_bb_run(tmp_path: Path):
    pipeline = {
        "pipelines": {
            "default": [
                {
                    "step": {
                        "name": "w",
                        "script": ["mkdir -p x", "echo z > x/a.txt"],
                        "artifacts": {
                            "upload": [
                                {
                                    "name": "snap",
                                    "type": "scoped",
                                    "paths": ["x/a.txt"],
                                }
                            ]
                        },
                    }
                },
                {
                    "step": {
                        "name": "next",
                        "script": ["test -f x/a.txt"],
                    }
                },
            ]
        }
    }
    (tmp_path / "bitbucket-pipelines.yml").write_text(
        yaml.dump(pipeline), encoding="utf-8"
    )
    assert HostRunner(tmp_path).run() is True
    scoped = list((tmp_path / ".bb-run").rglob("scoped"))
    assert scoped, "scoped artifact tree should exist under .bb-run"


def test_selective_download_by_artifact_name(tmp_path: Path):
    pipeline = {
        "pipelines": {
            "default": [
                {
                    "step": {
                        "name": "w",
                        "script": ["mkdir -p u", "echo n > u/1.txt"],
                        "artifacts": {
                            "upload": [
                                {
                                    "name": "mine",
                                    "type": "shared",
                                    "paths": ["u/1.txt"],
                                }
                            ]
                        },
                    }
                },
                {
                    "step": {
                        "name": "r",
                        "artifacts": {"download": ["mine"]},
                        "script": [
                            "rm -f u/1.txt",
                            "test ! -f u/1.txt",
                        ],
                    }
                },
                {
                    "step": {
                        "name": "restored",
                        "script": [
                            "test -f u/1.txt",
                            "grep -q n u/1.txt",
                        ],
                    }
                },
            ]
        }
    }
    (tmp_path / "bitbucket-pipelines.yml").write_text(
        yaml.dump(pipeline), encoding="utf-8"
    )
    assert HostRunner(tmp_path).run() is True


def test_artifact_session_merge_idempotent(tmp_path: Path):
    (tmp_path / "f.txt").write_text("x", encoding="utf-8")
    s = ArtifactSession(tmp_path)
    step_w = {"artifacts": ["f.txt"]}
    s.capture_after_step(step_w, True)
    s.prepare_for_step({})
    assert (tmp_path / "f.txt").read_text() == "x"
