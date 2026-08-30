#!/usr/bin/env python3
"""
bb-run CLI - Bitbucket Pipelines Local Runner
"""

import argparse
import contextlib
import json
import sys
from pathlib import Path

from . import __version__
from .caches import step_cache_names
from .discover import git_branch, resolve_repo_path
from .docker import DockerRunner, docker_daemon_available
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
from .validator import PipelineValidator


def list_targets(repo_path: Path, json_output: bool = False) -> int:
    """List available pipeline targets."""
    pipeline_file = repo_path / "bitbucket-pipelines.yml"
    if not pipeline_file.exists():
        if json_output:
            print(json.dumps({"error": f"bitbucket-pipelines.yml not found in {repo_path}"}))
        else:
            print(f"Error: bitbucket-pipelines.yml not found in {repo_path}")
        return 1

    validator = PipelineValidator(repo_path)
    config = validator.load()

    if not config:
        if json_output:
            print(json.dumps({"error": "bitbucket-pipelines.yml not found or invalid"}))
        else:
            print("Error: Could not read or parse bitbucket-pipelines.yml")
        return 1

    if "pipelines" not in config:
        if json_output:
            print(json.dumps({"error": "Missing 'pipelines' key in bitbucket-pipelines.yml"}))
        else:
            print("Error: Missing 'pipelines' key in bitbucket-pipelines.yml")
        return 1

    targets = collect_targets(config)
    image = config.get("image", "atlassian/default-image:latest")

    if json_output:
        print(json.dumps({"targets": targets, "default_image": image}))
        return 0

    print("Available pipeline targets:")
    for target in targets:
        print(f"  {target}")

    print(f"\nDefault image: {image}")
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
    chosen = resolve_auto_target(config, git_branch(repo_path))
    return chosen


def resolve_mode(mode: str, *, quiet: bool) -> tuple[str, str]:
    """Return ``(mode, reason)``. *mode* is ``auto``, ``docker``, or ``host``."""
    if mode == "docker":
        return "docker", "forced"
    if mode == "host":
        return "host", "forced"
    if docker_daemon_available():
        reason = "Docker daemon is available"
        if not quiet:
            print(f"Mode: auto → docker ({reason})")
        return "docker", reason
    reason = "Docker not available; using host"
    if not quiet:
        print(f"Mode: auto → host ({reason})")
    return "host", reason


def dry_run(
    repo_path: Path,
    target: str,
    branch: str,
    mode: str,
    json_output: bool = False,
    step_names: list[str] | None = None,
    mode_reason: str = "",
) -> int:
    """Show the selected pipeline plan without executing steps."""
    validator = PipelineValidator(repo_path)
    config = validator.load()
    if not config or "pipelines" not in config:
        if json_output:
            print(json.dumps({"error": "bitbucket-pipelines.yml not found or invalid"}))
        else:
            print("Error: Could not read or parse bitbucket-pipelines.yml")
        return 1

    steps = get_steps_for_target(config, target)
    steps = filter_pipeline_items(steps, step_names)
    if not steps:
        if json_output:
            print(json.dumps({"error": f"No steps found for target: {target}"}))
        else:
            if step_names:
                print(f"No steps matched: {', '.join(step_names)}")
            else:
                print(f"No steps found for target: {target}")
            print("Hint: bb-run --list-targets")
        return 1

    plan = _step_plan(steps, config)
    if json_output:
        print(
            json.dumps(
                {
                    "target": target,
                    "branch": branch,
                    "mode": mode,
                    "mode_reason": mode_reason,
                    "default_image": config.get("image", "atlassian/default-image:latest"),
                    "steps": plan,
                }
            )
        )
        return 0

    print("Dry run — no commands executed")
    print(f"Repository: {repo_path}")
    print(f"Target: {target}")
    print(f"Branch: {branch}")
    print(f"Mode: {mode.upper()}")
    print(f"Image: {config.get('image', 'atlassian/default-image:latest')}")
    print("\nPlan:")
    for entry in plan:
        if entry["type"] == "parallel":
            note = "fail-fast" if entry["fail_fast"] else "no fail-fast"
            print(f"  {entry['index']}. parallel ({len(entry['steps'])} steps, {note})")
            for child in entry["steps"]:
                _print_plan_step(child, indent=6)
        else:
            _print_plan_step(entry, indent=2)
    return 0


def _print_plan_step(entry: dict, indent: int) -> None:
    prefix = " " * indent
    extras = []
    if entry.get("services"):
        extras.append("services=" + ",".join(entry["services"]))
    if entry.get("caches"):
        extras.append("caches=" + ",".join(entry["caches"]))
    extra = f" ({'; '.join(extras)})" if extras else ""
    print(f"{prefix}{entry['index']}. {entry['name']}{extra}")
    for line in entry.get("script") or []:
        shown = line if len(line) <= 70 else line[:67] + "..."
        print(f"{prefix}   $ {shown}")
    if entry.get("after_script"):
        print(f"{prefix}   after-script:")
        for line in entry["after_script"]:
            shown = line if len(line) <= 70 else line[:67] + "..."
            print(f"{prefix}     $ {shown}")


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
    )

    return 0 if success else 1


def validate(repo_path: Path, json_output: bool = False) -> int:
    """Validate a pipeline YAML file."""
    validator = PipelineValidator(repo_path)

    if validator.validate():
        if json_output:
            config = validator.config or {}
            image = config.get("image", "atlassian/default-image:latest")
            print(json.dumps({
                "valid": True,
                "default_image": image,
                "targets": collect_targets(config),
            }))
            return 0

        print("✅ Valid bitbucket-pipelines.yml")
        validator.show_summary()
        return 0

    if json_output:
        print(json.dumps({"valid": False}))
        return 1

    print("❌ Invalid or missing bitbucket-pipelines.yml")
    return 1


def _cli_dispatch() -> int:
    parser = argparse.ArgumentParser(
        prog="bb-run",
        description="Run Bitbucket Pipelines locally",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  uvx bb-run                                # zero-install; auto target + mode
  bb-run                                    # Run the resolved pipeline
  bb-run --target branches.main            # Run main branch pipeline
  bb-run --repo /path/to/repo              # Run in specific repo
  bb-run --branch feature-x                # Simulate running on a branch
  bb-run --mode host                       # Run on host (no Docker)
  bb-run --mode docker                     # Run in Docker
  bb-run --step "Unit tests"               # Run only named steps
  bb-run -v KEY=VALUE                      # Pass variables
  bb-run --list-targets                    # List available targets
  bb-run --validate                        # Validate YAML only
  bb-run --list-targets --json             # List targets as JSON
  bb-run --validate --json                 # Validate as JSON
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
        default="auto",
        help="Execution mode (default: auto — Docker if the daemon is up, else host)",
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
        "--json",
        action="store_true",
        help="Output JSON for --list-targets, --validate, or --dry-run",
    )
    parser.add_argument(
        "--list-targets",
        action="store_true",
        help="List available pipeline targets and exit",
    )
    parser.add_argument(
        "--validate",
        action="store_true",
        help="Validate YAML only, do not run",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show the selected target plan without executing steps",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Print resolved target/branch/tag, extra -v values, and docker argv",
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"%(prog)s {__version__}",
    )

    args = parser.parse_args()

    if args.json and not (args.list_targets or args.validate or args.dry_run):
        print("Error: --json is only supported with --list-targets, --validate, or --dry-run")
        return 2

    try:
        repo_path = resolve_repo_path(args.repo)
    except OSError as e:
        print(f"Error: Could not resolve path {args.repo!r}: {e}", file=sys.stderr)
        return 1

    if not repo_path.is_dir():
        print(f"Error: Not a directory: {repo_path}", file=sys.stderr)
        return 1

    variables = {}
    if args.variables:
        for var in args.variables:
            if "=" not in var:
                print(f"Error: Invalid variable '{var}'. Expected KEY=VALUE.")
                return 2
            key, value = var.split("=", 1)
            if not key:
                print(f"Error: Invalid variable '{var}'. Key cannot be empty.")
                return 2
            variables[key] = value

    if args.list_targets:
        return list_targets(repo_path, json_output=args.json)

    if args.validate:
        return validate(repo_path, json_output=args.json)

    quiet_mode = args.json
    mode, mode_reason = resolve_mode(args.mode, quiet=quiet_mode)

    validator = PipelineValidator(repo_path)
    config = validator.load()
    if not config or "pipelines" not in config:
        if args.dry_run and args.json:
            print(json.dumps({"error": "bitbucket-pipelines.yml not found or invalid"}))
            return 1
        pipeline_file = repo_path / "bitbucket-pipelines.yml"
        if not pipeline_file.exists():
            print(f"Error: bitbucket-pipelines.yml not found in {repo_path}")
            print("Tip: run from your repository root, or pass --repo /path/to/repo")
            return 1
        print("Error: Could not read or parse bitbucket-pipelines.yml")
        return 1

    target = choose_target(config, repo_path, args.target)
    if args.target is None and not args.json:
        print(f"Target: auto → {target}")

    if args.dry_run:
        return dry_run(
            repo_path,
            target=target,
            branch=args.branch,
            mode=mode,
            json_output=args.json,
            step_names=args.steps,
            mode_reason=mode_reason,
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
        print("\nInterrupted.", file=sys.stderr)
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
