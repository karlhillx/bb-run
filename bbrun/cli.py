#!/usr/bin/env python3
"""
bb-run CLI - Bitbucket Pipelines Local Runner
"""

from __future__ import annotations

import argparse
import contextlib
import json
import os
import sys
import traceback
from pathlib import Path

from .caches import step_cache_names
from .discover import git_branch, resolve_repo_path
from .docker import DockerRunner, docker_daemon_status
from .doctor import inspect_environment, print_doctor
from .envfile import EnvFileError, parse_env_file
from .host import HostRunner
from .pipeline import (
    after_script_key,
    collect_targets,
    filter_pipeline_items,
    get_steps_for_target,
    parse_parallel_block,
    resolve_auto_target,
    unwrap_step_item,
)
from .services import resolve_service_specs
from .ui import configure_ui, get_ui
from .validator import PipelineValidator
from .version import __version__


def list_targets(repo_path: Path, json_output: bool = False) -> int:
    """List available pipeline targets."""
    ui = get_ui()
    validator = PipelineValidator(repo_path)
    config = validator.load()

    if not config:
        if json_output:
            print(json.dumps({"error": validator.last_error or "invalid pipeline"}))
        else:
            ui.error(validator.last_error or "Could not read or parse bitbucket-pipelines.yml")
        return 1

    if "pipelines" not in config:
        msg = "Missing 'pipelines' key in bitbucket-pipelines.yml"
        if json_output:
            print(json.dumps({"error": msg}))
        else:
            ui.error(msg)
        return 1

    targets = collect_targets(config)
    image = config.get("image", "atlassian/default-image:latest")

    if json_output:
        print(json.dumps({"targets": targets, "default_image": image}))
        return 0

    ui.info("Available pipeline targets:")
    for target in targets:
        ui.info(f"  {target}")

    ui.info(f"\nDefault image: {image}")
    return 0


def _script_preview(step: dict, key: str) -> list[str]:
    raw = step.get(key)
    if raw is None:
        return []
    if isinstance(raw, list):
        return [str(item) for item in raw]
    return [str(raw)]


def _step_detail(step: dict, config: dict, index: int) -> dict:
    after_key = after_script_key(step)
    services = [spec.name for spec in resolve_service_specs(config, step)]
    return {
        "index": index,
        "type": "step",
        "name": step.get("name", f"Step {index}"),
        "script": _script_preview(step, "script"),
        "after_script": _script_preview(step, after_key) if after_key else [],
        "services": services,
        "caches": step_cache_names(step),
    }


def _step_plan(items: list, config: dict) -> list[dict]:
    """Return a compact, serializable plan for top-level steps."""
    plan: list[dict] = []
    for i, item in enumerate(items):
        if isinstance(item, dict) and "parallel" in item:
            raw, fail_fast = parse_parallel_block(item["parallel"])
            children = []
            for j, child in enumerate(raw):
                step = unwrap_step_item(child)
                children.append(_step_detail(step, config, j + 1))
            plan.append(
                {
                    "index": i + 1,
                    "type": "parallel",
                    "fail_fast": fail_fast,
                    "steps": children,
                }
            )
            continue

        step = unwrap_step_item(item)
        plan.append(_step_detail(step, config, i + 1))
    return plan


def choose_target(config: dict, repo_path: Path, target: str | None) -> str:
    if target:
        return target
    return resolve_auto_target(config, git_branch(repo_path))


def resolve_mode(mode: str) -> tuple[str, str]:
    """Return ``(mode, reason)``. *mode* is ``auto``, ``docker``, or ``host``."""
    if mode == "docker":
        return "docker", ""
    if mode == "host":
        return "host", ""
    ok, detail = docker_daemon_status()
    if ok:
        return "docker", "Docker daemon is available"
    if detail == "docker CLI not found":
        return "host", "Docker not available; using host"
    return "host", f"{detail}; using host"


def dry_run(
    repo_path: Path,
    target: str,
    branch: str,
    mode: str,
    json_output: bool = False,
    step_names: list[str] | None = None,
    mode_reason: str = "",
    target_reason: str = "",
) -> int:
    """Show the selected pipeline plan without executing steps."""
    ui = get_ui()
    validator = PipelineValidator(repo_path)
    config = validator.load()
    if not config or "pipelines" not in config:
        if json_output:
            print(
                json.dumps(
                    {
                        "error": validator.last_error
                        or "bitbucket-pipelines.yml not found or invalid"
                    }
                )
            )
        else:
            ui.error(
                validator.last_error or "Could not read or parse bitbucket-pipelines.yml"
            )
        return 1

    steps = get_steps_for_target(config, target)
    steps = filter_pipeline_items(steps, step_names)
    if not steps:
        if json_output:
            print(json.dumps({"error": f"No steps found for target: {target}"}))
        else:
            if step_names:
                ui.error(f"No steps matched: {', '.join(step_names)}")
            else:
                ui.error(f"No steps found for target: {target}")
            ui.note("List names with: bb-run --list-targets", persist=True)
        return 1

    plan = _step_plan(steps, config)
    if json_output:
        print(
            json.dumps(
                {
                    "target": target,
                    "target_reason": target_reason,
                    "branch": branch,
                    "mode": mode,
                    "mode_reason": mode_reason,
                    "default_image": config.get("image", "atlassian/default-image:latest"),
                    "steps": plan,
                }
            )
        )
        return 0

    ui.title(f"bb-run {__version__}")
    ui.note("Dry run — nothing will be executed.")
    ui.blank()
    ui.kv("Repository", str(repo_path))
    target_value = f"{target}  ({target_reason})" if target_reason else target
    ui.kv("Target", target_value)
    ui.kv("Branch", branch)
    mode_value = f"{mode}  ({mode_reason})" if mode_reason else mode
    ui.kv("Mode", mode_value)
    ui.kv("Image", str(config.get("image", "atlassian/default-image:latest")))
    ui.blank()
    ui.info("Plan:")
    for entry in plan:
        if entry["type"] == "parallel":
            note = "fail-fast" if entry["fail_fast"] else "no fail-fast"
            ui.info(f"  {entry['index']}. parallel ({len(entry['steps'])} steps, {note})")
            for child in entry["steps"]:
                _print_plan_step(child, indent=6)
        else:
            _print_plan_step(entry, indent=2)
    return 0


def _print_plan_step(entry: dict, indent: int) -> None:
    ui = get_ui()
    prefix = " " * indent
    extras = []
    if entry.get("services"):
        extras.append("services=" + ",".join(entry["services"]))
    if entry.get("caches"):
        extras.append("caches=" + ",".join(entry["caches"]))
    extra = f" ({'; '.join(extras)})" if extras else ""
    ui.info(f"{prefix}{entry['index']}. {entry['name']}{extra}")
    for line in entry.get("script") or []:
        shown = line if len(line) <= 70 else line[:67] + "..."
        ui.info(f"{prefix}   $ {shown}")
    if entry.get("after_script"):
        ui.info(f"{prefix}   after-script:")
        for line in entry["after_script"]:
            shown = line if len(line) <= 70 else line[:67] + "..."
            ui.info(f"{prefix}     $ {shown}")


def run_pipeline(
    repo_path: Path,
    target: str,
    branch: str,
    variables: dict,
    mode: str,
    verbose: bool,
    tag: str,
    step_names: list[str] | None,
    enable_services: bool,
    enable_caches: bool,
    target_reason: str,
    mode_reason: str,
) -> int:
    """Run a pipeline in the specified mode."""
    runner = DockerRunner(repo_path) if mode == "docker" else HostRunner(repo_path)

    success = runner.run(
        target=target,
        branch=branch,
        variables=variables,
        verbose=verbose,
        tag=tag,
        step_names=step_names,
        enable_services=enable_services,
        enable_caches=enable_caches,
        target_reason=target_reason,
        mode_reason=mode_reason,
    )

    return 0 if success else 1


def validate(repo_path: Path, json_output: bool = False) -> int:
    """Validate a pipeline YAML file."""
    validator = PipelineValidator(repo_path)

    if validator.validate():
        if json_output:
            config = validator.config or {}
            image = config.get("image", "atlassian/default-image:latest")
            print(
                json.dumps(
                    {
                        "valid": True,
                        "default_image": image,
                        "targets": collect_targets(config),
                    }
                )
            )
            return 0

        get_ui().success("Valid bitbucket-pipelines.yml")
        validator.show_summary()
        return 0

    if json_output:
        print(json.dumps({"valid": False, "error": validator.last_error}))
        return 1

    return 1


def _default_mode() -> str:
    raw = os.environ.get("BB_RUN_MODE", "auto").strip().lower()
    if raw in {"auto", "docker", "host"}:
        return raw
    return "auto"


def _load_variables(
    env_files: list[str] | None, cli_vars: list[str] | None
) -> dict[str, str] | int:
    """Merge env files then ``-v`` flags. Returns a dict or an exit code."""
    ui = get_ui()
    variables: dict[str, str] = {}
    for raw_path in env_files or []:
        path = Path(raw_path).expanduser()
        try:
            variables.update(parse_env_file(path))
        except EnvFileError as exc:
            ui.error(str(exc))
            return 1
    if cli_vars:
        for var in cli_vars:
            if "=" not in var:
                ui.error(f"Invalid variable {var!r}. Expected KEY=VALUE.")
                return 2
            key, value = var.split("=", 1)
            if not key:
                ui.error(f"Invalid variable {var!r}. Key cannot be empty.")
                return 2
            variables[key] = value
    return variables


def _cli_dispatch() -> int:
    parser = argparse.ArgumentParser(
        prog="bb-run",
        description="Run Bitbucket Pipelines locally",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  uvx bb-run                                # zero-install; auto target + mode
  bb-run                                    # Run the resolved pipeline
  bb-run --doctor                           # Check Docker, YAML, and auto target
  bb-run --target branches.main            # Run main branch pipeline
  bb-run --repo /path/to/repo              # Run in specific repo
  bb-run --branch feature-x                # Simulate running on a branch
  bb-run --mode host                       # Run on host (no Docker)
  bb-run --mode docker                     # Run in Docker
  bb-run --step "Unit tests"               # Run only named steps
  bb-run --env-file .env -v KEY=VALUE      # Pass variables
  bb-run --list-targets                    # List available targets
  bb-run --validate                        # Validate YAML only
  bb-run --dry-run                         # Show selected steps without executing
  python3 -m bbrun --version               # If bb-run is not on PATH
        """,
    )

    parser.add_argument(
        "--repo",
        "-r",
        default=".",
        help="Path to repository (default: . — walk up for "
        "bitbucket-pipelines.yml; an explicit path is used as-is)",
    )
    parser.add_argument(
        "--target",
        "-t",
        default=None,
        help="Pipeline target (default: auto from git branch / default / "
        "pull-requests.**)",
    )
    parser.add_argument(
        "--branch",
        "-b",
        default="LOCAL",
        help="Branch name to simulate (default: LOCAL)",
    )
    parser.add_argument(
        "--tag",
        default="",
        help="Tag name for BITBUCKET_TAG (tag pipelines)",
    )
    parser.add_argument(
        "--mode",
        "-m",
        choices=["auto", "docker", "host"],
        default=_default_mode(),
        help="Execution mode (default: auto — Docker if the daemon is up, else host; "
        "override with BB_RUN_MODE)",
    )
    parser.add_argument(
        "--step",
        "--only",
        dest="steps",
        action="append",
        metavar="NAME",
        help="Run only steps with this name (repeatable)",
    )
    parser.add_argument(
        "--no-services",
        action="store_true",
        help="Do not start definitions.services sidecars",
    )
    parser.add_argument(
        "--no-cache",
        action="store_true",
        help="Do not restore or save step caches",
    )
    parser.add_argument(
        "--variables",
        "-v",
        action="append",
        help="Variables in KEY=VALUE format",
    )
    parser.add_argument(
        "--env-file",
        action="append",
        metavar="PATH",
        help="Load KEY=VALUE pairs from a file (repeatable; -v wins)",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output JSON for --list-targets, --validate, --dry-run, or --doctor",
    )
    parser.add_argument(
        "--list-targets",
        action="store_true",
        help="List available pipeline targets and exit",
    )
    parser.add_argument(
        "--validate",
        "--check",
        action="store_true",
        dest="validate",
        help="Validate YAML only, do not run",
    )
    parser.add_argument(
        "--doctor",
        action="store_true",
        help="Check Python, Docker, and the pipeline file, then exit",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show the selected target plan without executing steps",
    )
    parser.add_argument(
        "--quiet",
        "-q",
        action="store_true",
        help="Less bb-run chatter (step output is unchanged)",
    )
    parser.add_argument(
        "--color",
        choices=["auto", "always", "never"],
        default="auto",
        help="Color output (default: auto; also NO_COLOR / FORCE_COLOR)",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Print extra -v keys (secrets redacted) and docker argv",
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"%(prog)s {__version__}",
    )

    args = parser.parse_args()

    json_ok = args.list_targets or args.validate or args.dry_run or args.doctor
    color = "never" if args.json else args.color
    inspect = json_ok
    quiet = bool(args.json or (args.quiet and not inspect))
    configure_ui(color=color, quiet=quiet)
    ui = get_ui()

    if args.json and not json_ok:
        ui.error(
            "--json is only supported with --list-targets, --validate, --dry-run, or --doctor"
        )
        return 2

    env_mode = os.environ.get("BB_RUN_MODE", "").strip().lower()
    if env_mode and env_mode not in {"auto", "docker", "host"}:
        ui.warn(f"Ignoring invalid BB_RUN_MODE={env_mode!r} (use auto, docker, or host)")

    try:
        repo_path = resolve_repo_path(args.repo)
    except OSError as e:
        ui.error(f"Could not resolve path {args.repo!r}: {e}")
        return 1

    if not repo_path.is_dir():
        ui.error(f"Not a directory: {repo_path}")
        return 1

    loaded = _load_variables(args.env_file, args.variables)
    if isinstance(loaded, int):
        return loaded
    variables = loaded

    if args.list_targets:
        return list_targets(repo_path, json_output=args.json)

    if args.validate:
        return validate(repo_path, json_output=args.json)

    if args.doctor:
        return print_doctor(inspect_environment(repo_path), json_output=args.json)

    mode, mode_reason = resolve_mode(args.mode)
    if (
        args.mode == "auto"
        and mode == "host"
        and "daemon is not running" in mode_reason.lower()
        and not args.json
    ):
        ui.warn(mode_reason, persist=True)
        ui.note(
            "Start Docker Desktop or OrbStack, then re-run. "
            "Pass --mode docker to require containers.",
            persist=True,
        )

    validator = PipelineValidator(repo_path)
    config = validator.load()
    if not config or "pipelines" not in config:
        if args.dry_run and args.json:
            print(
                json.dumps(
                    {
                        "error": validator.last_error
                        or "bitbucket-pipelines.yml not found or invalid"
                    }
                )
            )
            return 1
        if validator.last_error:
            ui.error(validator.last_error)
            if "not found" in validator.last_error:
                ui.note(
                    "Run from your repository root, or pass --repo /path/to/repo",
                    persist=True,
                )
            return 1
        ui.error("Could not read or parse bitbucket-pipelines.yml")
        return 1

    target = choose_target(config, repo_path, args.target)
    target_reason = "" if args.target else "auto"

    if args.dry_run:
        return dry_run(
            repo_path,
            target=target,
            branch=args.branch,
            mode=mode,
            json_output=args.json,
            step_names=args.steps,
            mode_reason=mode_reason,
            target_reason=target_reason,
        )

    return run_pipeline(
        repo_path=repo_path,
        target=target,
        branch=args.branch,
        variables=variables,
        mode=mode,
        verbose=args.verbose,
        tag=args.tag,
        step_names=args.steps,
        enable_services=not args.no_services,
        enable_caches=not args.no_cache,
        target_reason=target_reason,
        mode_reason=mode_reason,
    )


def _line_buffer_stdio() -> None:
    """Keep banners ahead of child output when stdout is a pipe."""
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is None:
            continue
        with contextlib.suppress(OSError, ValueError):
            reconfigure(line_buffering=True)


def main() -> int:
    _line_buffer_stdio()
    try:
        return _cli_dispatch()
    except KeyboardInterrupt:
        get_ui().error("Interrupted.")
        return 130
    except BrokenPipeError:
        with contextlib.suppress(OSError):
            sys.stdout.close()
        return 0
    except Exception as exc:
        ui = get_ui()
        ui.error("bb-run hit an unexpected error.")
        ui.error(f"{type(exc).__name__}: {exc}")
        if "--verbose" in sys.argv or os.environ.get("BB_RUN_DEBUG"):
            traceback.print_exc()
        else:
            ui.note(
                "Re-run with --verbose or BB_RUN_DEBUG=1 for a traceback.",
                persist=True,
            )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
