"""Package version without importing the rest of ``bbrun``."""

from importlib.metadata import PackageNotFoundError, version


def package_version() -> str:
    try:
        return version("bb-run")
    except PackageNotFoundError:
        return "0.0.0+source"


__version__ = package_version()
