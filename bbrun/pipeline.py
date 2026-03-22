"""Shared pipeline parsing and parallel step execution."""

from __future__ import annotations

import subprocess
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any, Callable, Dict, List, Optional, Tuple

from .errors import explain_process_launch_error


def unwrap_step_item(item: Any) -> Dict:
    """Normalize a pipeline list entry to the inner step dict."""
    if isinstance(item, dict):
        return item.get("step", item)
    return {}


def parallel_failure_summaries(raw_items: List[Any], each_ok: List[bool]) -> List[str]:
    """Human-readable labels for failed parallel children (for logging)."""
    lines: List[str] = []
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


def parse_parallel_block(parallel_val: Any) -> Tuple[List[Any], bool]:
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


def abort_siblings_on_step_failure(step: Dict, group_fail_fast: bool) -> bool:
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
    raw_items: List[Any],
    *,
    group_fail_fast: bool,
    spawn: Callable[[int, Dict], Optional[subprocess.Popen]],
    wait: Callable[[subprocess.Popen], int] = lambda p: p.wait(),
) -> Tuple[bool, List[bool]]:
    """
    Run unwrapped parallel child steps concurrently.

    spawn(index, step_dict, env) returns Popen or None (skip / no process).
    On fail-fast, other running processes are terminated.

    Returns (all_succeeded, per_index_success).
    """
    steps = [unwrap_step_item(x) for x in raw_items]
    n = len(steps)
    if n == 0:
        return True, []

    active: List[Optional[subprocess.Popen]] = [None] * n
    lock = threading.Lock()
    results: List[bool] = [True] * n

    def terminate_others(except_index: int) -> None:
        with lock:
            for j, proc in enumerate(active):
                if j == except_index or proc is None:
                    continue
                try:
                    proc.terminate()
                except (ProcessLookupError, OSError):
                    pass

    def work(i: int) -> None:
        step = steps[i]
        if not isinstance(step, dict):
            results[i] = True
            return

        proc: Optional[subprocess.Popen]
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

        results[i] = rc == 0
        if not results[i] and abort_siblings_on_step_failure(
            step, group_fail_fast
        ):
            terminate_others(i)

    with ThreadPoolExecutor(max_workers=min(32, max(1, n))) as pool:
        futures = [pool.submit(work, i) for i in range(n)]
        for f in as_completed(futures):
            f.result()

    return all(results), results
