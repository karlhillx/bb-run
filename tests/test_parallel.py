"""Tests for parallel pipeline groups."""

import time

import yaml

from bbrun.host import HostRunner
from bbrun.pipeline import (
    abort_siblings_on_step_failure,
    parallel_failure_summaries,
    parse_parallel_block,
    unwrap_step_item,
)


def test_parse_parallel_dict_steps_and_fail_fast():
    block = {
        "fail-fast": True,
        "steps": [
            {"step": {"name": "a", "script": ["echo 1"]}},
            {"step": {"name": "b", "script": ["echo 2"]}},
        ],
    }
    raw, ff = parse_parallel_block(block)
    assert ff is True
    assert len(raw) == 2


def test_parse_parallel_list_form():
    raw, ff = parse_parallel_block(
        [
            {"step": {"name": "x", "script": ["true"]}},
        ]
    )
    assert ff is False
    assert len(raw) == 1


def test_unwrap_step_item():
    inner = {"name": "t", "script": ["true"]}
    assert unwrap_step_item({"step": inner}) == inner


def test_parallel_failure_summaries():
    raw = [
        {"step": {"name": "A", "script": ["true"]}},
        {"step": {"name": "B", "script": ["false"]}},
    ]
    lines = parallel_failure_summaries(raw, [True, False])
    assert len(lines) == 1
    assert "B" in lines[0]
    assert "parallel index 1" in lines[0]


def test_abort_siblings_on_step_failure():
    assert abort_siblings_on_step_failure({}, True) is True
    assert abort_siblings_on_step_failure({"fail-fast": False}, True) is False
    assert abort_siblings_on_step_failure({}, False) is False
    assert abort_siblings_on_step_failure({"fail-fast": True}, False) is True


def test_host_parallel_runs(tmp_path):
    pipeline = {
        "pipelines": {
            "default": [
                {
                    "parallel": {
                        "steps": [
                            {"step": {"name": "a", "script": ["echo a"]}},
                            {"step": {"name": "b", "script": ["echo b"]}},
                        ]
                    }
                }
            ]
        }
    }
    (tmp_path / "bitbucket-pipelines.yml").write_text(
        yaml.dump(pipeline), encoding="utf-8"
    )
    runner = HostRunner(tmp_path)
    assert runner.run() is True


def test_host_parallel_fail_fast_terminates_sibling(tmp_path):
    pipeline = {
        "pipelines": {
            "default": [
                {
                    "parallel": {
                        "fail-fast": True,
                        "steps": [
                            {"step": {"name": "fail", "script": ["exit 1"]}},
                            {
                                "step": {
                                    "name": "slow",
                                    "script": ["sleep 12"],
                                }
                            },
                        ],
                    }
                }
            ]
        }
    }
    (tmp_path / "bitbucket-pipelines.yml").write_text(
        yaml.dump(pipeline), encoding="utf-8"
    )
    runner = HostRunner(tmp_path)
    start = time.monotonic()
    assert runner.run() is False
    assert time.monotonic() - start < 8.0, "fail-fast should not wait for sleep"
