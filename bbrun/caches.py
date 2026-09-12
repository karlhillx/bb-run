"""Bitbucket-style dependency caches persisted under ``.bb-run/caches/``."""

from __future__ import annotations

import contextlib
import os
import shutil
import sqlite3
import stat
from pathlib import Path
from typing import Any

from .ui import get_ui

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


def _is_under_home(path: Path, home: Path) -> bool:
    """True if *path* is the home directory or a subdirectory of it."""
    try:
        resolved = path.expanduser().resolve()
        home_res = home.expanduser().resolve()
    except OSError:
        return False
    return resolved == home_res or home_res in resolved.parents


def _dir_has_files(path: Path) -> bool:
    try:
        if not path.exists():
            return False
        if path.is_file():
            return True
        next(path.iterdir())
        return True
    except (OSError, StopIteration):
        return False


def _replace_file(src: Path, dest: Path) -> None:
    """Copy *src* onto *dest*, replacing read-only files (uv git packs, etc.)."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists():
        with contextlib.suppress(OSError):
            if dest.samefile(src):
                return
        with contextlib.suppress(OSError):
            dest.chmod(dest.stat().st_mode | stat.S_IWRITE)
        dest.unlink()
    shutil.copy2(src, dest)


def _path_is_under(path: str, dest: str) -> bool:
    """True if *path* is *dest* or a subdirectory of it."""
    prefix = dest.rstrip("/")
    return path == prefix or path.startswith(prefix + "/")


def _precommit_db_has_foreign_paths(layer: Path, dest: str) -> bool:
    """True if a pre-commit ``db.db`` records clones outside *dest*."""
    db = layer / "db.db"
    if not db.is_file():
        return False
    try:
        con = sqlite3.connect(db)
        try:
            tables = {
                row[0]
                for row in con.execute("SELECT name FROM sqlite_master WHERE type='table'")
            }
            if "repos" not in tables:
                return False
            for (path,) in con.execute("SELECT path FROM repos"):
                if isinstance(path, str) and path and not _path_is_under(path, dest):
                    return True
        finally:
            con.close()
    except sqlite3.Error:
        return True
    return False


def _reset_layer(layer: Path) -> None:
    """Delete *layer* even when it contains read-only git objects."""

    def _make_writable(func: Any, path: str, _exc: BaseException) -> None:
        with contextlib.suppress(OSError):
            os.chmod(path, stat.S_IWRITE)
        func(path)

    if layer.exists():
        shutil.rmtree(layer, onexc=_make_writable)
    layer.mkdir(parents=True, exist_ok=True)


def _copy_tree(src: Path, dest: Path) -> tuple[int, int]:
    """
    Overlay *src* onto *dest* without deleting extra dest files.

    Returns ``(copied, skipped)``. Permission errors are skipped so a live
    ``~/.cache/uv`` cannot abort the pipeline.
    """
    copied = 0
    skipped = 0
    try:
        if not src.exists():
            return copied, skipped
        dest.mkdir(parents=True, exist_ok=True)
        for item in src.rglob("*"):
            try:
                if not item.is_file():
                    continue
                target = dest / item.relative_to(src)
                _replace_file(item, target)
                copied += 1
            except OSError:
                skipped += 1
    except OSError:
        skipped += 1
    return copied, skipped


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
        caches = self.repo / ".bb-run" / "caches"
        # Host snapshots store absolute machine paths (pre-commit db.db).
        # Docker bind-mounts a separate tree so those paths never leak in.
        self.store = caches / "docker" if docker_mode else caches
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

        ui = get_ui()
        try:
            return self._prepare_for_step(step)
        except Exception as exc:
            ui.warn(f"Cache: skipped restore ({exc})")
            self._active = []
            return []

    def _prepare_for_step(self, step: dict[str, Any]) -> list[str]:
        self.store.mkdir(parents=True, exist_ok=True)
        ui = get_ui()
        home = Path("/root") if self.docker_mode else Path.home()
        mounts: list[str] = []
        for name in step_cache_names(step):
            dest = resolve_cache_path(name, self.definitions, home=str(home))
            if dest is None:
                ui.warn(f"unknown cache {name!r}")
                continue
            layer = self.store / name
            layer.mkdir(parents=True, exist_ok=True)
            if self.docker_mode:
                if _precommit_db_has_foreign_paths(layer, dest):
                    _reset_layer(layer)
                    ui.warn(
                        f"Cache: reset [{name}] "
                        "(host paths are not valid inside Docker)"
                    )
                mounts.extend(["-v", f"{layer}:{dest}"])
                ui.info(f"Cache: mount [{name}] -> {dest}")
                continue

            dest_path = Path(dest)
            if not dest_path.is_absolute():
                dest_path = self.repo / dest_path
            if _is_under_home(dest_path, home):
                ui.info(f"Cache: [{name}] already on the host at {dest_path}")
                continue
            if _dir_has_files(layer):
                copied, skipped = _copy_tree(layer, dest_path)
                ui.info(f"Cache: restored [{name}] -> {dest_path}")
                if skipped:
                    ui.warn(
                        f"Cache: skipped {skipped} file(s) under {dest_path} "
                        f"({copied} written)"
                    )
            self._active.append((name, layer, dest_path))
        return mounts

    def capture_after_step(self, step: dict[str, Any]) -> None:
        """Snapshot host cache dirs back into ``.bb-run/caches/``."""
        del step  # Docker bind-mounts stay live; host uses _active.
        if self.docker_mode or not self.enabled:
            self._active = []
            return
        ui = get_ui()
        try:
            for name, layer, dest in self._active:
                if dest.exists():
                    copied, skipped = _copy_tree(dest, layer)
                    ui.info(f"Cache: saved [{name}]")
                    if skipped:
                        ui.warn(
                            f"Cache: skipped {skipped} file(s) while saving [{name}] "
                            f"({copied} written)"
                        )
        except Exception as exc:
            ui.warn(f"Cache: skipped save ({exc})")
        self._active = []
