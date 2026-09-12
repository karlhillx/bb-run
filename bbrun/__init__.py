"""
bb-run - Bitbucket Pipelines Local Runner.

Faithfully runs ``bitbucket-pipelines.yml`` locally using Docker or your host
environment, including parallel steps, fail-fast, artifacts, services, caches,
and after-script.

The package is usable both as a CLI (``bb-run`` / ``python -m bbrun``) and as a
library::

    from bbrun import HostRunner

    runner = HostRunner(".")
    ok = runner.run(target="default")
"""

from .cli import main
from .discover import find_repo_root
from .docker import DockerRunner
from .host import HostRunner
from .pipeline import get_steps_for_target, resolve_auto_target
from .runner import BaseRunner
from .validator import PipelineValidator
from .version import __version__

__author__ = "Karl Hill"
__license__ = "MIT"

__all__ = [
    "BaseRunner",
    "DockerRunner",
    "HostRunner",
    "PipelineValidator",
    "find_repo_root",
    "get_steps_for_target",
    "main",
    "resolve_auto_target",
    "__version__",
]
