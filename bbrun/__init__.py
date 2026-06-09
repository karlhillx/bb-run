"""
bb-run - Bitbucket Pipelines Local Runner.

Faithfully runs ``bitbucket-pipelines.yml`` locally using Docker or your host
environment, including parallel steps, fail-fast, and artifact modeling.

The package is usable both as a CLI (``bb-run`` / ``python -m bbrun``) and as a
library::

    from bbrun import HostRunner

    runner = HostRunner(".")
    ok = runner.run(target="default")
"""

from importlib.metadata import PackageNotFoundError, version


def _package_version() -> str:
    try:
        return version("bb-run")
    except PackageNotFoundError:
        return "0.0.0+source"


__version__ = _package_version()
__author__ = "Karl Hill"
__license__ = "MIT"

# Imports are placed after ``__version__`` because the CLI reads it from here.
from .cli import main  # noqa: E402
from .docker import DockerRunner  # noqa: E402
from .host import HostRunner  # noqa: E402
from .pipeline import get_steps_for_target  # noqa: E402
from .runner import BaseRunner  # noqa: E402
from .validator import PipelineValidator  # noqa: E402

__all__ = [
    "BaseRunner",
    "DockerRunner",
    "HostRunner",
    "PipelineValidator",
    "get_steps_for_target",
    "main",
    "__version__",
]
