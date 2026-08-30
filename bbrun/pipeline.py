"""Shared pipeline parsing and parallel step execution."""

from __future__ import annotations

import contextlib
import fnmatch
import subprocess
import threading
import time
from collections.abc import Callable
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor
from concurrent.futures import wait as futures_wait
from typing import Any

from .errors import explain_process_launch_error


def unwrap_step_item(item: Any) -> dict:
    """Normalize a pipeline list entry to the inner step dict."""
    if isinstance(item, dict):
        return item.get("step", item)
    return {}


def _pattern_specificity(pattern: str) -> tuple[int, int]:
    """Rank glob patterns so precise matches beat broad catch-alls like ``**``."""
    wildcard_count = sum(pattern.count(ch) for ch in "*?[")
    literal_count = len(pattern) - wildcard_count
    return wildcard_count, -literal_count


def _pattern_steps(pipelines: dict[str, Any], group: str, name: str) -> list:
    """Resolve Bitbucket target groups with exact match, then glob-style patterns."""
    entries = pipelines.get(group, {})
    if not isinstance(entries, dict):
        return []
    if name in entries:
        return entries[name]

    matches = [
        (pattern, steps)
        for pattern, steps in entries.items()
        if fnmatch.fnmatchcase(name, pattern)
    ]
    if not matches:
        return []
    matches.sort(key=lambda item: _pattern_specificity(str(item[0])))
    return matches[0][1]


def collect_targets(config: dict[str, Any]) -> list[str]:
    """Collect available pipeline targets from a loaded config."""
    targets: list[str] = []
    pipelines = config.get("pipelines", {})
    if not isinstance(pipelines, dict):
        return targets

    if "default" in pipelines:
        targets.append("default")

    branches = pipelines.get("branches", {})
    if isinstance(branches, dict):
        for branch in sorted(branches.keys()):
            targets.append(f"branches.{branch}")

    tags = pipelines.get("tags", {})
    if isinstance(tags, dict):
        for tag in sorted(tags.keys()):
            targets.append(f"tags.{tag}")

    for name in sorted(pipelines.keys()):
        if name in ("default", "branches", "tags"):
            continue
        if name == "custom" and isinstance(pipelines.get("custom"), dict):
            for custom_name in sorted(pipelines["custom"].keys()):
                targets.append(f"custom.{custom_name}")
        elif name == "pull-requests" and isinstance(pipelines.get("pull-requests"), dict):
            for pr_name in sorted(pipelines["pull-requests"].keys()):
                targets.append(f"pull-requests.{pr_name}")
        else:
            targets.append(name)

    return targets


def resolve_auto_target(config: dict[str, Any], git_branch_name: str | None) -> str:
    """
    Pick a target when the user omits ``--target``.

    Order: matching ``branches.<git-branch>``, then ``default``, then
    ``pull-requests.**``, then the first listed target.
    """
    pipelines = config.get("pipelines", {})
    if not isinstance(pipelines, dict):
        return "default"

    if git_branch_name:
        branch_target = f"branches.{git_branch_name}"
        if get_steps_for_target(config, branch_target):
            return branch_target

    if "default" in pipelines:
        return "default"

    pull_requests = pipelines.get("pull-requests")
    if isinstance(pull_requests, dict):
        if "**" in pull_requests:
            return "pull-requests.**"
        if pull_requests:
            first = next(iter(pull_requests))
            return f"pull-requests.{first}"

    targets = collect_targets(config)
    return targets[0] if targets else "default"


def filter_pipeline_items(
    items: list[Any], names: list[str] | None
) -> list[Any]:
    """Keep only steps whose ``name`` is in *names*. Empty *names* keeps all."""
    if not names:
        return items
    wanted = set(names)
    out: list[Any] = []
    for item in items:
        if isinstance(item, dict) and "parallel" in item:
            raw, _fail_fast = parse_parallel_block(item["parallel"])
            kept = [
                child
                for child in raw
                if unwrap_step_item(child).get("name") in wanted
            ]
            if not kept:
                continue
            if isinstance(item["parallel"], dict):
                new_block = dict(item["parallel"])
                new_block["steps"] = kept
                out.append({"parallel": new_block})
            else:
                out.append({"parallel": kept})
            continue
        step = unwrap_step_item(item)
        if step.get("name") in wanted:
            out.append(item)
    return out


def after_script_key(step: dict[str, Any]) -> str | None:
    """Return the after-script key present on *step*, if any."""
    if "after-script" in step:
        return "after-script"
    if "after_script" in step:
        return "after_script"
    return None


def get_steps_for_target(config: dict[str, Any], target: str) -> list:
    """Return pipeline steps for a target, including Bitbucket-style wildcard keys."""
    pipelines = config.get("pipelines", {})
    if not isinstance(pipelines, dict):
        return []

    if target == "default":
        return pipelines.get("default", [])

    if target.startswith("branches."):
        return _pattern_steps(pipelines, "branches", target.split(".", 1)[1])

    if target.startswith("tags."):
        return _pattern_steps(pipelines, "tags", target.split(".", 1)[1])

    if target.startswith("custom."):
        custom = pipelines.get("custom", {})
        if isinstance(custom, dict):
            return custom.get(target.split(".", 1)[1], [])
        return []

    if target.startswith("pull-requests."):
        return _pattern_steps(pipelines, "pull-requests", target.split(".", 1)[1])

    value = pipelines.get(target, [])
    return value if isinstance(value, list) else []


def parallel_failure_summaries(raw_items: list[Any], each_ok: list[bool]) -> list[str]:
    """Human-readable labels for failed parallel children (for logging)."""
    lines: list[str] = []
    for i, succeeded in enumerate(each_ok):
        if succeeded:
            continue
        item = raw_items[i] if i < len(raw_items) else None
        st = unwrap_step_item(item)
        nm = (
            st.get("name", f"step {i + 1}")
            if isinstance(st, dict)
            else f"step {i + 1}"
        )
        lines.append(f"{nm} (parallel index {i})")
    return lines


def parse_parallel_block(parallel_val: Any) -> tuple[list[Any], bool]:
    """
    Bitbucket format: parallel: { fail-fast?: bool, steps: [ { step: ... }, ... ] }
    Also accepts parallel: [ { step: ... }, ... ] as a list of steps.
    """
    if parallel_val is None:
        return [], False
    if isinstance(parallel_val, list):
        return list(parallel_val), False
    if isinstance(parallel_val, dict):
        ff = bool(
            parallel_val.get("fail-fast", parallel_val.get("fail_fast", False))
        )
        steps = parallel_val.get("steps")
        if isinstance(steps, list):
            return steps, ff
        return [], ff
    return [], False


def abort_siblings_on_step_failure(step: dict, group_fail_fast: bool) -> bool:
    """
    Whether a failed step should trigger stopping other parallel siblings.
    Mirrors Bitbucket: group fail-fast + per-step fail-fast overrides.
    """
    if step.get("fail-fast") is False or step.get("fail_fast") is False:
        return False
    if step.get("fail-fast") is True or step.get("fail_fast") is True:
        return True
    return group_fail_fast


def run_parallel_group(
    raw_items: list[Any],
    *,
    group_fail_fast: bool,
    spawn: Callable[[int, dict], subprocess.Popen | None],
    wait: Callable[[subprocess.Popen], int] = lambda p: p.wait(),
    terminate: Callable[[subprocess.Popen], None] = lambda p: p.terminate(),
    finalize: Callable[[int, dict, int], int] | None = None,
) -> tuple[bool, list[bool]]:
    """
    Run unwrapped parallel child steps concurrently.

    spawn(index, step_dict) returns Popen or None (skip / no process).
    On fail-fast, other running processes are terminated.
    finalize(index, step, script_rc) may run after-script and return the
    combined exit code.

    Returns (all_succeeded, per_index_success).
    """
    steps = [unwrap_step_item(x) for x in raw_items]
    n = len(steps)
    if n == 0:
        return True, []

    active: list[subprocess.Popen | None] = [None] * n
    lock = threading.Lock()
    results: list[bool] = [True] * n
    fail_fast_triggered = threading.Event()

    def terminate_others(except_index: int) -> None:
        with lock:
            for j, proc in enumerate(active):
                if j == except_index or proc is None:
                    continue
                with contextlib.suppress(ProcessLookupError, OSError):
                    terminate(proc)

    def work(i: int) -> None:
        step = steps[i]
        if not isinstance(step, dict):
            results[i] = True
            return

        proc: subprocess.Popen | None
        try:
            proc = spawn(i, step)
        except Exception as e:
            results[i] = False
            label = (
                step.get("name", f"step {i + 1}")
                if isinstance(step, dict)
                else f"step {i + 1}"
            )
            print(
                f"❌ Could not start parallel step {label!r}: "
                f"{explain_process_launch_error(e)}"
            )
            if abort_siblings_on_step_failure(step, group_fail_fast):
                fail_fast_triggered.set()
                terminate_others(-1)
            return

        if proc is None:
            results[i] = True
            return

        with lock:
            active[i] = proc
        try:
            rc = wait(proc)
        finally:
            with lock:
                active[i] = None

        if finalize is not None:
            rc = finalize(i, step, rc)

        results[i] = rc == 0
        if not results[i] and abort_siblings_on_step_failure(step, group_fail_fast):
            fail_fast_triggered.set()
            terminate_others(i)

    pool = ThreadPoolExecutor(max_workers=min(32, max(1, n)))
    try:
        futures = [pool.submit(work, i) for i in range(n)]
        pending = set(futures)

        while pending:
            done, pending = futures_wait(pending, timeout=0.1, return_when=FIRST_COMPLETED)
            for f in done:
                f.result()

            if fail_fast_triggered.is_set():
                for f in list(pending):
                    f.cancel()
                break

        if fail_fast_triggered.is_set() and pending:
            deadline = time.monotonic() + 2.0
            while pending and time.monotonic() < deadline:
                done, pending = futures_wait(pending, timeout=0.05, return_when=FIRST_COMPLETED)
                for f in done:
                    f.result()
    finally:
        pool.shutdown(wait=False, cancel_futures=True)

    return all(results), results
