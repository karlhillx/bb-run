#!/usr/bin/env python3
"""
bb-run CLI - Bitbucket Pipelines Local Runner
"""

import sys
import json
import argparse
from pathlib import Path
from typing import Dict, List

from . import __version__
from .docker import DockerRunner
from .host import HostRunner
from .validator import PipelineValidator


def _collect_targets(config: Dict) -> List[str]:
    """Collect available pipeline targets from config."""
    targets: List[str] = []
    pipelines = config.get("pipelines", {})

    if "default" in pipelines:
        targets.append("default")

    branches = pipelines.get("branches", {})
    for branch in sorted(branches.keys()):
        targets.append(f"branches.{branch}")

    tags = pipelines.get("tags", {})
    for tag in sorted(tags.keys()):
        targets.append(f"tags.{tag}")

    for name in sorted(pipelines.keys()):
        if name not in ["default", "branches", "tags"]:
            if name == "custom" and isinstance(pipelines.get("custom"), dict):
                for custom_name in sorted(pipelines["custom"].keys()):
                    targets.append(f"custom.{custom_name}")
            elif name == "pull-requests" and isinstance(pipelines.get("pull-requests"), dict):
                for pr_name in sorted(pipelines["pull-requests"].keys()):
                    targets.append(f"pull-requests.{pr_name}")
            else:
                targets.append(name)

    return targets


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

    targets = _collect_targets(config)
    image = config.get("image", "atlassian/default-image:latest")

    if json_output:
        print(json.dumps({"targets": targets, "default_image": image}))
        return 0

    print("Available pipeline targets:")
    for target in targets:
        print(f"  {target}")

    print(f"\nDefault image: {image}")
    return 0


def run_pipeline(
    repo_path: Path,
    target: str,
    branch: str,
    variables: dict,
    mode: str,
    verbose: bool,
) -> int:
    """Run a pipeline in the specified mode."""
    if mode == "docker":
        runner = DockerRunner(repo_path)
    else:
        runner = HostRunner(repo_path)

    success = runner.run(
        target=target,
        branch=branch,
        variables=variables,
        verbose=verbose,
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
                "targets": _collect_targets(config),
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
  bb-run                                    # Run default pipeline
  bb-run --target branches.main            # Run main branch pipeline
  bb-run --repo /path/to/repo              # Run in specific repo
  bb-run --branch feature-x                # Simulate running on a branch
  bb-run --mode host                       # Run on host (no Docker)
  bb-run --mode docker                     # Run in Docker (default)
  bb-run -v KEY=VALUE                      # Pass variables
  bb-run --list-targets                    # List available targets
  bb-run --validate                        # Validate YAML only
  bb-run --list-targets --json             # List targets as JSON
  bb-run --validate --json                 # Validate as JSON
  python3 -m bbrun --version               # If bb-run is not on PATH
        """,
    )

    parser.add_argument(
        "--repo",
        "-r",
        default=".",
        help="Path to repository (default: current directory)",
    )
    parser.add_argument(
        "--target",
        "-t",
        default="default",
        help="Pipeline target (default: default)",
    )
    parser.add_argument(
        "--branch",
        "-b",
        default="LOCAL",
        help="Branch name to simulate (default: LOCAL)",
    )
    parser.add_argument(
        "--mode",
        "-m",
        choices=["docker", "host"],
        default="docker",
        help="Execution mode (default: docker)",
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
        help="Output JSON for --list-targets or --validate",
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
        "--verbose",
        action="store_true",
        help="Print variables from -v/--variables before the run",
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"%(prog)s {__version__}",
    )

    args = parser.parse_args()

    if args.json and not (args.list_targets or args.validate):
        print("Error: --json is only supported with --list-targets or --validate")
        return 2

    try:
        repo_path = Path(args.repo).expanduser().resolve(strict=False)
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

    pipeline_file = repo_path / "bitbucket-pipelines.yml"
    if not pipeline_file.exists():
        print(f"Error: bitbucket-pipelines.yml not found in {repo_path}")
        print("Tip: run from your repository root, or pass --repo /path/to/repo")
        return 1

    return run_pipeline(
        repo_path=repo_path,
        target=args.target,
        branch=args.branch,
        variables=variables,
        mode=args.mode,
        verbose=args.verbose,
    )


def main() -> int:
    try:
        return _cli_dispatch()
    except KeyboardInterrupt:
        print("\nInterrupted.", file=sys.stderr)
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
