"""Bitbucket-style dependency caches persisted under ``.bb-run/caches/``."""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any

# Bitbucket predefined cache names plus common extras used in uv repos.
PREDEFINED_CACHES: dict[str, str] = {
    "pip": "~/.cache/pip",
    "pip3": "~/.cache/pip",
    "poetry": "~/.cache/pypoetry",
    "node": "node_modules",
    "yarn": "~/.cache/yarn",
    "pnpm": "~/.local/share/pnpm/store",
    "composer": "~/.composer/cache",
    "gradle": "~/.gradle/caches",
    "maven": "~/.m2/repository",
    "sbt": "~/.sbt",
    "ivy2": "~/.ivy2/cache",
    "nuget": "~/.nuget/packages",
    "dotnetcore": "~/.nuget/packages",
    "cargo": "~/.cargo/registry",
    "go": "~/go/pkg/mod",
    "ccache": "~/.ccache",
}


def _expand_cache_path(raw: str, home: str) -> str:
    if raw == "~":
        return home
    if raw.startswith("~/"):
        return str(Path(home) / raw[2:])
    return raw


def cache_definitions(config: dict[str, Any] | None) -> dict[str, str]:
    """Return ``name → path`` from ``definitions.caches``."""
    raw = ((config or {}).get("definitions") or {}).get("caches") or {}
    if not isinstance(raw, dict):
        return {}
    out: dict[str, str] = {}
    for name, value in raw.items():
        if isinstance(value, str) and value.strip():
            out[str(name)] = value
    return out


def resolve_cache_path(
    name: str,
    definitions: dict[str, str],
    *,
    home: str,
) -> str | None:
    """Absolute or repo-relative destination for a cache name."""
    if name in definitions:
        return _expand_cache_path(definitions[name], home)
    if name in PREDEFINED_CACHES:
        return _expand_cache_path(PREDEFINED_CACHES[name], home)
    return None


def step_cache_names(step: dict[str, Any]) -> list[str]:
    raw = step.get("caches") or []
    if isinstance(raw, str):
        return [raw]
    if not isinstance(raw, list):
        return []
    return [str(item) for item in raw]


def _dir_has_files(path: Path) -> bool:
    if not path.exists():
        return False
    return any(path.rglob("*"))


def _copy_tree(src: Path, dest: Path) -> None:
    """Overlay *src* onto *dest* without deleting extra dest files."""
    if not src.exists():
        return
    dest.mkdir(parents=True, exist_ok=True)
    for item in src.rglob("*"):
        if not item.is_file():
            continue
        rel = item.relative_to(src)
        target = dest / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(item, target)


class CacheSession:
    """Restore and save step caches. Docker mode bind-mounts the store."""

    def __init__(
        self,
        repo: Path,
        definitions: dict[str, str],
        *,
        enabled: bool = True,
        docker_mode: bool = False,
    ) -> None:
        self.repo = Path(repo).resolve()
        self.definitions = definitions
        self.enabled = enabled
        self.docker_mode = docker_mode
        self.store = self.repo / ".bb-run" / "caches"
        self.store.mkdir(parents=True, exist_ok=True)
        self._active: list[tuple[str, Path, Path]] = []

    def prepare_for_step(self, step: dict[str, Any]) -> list[str]:
        """
        Restore caches for *step*.

        Returns extra ``docker run`` arguments (``-v host:container``) in
        Docker mode; an empty list in host mode.
        """
        self._active = []
        if not self.enabled:
            return []

        home = "/root" if self.docker_mode else str(Path.home())
        mounts: list[str] = []
        for name in step_cache_names(step):
            dest = resolve_cache_path(name, self.definitions, home=home)
            if dest is None:
                print(f"Warning: unknown cache {name!r}")
                continue
            layer = self.store / name
            layer.mkdir(parents=True, exist_ok=True)
            if self.docker_mode:
                mounts.extend(["-v", f"{layer}:{dest}"])
                print(f"📦 Cache: mount [{name}] → {dest}")
                continue

            dest_path = Path(dest)
            if not dest_path.is_absolute():
                dest_path = self.repo / dest_path
            if _dir_has_files(layer):
                _copy_tree(layer, dest_path)
                print(f"📦 Cache: restored [{name}] → {dest_path}")
            self._active.append((name, layer, dest_path))
        return mounts

    def capture_after_step(self, step: dict[str, Any]) -> None:
        """Snapshot host cache dirs back into ``.bb-run/caches/``."""
        del step  # Docker bind-mounts stay live; host uses _active.
        if self.docker_mode or not self.enabled:
            return
        for name, layer, dest in self._active:
            if dest.exists():
                _copy_tree(dest, layer)
                print(f"📦 Cache: saved [{name}]")
        self._active = []
