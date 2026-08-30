"""Locate a pipeline file and gather lightweight git context."""

from __future__ import annotations

import subprocess
from pathlib import Path

PIPELINE_FILENAME = "bitbucket-pipelines.yml"


def find_repo_root(start: Path) -> Path | None:
    """Walk *start* and its parents for ``bitbucket-pipelines.yml``."""
    current = Path(start).resolve()
    for candidate in (current, *current.parents):
        if (candidate / PIPELINE_FILENAME).is_file():
            return candidate
    return None


def resolve_repo_path(repo_arg: str) -> Path:
    """
    Resolve ``--repo``.

    When the argument is the default ``.`` and the current directory has no
    pipeline file, walk parents. An explicit path is used as-is.
    """
    path = Path(repo_arg).expanduser().resolve(strict=False)
    if repo_arg in (".", "") and not (path / PIPELINE_FILENAME).is_file():
        found = find_repo_root(path)
        if found is not None:
            return found
    return path


def git_branch(repo: Path) -> str | None:
    """Current git branch name, or ``None`` if detached / unavailable."""
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            capture_output=True,
            text=True,
            cwd=repo,
            timeout=5,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    branch = result.stdout.strip()
    if result.returncode != 0 or not branch or branch == "HEAD":
        return None
    return branch


def git_remote_url(repo: Path, remote: str = "origin") -> str:
    """``git remote get-url`` or empty string."""
    try:
        result = subprocess.run(
            ["git", "remote", "get-url", remote],
            capture_output=True,
            text=True,
            cwd=repo,
            timeout=5,
        )
    except (OSError, subprocess.TimeoutExpired):
        return ""
    if result.returncode != 0:
        return ""
    return result.stdout.strip()


def _ssh_to_https(url: str) -> str:
    if url.startswith("git@") and ":" in url:
        host, path = url[4:].split(":", 1)
        return f"https://{host}/{path}"
    if url.startswith("ssh://git@"):
        rest = url[len("ssh://git@") :]
        if "/" in rest:
            host, path = rest.split("/", 1)
            return f"https://{host}/{path}"
    return ""


def _https_to_ssh(url: str) -> str:
    for prefix in ("https://", "http://"):
        if url.startswith(prefix):
            rest = url[len(prefix) :]
            if "/" in rest:
                host, path = rest.split("/", 1)
                return f"git@{host}:{path}"
    return ""


def git_origin_urls(repo: Path) -> tuple[str, str]:
    """Return ``(http_origin, ssh_origin)`` derived from ``origin``."""
    url = git_remote_url(repo)
    if not url:
        return "", ""
    if url.startswith(("git@", "ssh://")):
        return _ssh_to_https(url), url
    if url.startswith(("http://", "https://")):
        return url, _https_to_ssh(url)
    return url, ""
