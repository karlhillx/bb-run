"""
Shared runner orchestration for Docker and host execution modes.

``BaseRunner`` owns everything that is identical between the two modes:
environment scaffolding, the top-level step loop, parallel-group handling,
artifact capture, and result reporting. Concrete runners only implement the
small surface that genuinely differs — how a single step is spawned, mode
specific environment, and how a running process is terminated.
"""

from __future__ import annotations

import contextlib
import os
import subprocess
from pathlib import Path

from .artifacts import ArtifactSession
from .errors import explain_process_launch_error, report_step_script_failure
from .pipeline import (
    get_steps_for_target,
    parallel_failure_summaries,
    parse_parallel_block,
    run_parallel_group,
    unwrap_step_item,
)
from .validator import PipelineValidator

DEFAULT_IMAGE = "atlassian/default-image:latest"
_BANNER = "=" * 60


class BaseRunner:
    """Common pipeline execution logic shared by all runner modes."""

    #: Used by :func:`report_step_script_failure` to tailor its hint.
    docker_mode: bool = False

    def __init__(self, repo_path: Path | str) -> None:
        self.repo_path = Path(repo_path)
        self.pipeline_file = self.repo_path / "bitbucket-pipelines.yml"
        self.variables: dict[str, str] = {}
        self.validator = PipelineValidator(self.repo_path)
        self.default_image = DEFAULT_IMAGE

    # -- environment ------------------------------------------------------

    def _git_commit(self) -> str:
        """Best-effort git SHA for ``BITBUCKET_COMMIT`` (``local`` if unknown)."""
        try:
            result = subprocess.run(
                ["git", "rev-parse", "HEAD"],
                capture_output=True,
                text=True,
                cwd=self.repo_path,
            )
        except OSError:
            return "local"
        commit = result.stdout.strip()
        return commit or "local"

    def _clone_dir(self) -> str:
        """Path reported as ``BITBUCKET_CLONE_DIR`` (overridden for Docker)."""
        return str(self.repo_path)

    def _extra_env(self) -> dict[str, str]:
        """Mode-specific environment overrides applied before user variables."""
        return {}

    def _build_env(self, branch: str) -> dict[str, str]:
        """Build the environment passed to each step."""
        env = dict(os.environ)
        env.update(
            {
                "BITBUCKET_BUILD_NUMBER": "1",
                "BITBUCKET_CLONE_DIR": self._clone_dir(),
                "BITBUCKET_COMMIT": self._git_commit(),
                "BITBUCKET_BRANCH": branch,
                "BITBUCKET_REPO_SLUG": self.repo_path.name,
                "BITBUCKET_REPO_UUID": f"bb-run-{os.getpid()}",
                "BITBUCKET_WORKSPACE": "local",
            }
        )
        env.update(self._extra_env())
        env.update(self.variables)
        return env

    # -- hooks for subclasses --------------------------------------------

    def _preflight(self) -> bool:
        """Return True if the mode is ready to run (e.g. Docker is available)."""
        return True

    def _print_mode_lines(self, image: str) -> None:
        """Print the mode-specific portion of the run header."""
        raise NotImplementedError

    def _spawn_step(
        self, step: dict, env: dict[str, str], label: str
    ) -> subprocess.Popen | None:
        """Start a single step, returning its process or None if nothing ran."""
        raise NotImplementedError

    def _terminate_proc(self, proc: subprocess.Popen) -> None:
        """Terminate a running step (overridden where process groups apply)."""
        with contextlib.suppress(ProcessLookupError, OSError):
            proc.terminate()

    # -- execution --------------------------------------------------------

    def _get_steps(self, config: dict, target: str) -> list:
        return get_steps_for_target(config, target)

    def _execute_step(self, step: dict, step_name: str, env: dict[str, str]) -> bool:
        """Run one sequential step and report the outcome."""
        print(f"\n{_BANNER}")
        print(f"Step: {step_name}")
        print(_BANNER)

        try:
            proc = self._spawn_step(step, env, label="")
        except RuntimeError as exc:
            print(f"❌ {exc}")
            return False
        except OSError as exc:
            print(f"❌ {explain_process_launch_error(exc)}")
            return False

        if proc is None:
            return True

        rc = proc.wait()
        if rc != 0:
            report_step_script_failure(step_name, rc, docker=self.docker_mode)
            return False
        return True

    def _run_parallel(
        self, parallel_block, env: dict[str, str], artifacts: ArtifactSession
    ) -> bool:
        """Run a ``parallel:`` group concurrently, honoring fail-fast."""
        raw, group_ff = parse_parallel_block(parallel_block)
        n = len(raw)
        if n == 0:
            print("Warning: empty parallel group")
            return True

        # Children share the same restored artifacts; Bitbucket injects per step.
        artifacts.prepare_for_step({})

        ff_note = "fail-fast: on" if group_ff else "fail-fast: off"
        print(f"\n{_BANNER}")
        print(f"Parallel group ({n} steps, {ff_note})")
        print(_BANNER)
        for j, item in enumerate(raw):
            st = unwrap_step_item(item)
            name = st.get("name", f"step {j + 1}") if isinstance(st, dict) else j
            print(f"  • {name}")

        def spawn(i: int, step: dict) -> subprocess.Popen | None:
            child_env = dict(env)
            child_env["BITBUCKET_PARALLEL_STEP"] = str(i)
            child_env["BITBUCKET_PARALLEL_STEP_COUNT"] = str(n)
            name = step.get("name", f"step {i + 1}") if isinstance(step, dict) else i
            label = f"[parallel {i + 1}/{n} | {name}] "
            return self._spawn_step(step, child_env, label=label)

        ok, each_ok = run_parallel_group(
            raw,
            group_fail_fast=group_ff,
            spawn=spawn,
            terminate=self._terminate_proc,
        )

        for i, item in enumerate(raw):
            st = unwrap_step_item(item)
            if isinstance(st, dict) and i < len(each_ok):
                artifacts.capture_after_step(st, each_ok[i])

        if not ok:
            print("❌ Parallel group failed")
            for line in parallel_failure_summaries(raw, each_ok):
                print(f"   • {line}")
        return ok

    def run(
        self,
        target: str = "default",
        branch: str = "LOCAL",
        variables: dict | None = None,
        verbose: bool = False,
    ) -> bool:
        """Run the pipeline for a given target. Returns True on success."""
        if variables:
            self.variables.update(variables)

        if verbose and self.variables:
            print(f"(verbose) Extra variables: {self.variables}")

        if not self._preflight():
            return False

        config = self.validator.load()
        if not config:
            print("Error: Could not load pipeline")
            return False

        image = config.get("image", DEFAULT_IMAGE)
        self.default_image = image

        print(f"Repository: {self.repo_path}")
        print(f"Target: {target}")
        print(f"Branch: {branch}")
        self._print_mode_lines(image)

        steps = self._get_steps(config, target)
        if not steps:
            print(f"No steps found for target: {target}")
            print("Hint: bb-run --list-targets")
            return False

        env = self._build_env(branch)
        artifacts = ArtifactSession(self.repo_path)
        all_passed = True

        for i, item in enumerate(steps):
            if isinstance(item, dict) and "parallel" in item:
                if not self._run_parallel(item["parallel"], env, artifacts):
                    all_passed = False
                    break
                continue

            step = item.get("step", item) if isinstance(item, dict) else {}
            step_name = step.get("name", f"Step {i + 1}")

            artifacts.prepare_for_step(step)
            step_ok = self._execute_step(step, step_name, env)
            artifacts.capture_after_step(step, step_ok)
            if not step_ok:
                all_passed = False
                break

        print(f"\n{_BANNER}")
        if all_passed:
            print("✅ All steps completed successfully!")
        else:
            print("❌ Pipeline failed!")
        print(_BANNER)

        return all_passed
