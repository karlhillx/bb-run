"""``bb-run --doctor``: a short health check before a real run."""

from __future__ import annotations

import json
import sys
from dataclasses import dataclass
from pathlib import Path

from .discover import git_branch
from .docker import docker_daemon_status, missing_docker_credential_helper
from .pipeline import collect_targets, resolve_auto_target
from .ui import get_ui
from .validator import PipelineValidator
from .version import __version__


@dataclass
class DoctorReport:
    python: str
    bb_run: str
    repo: str
    pipeline_path: str | None
    valid: bool
    error: str | None
    targets: list[str]
    docker: bool
    docker_detail: str
    cred_helper: str | None
    mode: str
    git_branch: str | None
    auto_target: str | None

    @property
    def ok(self) -> bool:
        return self.valid


def inspect_environment(repo_path: Path) -> DoctorReport:
    validator = PipelineValidator(repo_path)
    pipeline_file = repo_path / "bitbucket-pipelines.yml"
    pipeline_path = str(pipeline_file) if pipeline_file.is_file() else None
    config = validator.load()
    valid = bool(config) and "pipelines" in config
    if config and not valid:
        validator.last_error = "Missing 'pipelines' key"
    targets = collect_targets(config) if config and valid else []
    docker, docker_detail = docker_daemon_status()
    cred_helper = missing_docker_credential_helper() if docker else None
    branch = git_branch(repo_path)
    auto_target = resolve_auto_target(config, branch) if config and valid else None
    return DoctorReport(
        python=".".join(str(part) for part in sys.version_info[:3]),
        bb_run=__version__,
        repo=str(repo_path),
        pipeline_path=pipeline_path,
        valid=valid,
        error=validator.last_error,
        targets=targets,
        docker=docker,
        docker_detail=docker_detail,
        cred_helper=cred_helper,
        mode="docker" if docker else "host",
        git_branch=branch,
        auto_target=auto_target,
    )


def print_doctor(report: DoctorReport, *, json_output: bool) -> int:
    if json_output:
        print(
            json.dumps(
                {
                    "ok": report.ok,
                    "python": report.python,
                    "bb_run": report.bb_run,
                    "repo": report.repo,
                    "pipeline": report.pipeline_path,
                    "valid": report.valid,
                    "error": report.error,
                    "targets": report.targets,
                    "docker": report.docker,
                    "docker_detail": report.docker_detail,
                    "cred_helper_missing": report.cred_helper,
                    "mode": report.mode,
                    "git_branch": report.git_branch,
                    "auto_target": report.auto_target,
                }
            )
        )
        return 0 if report.ok else 1

    ui = get_ui()
    ui.title(f"bb-run {report.bb_run}  doctor")
    ui.blank()
    ui.kv("Python", report.python)
    ui.kv("Package", report.bb_run)
    ui.kv("Repository", report.repo)

    if report.pipeline_path:
        ui.kv("Pipeline", report.pipeline_path)
    else:
        ui.kv("Pipeline", "not found")

    if report.valid:
        n = len(report.targets)
        label = "1 target" if n == 1 else f"{n} targets"
        ui.kv("YAML", f"valid  {ui.sep}  {label}")
    else:
        ui.kv("YAML", report.error or "invalid")

    if report.docker:
        ui.kv("Docker", "available")
        if report.cred_helper:
            ui.kv("Creds", f"{report.cred_helper} missing")
        ui.kv("Mode", "docker")
    else:
        ui.kv("Docker", report.docker_detail)
        ui.kv("Mode", "host  (fallback)")

    ui.kv("Git branch", report.git_branch or "unknown")
    if report.auto_target:
        ui.kv("Auto target", report.auto_target)

    ui.blank(persist=True)
    if not report.pipeline_path:
        ui.failure("No bitbucket-pipelines.yml here.")
        ui.note("cd into the project, or pass --repo /path/to/repo.", persist=True)
        return 1
    if not report.valid:
        ui.failure("The pipeline file is not valid yet.")
        ui.note("Fix the YAML, then try: bb-run --validate", persist=True)
        return 1

    target = report.auto_target or "default"
    if report.docker:
        ui.success(f"Looks good. Next: bb-run   (target {target}, docker mode)")
        if report.cred_helper:
            ui.note(
                f"{report.cred_helper} is not on PATH. Image pulls may fail. "
                "Use --mode host, or remove credsStore from ~/.docker/config.json.",
                persist=True,
            )
    else:
        ui.success(f"Looks good. Next: bb-run   (target {target}, host mode)")
        ui.note(
            "Start Docker Desktop or OrbStack for containers, then pass --mode docker. "
            "Service sidecars also need a running daemon.",
            persist=True,
        )
    return 0
