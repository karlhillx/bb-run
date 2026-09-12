"""
Shared runner orchestration for Docker and host execution modes.

``BaseRunner`` owns everything that is identical between the two modes:
environment scaffolding, the top-level step loop, parallel-group handling,
artifact capture, caches, services, after-script, and result reporting.
Concrete runners only implement the small surface that genuinely differs —
how a single step is spawned, mode-specific environment, and how a running
process is terminated.
"""

from __future__ import annotations

import contextlib
import os
import subprocess
import time
import uuid
from collections.abc import Callable
from pathlib import Path

from .artifacts import ArtifactSession
from .caches import CacheSession, cache_definitions
from .discover import git_origin_urls
from .envfile import redact_variables
from .errors import explain_process_launch_error, report_step_script_failure
from .pipeline import (
    after_script_key,
    count_executable_steps,
    filter_pipeline_items,
    get_steps_for_target,
    parallel_failure_summaries,
    parse_parallel_block,
    run_parallel_group,
    unwrap_step_item,
)
from .services import ServiceSession, resolve_service_specs
from .ui import get_ui
from .validator import PipelineValidator
from .version import __version__

DEFAULT_IMAGE = "atlassian/default-image:latest"


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
        self.tag = ""
        self.step_names: list[str] | None = None
        self.enable_services = True
        self.enable_caches = True
        self.verbose = False
        self.target_reason = ""
        self.mode_reason = ""
        self._config: dict | None = None
        self._pipeline_uuid = str(uuid.uuid4())
        self._run_id = f"{os.getpid()}-{uuid.uuid4().hex[:8]}"
        self._docker_extra_args: list[str] = []
        self._caches: CacheSession | None = None
        self._services: ServiceSession | None = None
        self._step_index = 0
        self._step_total = 0
        self._failed_at: str | None = None

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

    def _base_env(self) -> dict[str, str]:
        """Starting environment for a step. Host copies the process env."""
        return dict(os.environ)

    def _extra_env(self) -> dict[str, str]:
        """Mode-specific environment overrides applied before user variables."""
        return {}

    def _build_env(self, branch: str) -> dict[str, str]:
        """Build the environment passed to each step."""
        http_origin, ssh_origin = git_origin_urls(self.repo_path)
        env = self._base_env()
        env.update(
            {
                "CI": "true",
                "BITBUCKET_BUILD_NUMBER": "1",
                "BITBUCKET_CLONE_DIR": self._clone_dir(),
                "BITBUCKET_COMMIT": self._git_commit(),
                "BITBUCKET_BRANCH": branch,
                "BITBUCKET_TAG": self.tag,
                "BITBUCKET_REPO_SLUG": self.repo_path.name,
                "BITBUCKET_REPO_UUID": f"bb-run-{os.getpid()}",
                "BITBUCKET_WORKSPACE": "local",
                "BITBUCKET_PIPELINE_UUID": self._pipeline_uuid,
                "BITBUCKET_GIT_HTTP_ORIGIN": http_origin,
                "BITBUCKET_GIT_SSH_ORIGIN": ssh_origin,
            }
        )
        env.update(self._extra_env())
        env.update(self.variables)
        return env

    # -- hooks for subclasses --------------------------------------------

    def _preflight(self) -> bool:
        """Return True if the mode is ready to run (e.g. Docker is available)."""
        return True

    def _mode_summary(self, image: str) -> tuple[str, str]:
        """Return ``(mode label, extra detail)`` for the run header."""
        raise NotImplementedError

    def _spawn_step(
        self,
        step: dict,
        env: dict[str, str],
        label: str,
        script_key: str = "script",
    ) -> subprocess.Popen | None:
        """Start a single script block, returning its process or None."""
        raise NotImplementedError

    def _terminate_proc(self, proc: subprocess.Popen) -> None:
        """Terminate a running step (overridden where process groups apply)."""
        with contextlib.suppress(ProcessLookupError, OSError):
            proc.terminate()

    # -- execution --------------------------------------------------------

    def _get_steps(self, config: dict, target: str) -> list:
        return get_steps_for_target(config, target)

    def _print_run_header(
        self,
        target: str,
        branch: str,
        image: str,
        step_count: int,
    ) -> None:
        ui = get_ui()
        mode, mode_detail = self._mode_summary(image)
        ui.title(f"bb-run {__version__}")
        ui.blank()
        ui.kv("Repository", str(self.repo_path))
        target_value = target
        if self.target_reason:
            target_value = f"{target}  ({self.target_reason})"
        ui.kv("Target", target_value)
        mode_value = mode
        if self.mode_reason:
            mode_value = f"{mode}  ({self.mode_reason})"
        elif mode_detail:
            mode_value = f"{mode}  ({mode_detail})"
        ui.kv("Mode", mode_value)
        if self.docker_mode:
            ui.kv("Image", image)
        ui.kv("Branch", branch)
        if self.tag:
            ui.kv("Tag", self.tag)
        steps_label = "1 step" if step_count == 1 else f"{step_count} steps"
        ui.kv("Plan", steps_label)
        if self.verbose:
            if self.variables:
                shown = redact_variables(self.variables)
                ui.kv("Variables", ", ".join(f"{k}={v}" for k, v in shown.items()))
            if self.step_names:
                ui.kv("Filter", ", ".join(self.step_names))

    def _run_script_block(
        self,
        step: dict,
        env: dict[str, str],
        label: str,
        script_key: str,
    ) -> int | None:
        """Run one script/after-script block. None means nothing ran."""
        proc = self._spawn_step(step, env, label, script_key=script_key)
        if proc is None:
            return None
        return proc.wait()

    def _run_after_script(self, step: dict, env: dict[str, str], label: str, script_rc: int) -> int:
        """Run after-script in a new shell. Returns combined exit code."""
        ui = get_ui()
        key = after_script_key(step)
        if key is None:
            return script_rc
        after_env = dict(env)
        after_env["BITBUCKET_EXIT_CODE"] = str(script_rc)
        ui.info(f"{label}after-script (BITBUCKET_EXIT_CODE={script_rc})")
        try:
            after_rc = self._run_script_block(step, after_env, label, key)
        except RuntimeError as exc:
            ui.error(str(exc))
            return script_rc if script_rc != 0 else 1
        except OSError as exc:
            ui.error(explain_process_launch_error(exc))
            return script_rc if script_rc != 0 else 1
        if after_rc is None:
            return script_rc
        if after_rc != 0:
            ui.error(f"after-script failed (exit code {after_rc}).")
            return after_rc if script_rc == 0 else script_rc
        return script_rc

    def _execute_step(self, step: dict, step_name: str, env: dict[str, str]) -> bool:
        """Run one sequential step (script + after-script) and report the outcome."""
        ui = get_ui()
        self._step_index += 1
        ui.step_banner(self._step_index, self._step_total, step_name)

        step_env = dict(env)
        step_env["BITBUCKET_STEP_UUID"] = str(uuid.uuid4())
        started = time.monotonic()

        try:
            rc = self._run_script_block(step, step_env, "", "script")
        except RuntimeError as exc:
            ui.error(str(exc))
            ui.step_result(step_name, False, time.monotonic() - started)
            self._failed_at = step_name
            return False
        except OSError as exc:
            ui.error(explain_process_launch_error(exc))
            ui.step_result(step_name, False, time.monotonic() - started)
            self._failed_at = step_name
            return False

        script_rc = 0 if rc is None else rc
        if rc is not None and rc != 0:
            report_step_script_failure(step_name, rc, docker=self.docker_mode)

        combined = self._run_after_script(step, step_env, "", script_rc)
        ok = combined == 0
        ui.step_result(step_name, ok, time.monotonic() - started)
        if not ok:
            self._failed_at = step_name
        return ok

    def _children_need_services(self, raw: list) -> bool:
        if not self.enable_services:
            return False
        config = self._config or {}
        for item in raw:
            step = unwrap_step_item(item)
            if isinstance(step, dict) and resolve_service_specs(config, step):
                return True
        return False

    def _with_step_sidecars(
        self, step: dict, artifacts: ArtifactSession, body: Callable[[], bool]
    ) -> bool:
        """Restore caches/artifacts, start services, run *body*, then tear down."""
        artifacts.prepare_for_step(step)
        caches = self._caches
        services = self._services
        extra: list[str] = []
        if caches is not None:
            extra.extend(caches.prepare_for_step(step))
        ok = True
        if services is not None:
            specs = resolve_service_specs(self._config or {}, step)
            ok = services.start(specs)
            extra.extend(services.docker_run_args())
        self._docker_extra_args = extra
        try:
            if not ok:
                return False
            return body()
        finally:
            if services is not None:
                services.stop()
            if caches is not None:
                caches.capture_after_step(step)
            self._docker_extra_args = []

    def _run_parallel(
        self, parallel_block, env: dict[str, str], artifacts: ArtifactSession
    ) -> bool:
        """Run a ``parallel:`` group concurrently, honoring fail-fast."""
        ui = get_ui()
        raw, group_ff = parse_parallel_block(parallel_block)
        n = len(raw)
        if n == 0:
            ui.warn("empty parallel group")
            return True

        if self._children_need_services(raw):
            ui.note(
                "Parallel group has services; running children one at a time "
                "so sidecar ports do not clash"
            )
            group_ok = True
            for j, item in enumerate(raw):
                step = unwrap_step_item(item)
                if not isinstance(step, dict):
                    continue
                name = step.get("name", f"step {j + 1}")
                child_env = dict(env)
                child_env["BITBUCKET_PARALLEL_STEP"] = str(j)
                child_env["BITBUCKET_PARALLEL_STEP_COUNT"] = str(n)

                def body(s=step, nm=name, e=child_env) -> bool:
                    return self._execute_step(s, nm, e)

                step_ok = self._with_step_sidecars(step, artifacts, body)
                artifacts.capture_after_step(step, step_ok)
                if not step_ok:
                    group_ok = False
                    if group_ff:
                        ui.error("Parallel group failed")
                        self._failed_at = name
                        return False
            if not group_ok:
                ui.error("Parallel group failed")
                self._failed_at = self._failed_at or "parallel group"
            return group_ok

        # Children share the same restored artifacts; Bitbucket injects per step.
        artifacts.prepare_for_step({})
        if self._caches is not None:
            cache_names: list[str] = []
            for item in raw:
                st = unwrap_step_item(item)
                if isinstance(st, dict):
                    cache_names.extend(st.get("caches") or [])
            if cache_names:
                self._docker_extra_args = self._caches.prepare_for_step(
                    {"caches": list(dict.fromkeys(str(c) for c in cache_names))}
                )

        start = self._step_index + 1
        end = self._step_index + n
        self._step_index = end
        ui.parallel_banner(start, end, self._step_total, n, fail_fast=group_ff)
        for j, item in enumerate(raw):
            st = unwrap_step_item(item)
            name = st.get("name", f"step {j + 1}") if isinstance(st, dict) else j
            ui.info(f"  {ui.bullet} {name}")

        started = time.monotonic()

        def spawn(i: int, step: dict) -> subprocess.Popen | None:
            child_env = dict(env)
            child_env["BITBUCKET_PARALLEL_STEP"] = str(i)
            child_env["BITBUCKET_PARALLEL_STEP_COUNT"] = str(n)
            child_env["BITBUCKET_STEP_UUID"] = str(uuid.uuid4())
            name = step.get("name", f"step {i + 1}") if isinstance(step, dict) else i
            label = f"[parallel {i + 1}/{n} | {name}] "
            return self._spawn_step(step, child_env, label=label, script_key="script")

        def finalize(i: int, step: dict, script_rc: int) -> int:
            child_env = dict(env)
            child_env["BITBUCKET_PARALLEL_STEP"] = str(i)
            child_env["BITBUCKET_PARALLEL_STEP_COUNT"] = str(n)
            child_env["BITBUCKET_STEP_UUID"] = str(uuid.uuid4())
            name = step.get("name", f"step {i + 1}") if isinstance(step, dict) else i
            label = f"[parallel {i + 1}/{n} | {name}] "
            return self._run_after_script(step, child_env, label, script_rc)

        ok, each_ok = run_parallel_group(
            raw,
            group_fail_fast=group_ff,
            spawn=spawn,
            terminate=self._terminate_proc,
            finalize=finalize,
        )

        if self._caches is not None:
            self._caches.capture_after_step({})
            self._docker_extra_args = []

        for i, item in enumerate(raw):
            st = unwrap_step_item(item)
            if isinstance(st, dict) and i < len(each_ok):
                artifacts.capture_after_step(st, each_ok[i])

        elapsed = time.monotonic() - started
        if not ok:
            ui.error("Parallel group failed")
            for line in parallel_failure_summaries(raw, each_ok):
                ui.info(f"   {ui.bullet} {line}", persist=True)
            self._failed_at = "parallel group"
            ui.step_result("parallel group", False, elapsed)
        else:
            ui.step_result("parallel group", True, elapsed)
        return ok

    def run(
        self,
        target: str = "default",
        branch: str = "LOCAL",
        variables: dict | None = None,
        verbose: bool = False,
        *,
        tag: str = "",
        step_names: list[str] | None = None,
        enable_services: bool = True,
        enable_caches: bool = True,
        target_reason: str = "",
        mode_reason: str = "",
    ) -> bool:
        """Run the pipeline for a given target. Returns True on success."""
        ui = get_ui()
        if variables:
            self.variables.update(variables)
        self.verbose = verbose
        self.tag = tag
        self.step_names = step_names
        self.enable_services = enable_services
        self.enable_caches = enable_caches
        self.target_reason = target_reason
        self.mode_reason = mode_reason
        self._step_index = 0
        self._failed_at = None

        if not self._preflight():
            return False

        config = self.validator.load()
        if not config:
            ui.error(self.validator.last_error or "Could not load pipeline")
            return False
        self._config = config

        image = config.get("image", DEFAULT_IMAGE)
        self.default_image = image
        self._caches = CacheSession(
            self.repo_path,
            cache_definitions(config),
            enabled=enable_caches,
            docker_mode=self.docker_mode,
        )
        self._services = ServiceSession(
            enabled=enable_services,
            docker_mode=self.docker_mode,
            run_id=self._run_id,
        )

        steps = self._get_steps(config, target)
        steps = filter_pipeline_items(steps, step_names)
        self._step_total = count_executable_steps(steps)
        if not steps:
            if step_names:
                ui.error(f"No steps matched: {', '.join(step_names)}")
            else:
                ui.error(f"No steps found for target: {target}")
            ui.note("List names with: bb-run --list-targets", persist=True)
            return False

        self._print_run_header(target, branch, image, self._step_total)

        env = self._build_env(branch)
        artifacts = ArtifactSession(self.repo_path)
        all_passed = True
        started = time.monotonic()

        try:
            for i, item in enumerate(steps):
                if isinstance(item, dict) and "parallel" in item:
                    if not self._run_parallel(item["parallel"], env, artifacts):
                        all_passed = False
                        break
                    continue

                step = item.get("step", item) if isinstance(item, dict) else {}
                step_name = step.get("name", f"Step {i + 1}")

                def body(s=step, nm=step_name) -> bool:
                    return self._execute_step(s, nm, env)

                step_ok = self._with_step_sidecars(step, artifacts, body)
                artifacts.capture_after_step(step, step_ok)
                if not step_ok:
                    all_passed = False
                    break
        finally:
            if self._services is not None:
                self._services.stop()

        ui.run_summary(
            ok=all_passed,
            step_count=self._step_total,
            seconds=time.monotonic() - started,
            failed_at=self._failed_at,
        )
        return all_passed
