#!/usr/bin/env python3
"""
bb-run CLI - Bitbucket Pipelines Local Runner
"""

import os
import sys
import argparse
from pathlib import Path
from typing import Optional

from .validator import PipelineValidator
from .docker import DockerRunner
from .host import HostRunner


def list_targets(repo_path: Path) -> int:
    """List available pipeline targets."""
    validator = PipelineValidator(repo_path)
    config = validator.load()
    
    if not config:
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
    else:
        print("❌ Invalid or missing bitbucket-pipelines.yml")
        return 1


def main():
    parser = argparse.ArgumentParser(
        prog='bb-run',
        description='Run Bitbucket Pipelines locally',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  bb-run                                    # Run default pipeline
  bb-run --target master                   # Run master branch pipeline
  bb-run --repo /path/to/repo              # Run in specific repo
  bb-run --branch feature-x                # Simulate running on a branch
  bb-run --mode host                       # Run on host (no Docker)
  bb-run --mode docker                     # Run in Docker (default)
  bb-run -v KEY=VALUE                      # Pass variables
  bb-run --list-targets                    # List available targets
  bb-run --validate                        # Validate YAML only
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
        help='Verbose output'
    )
    parser.add_argument(
        '--version',
        action='version',
        version='%(prog)s 0.1.0'
    )
    
    args = parser.parse_args()
    
    # Parse variables
    variables = {}
    if args.variables:
        for var in args.variables:
            if '=' in var:
                key, value = var.split('=', 1)
                variables[key] = value
    
    repo_path = Path(args.repo).resolve()
    
    # Validate repo has a pipeline file
    pipeline_file = repo_path / 'bitbucket-pipelines.yml'
    if not pipeline_file.exists() and not args.list_targets:
        print(f"Error: bitbucket-pipelines.yml not found in {repo_path}")
        return 1
    
    # Execute
    if args.list_targets:
        return list_targets(repo_path)
    
    if args.validate:
        return validate(repo_path)
    
    return run_pipeline(
        repo_path=repo_path,
        target=args.target,
        branch=args.branch,
        variables=variables,
        mode=args.mode,
        verbose=args.verbose
    )


if __name__ == '__main__':
    sys.exit(main())