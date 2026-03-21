"""
bb-run - Bitbucket Pipelines Local Runner

Faithfully runs bitbucket-pipelines.yml locally using Docker or your host environment.
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

from .cli import main  # noqa: E402 - import after __version__ (cli reads it from this package)

__all__ = ["main", "__version__"]
