#!/usr/bin/env python3
"""
bb-run CLI - Bitbucket Pipelines Local Runner
"""

import sys
import argparse
from pathlib import Path

from . import __version__
from .docker import DockerRunner
from .host import HostRunner
from .validator import PipelineValidator


def list_targets(repo_path: Path) -> int:
    """List available pipeline targets."""
    pipeline_file = repo_path / "bitbucket-pipelines.yml"
    if not pipeline_file.exists():
        print(f"Error: bitbucket-pipelines.yml not found in {repo_path}")
        return 1

    validator = PipelineValidator(repo_path)
    config = validator.load()

    if not config:
        print("Error: Could not read or parse bitbucket-pipelines.yml")
        return 1

    if "pipelines" not in config:
        print("Error: Missing 'pipelines' key in bitbucket-pipelines.yml")
        return 1

    print("Available pipeline targets:")
    print("\n  default")
    
    pipelines = config.get('pipelines', {})
    
    branches = pipelines.get('branches', {})
    for branch in sorted(branches.keys()):
        print(f"  branches.{branch}")
    
    tags = pipelines.get('tags', {})
    for tag in sorted(tags.keys()):
        print(f"  tags.{tag}")
    
    for name in pipelines:
        if name not in ['default', 'branches', 'tags']:
            print(f"  {name}")
    
    image = config.get('image', 'atlassian/default-image:latest')
    print(f"\nDefault image: {image}")
    
    return 0


def run_pipeline(
    repo_path: Path,
    target: str,
    branch: str,
    variables: dict,
    mode: str,
    verbose: bool
) -> int:
    """Run a pipeline in the specified mode."""
    
    if mode == 'docker':
        runner = DockerRunner(repo_path)
    else:
        runner = HostRunner(repo_path)
    
    success = runner.run(
        target=target,
        branch=branch,
        variables=variables,
        verbose=verbose
    )
    
    return 0 if success else 1


def validate(repo_path: Path) -> int:
    """Validate a pipeline YAML file."""
    validator = PipelineValidator(repo_path)

    if validator.validate():
        print("✅ Valid bitbucket-pipelines.yml")
        validator.show_summary()
        return 0
    return 1


def _cli_dispatch() -> int:
    parser = argparse.ArgumentParser(
        prog='bb-run',
        description='Run Bitbucket Pipelines locally',
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
  python3 -m bbrun --version               # If bb-run is not on PATH
        """
    )
    
    parser.add_argument(
        '--repo', '-r',
        default='.',
        help='Path to repository (default: current directory)'
    )
    parser.add_argument(
        '--target', '-t',
        default='default',
        help='Pipeline target (default: default)'
    )
    parser.add_argument(
        '--branch', '-b',
        default='LOCAL',
        help='Branch name to simulate (default: LOCAL)'
    )
    parser.add_argument(
        '--mode', '-m',
        choices=['docker', 'host'],
        default='docker',
        help='Execution mode (default: docker)'
    )
    parser.add_argument(
        '--variables', '-v',
        action='append',
        help='Variables in KEY=VALUE format'
    )
    parser.add_argument(
        '--list-targets',
        action='store_true',
        help='List available pipeline targets and exit'
    )
    parser.add_argument(
        '--validate',
        action='store_true',
        help='Validate YAML only, do not run'
    )
    parser.add_argument(
        '--verbose',
        action='store_true',
        help='Print variables from -v/--variables before the run',
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"%(prog)s {__version__}",
    )
    
    args = parser.parse_args()

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
                print(
                    f"Warning: ignoring -v {var!r} (use KEY=value)",
                    file=sys.stderr,
                )
                continue
            key, value = var.split("=", 1)
            variables[key] = value

    if args.list_targets:
        return list_targets(repo_path)

    if args.validate:
        return validate(repo_path)

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