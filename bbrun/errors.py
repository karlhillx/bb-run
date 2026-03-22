"""
User-facing messages for failed step launches and script exits.
"""

from __future__ import annotations

import os


def explain_process_launch_error(exc: BaseException) -> str:
    """Turn errors from subprocess.Popen (or pull failures) into short, actionable text."""
    if isinstance(exc, FileNotFoundError):
        fn = getattr(exc, "filename", None)
        if fn is None and exc.args:
            a0 = exc.args[0]
            if isinstance(a0, str):
                fn = a0
        if isinstance(fn, str) and os.path.basename(fn) == "docker":
            return (
                "could not run `docker` (executable not on PATH). "
                "Install Docker or use bb-run --mode host."
            )
        if isinstance(fn, str):
            return (
                f"no such file or directory while starting the step ({fn!r}). "
                "If this path is inside your repo, create it in an earlier command "
                "in the same step."
            )
        return f"could not start process: {exc}"

    if isinstance(exc, PermissionError):
        fn = getattr(exc, "filename", None)
        if isinstance(fn, str):
            return f"permission denied ({fn!r})."
        return f"permission denied: {exc}"

    if isinstance(exc, OSError):
        return f"could not start process: {exc}"

    return str(exc)


def report_step_script_failure(
    step_name: str, exit_code: int, *, docker: bool
) -> None:
    """Print context after a pipeline script exits non-zero."""
    print(f"❌ Step {step_name!r} failed (exit code {exit_code}).")
    print("   Scroll up for output from your pipeline script.")
    if docker:
        print(
            "   In Docker mode the repo is mounted at "
            "/opt/atlassian/pipelines/agent/build. "
            "“No such file or directory” for .venv or binaries usually means "
            "that path is not created yet in this step—run setup first in the "
            "same script block."
        )
