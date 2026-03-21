"""
Bitbucket-style pipeline artifacts: capture paths after steps and restore for later steps.

Uses only the standard library. Artifact cache lives under <repo>/.bb-run/artifacts/.
"""

from __future__ import annotations

import glob
import os
import shutil
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Union

# Sentinel: restore all shared layers from prior steps
_ALL_DOWNLOAD = object()


@dataclass
class UploadSpec:
    """One artifact upload definition."""

    name: Optional[str]
    type: str  # shared | scoped | test-reports
    paths: List[str]
    ignore_paths: List[str]
    capture_on: str  # always | success | failed


def _norm_capture_on(raw: Any) -> str:
    v = (raw or "always")
    if isinstance(v, str):
        v = v.strip().lower().replace("_", "-")
    if v in ("failure", "fail"):
        v = "failed"
    if v not in ("always", "success", "failed"):
        return "always"
    return v


def _parse_upload_dict(entry: Dict[str, Any]) -> UploadSpec:
    name = entry.get("name")
    if name is not None:
        name = str(name)
    typ = str(entry.get("type", "shared")).lower().replace("_", "-")
    if typ == "testreports":
        typ = "test-reports"
    paths = entry.get("paths") or []
    if isinstance(paths, str):
        paths = [paths]
    ignore = entry.get("ignore-paths") or entry.get("ignore_paths") or []
    if isinstance(ignore, str):
        ignore = [ignore]
    return UploadSpec(
        name=name,
        type=typ,
        paths=[str(p) for p in paths],
        ignore_paths=[str(p) for p in ignore],
        capture_on=_norm_capture_on(entry.get("capture-on", entry.get("capture_on"))),
    )


def iter_upload_specs(step: Dict[str, Any]) -> List[UploadSpec]:
    """Collect artifact upload definitions from a step (may be empty)."""
    raw = step.get("artifacts")
    if raw is None:
        return []
    if isinstance(raw, list):
        patterns = [str(p) for p in raw]
        if not patterns:
            return []
        return [
            UploadSpec(
                name=None,
                type="shared",
                paths=patterns,
                ignore_paths=[],
                capture_on="always",
            )
        ]
    if not isinstance(raw, dict):
        return []

    specs: List[UploadSpec] = []

    paths = raw.get("paths")
    if paths is not None:
        if isinstance(paths, str):
            paths = [paths]
        elif not isinstance(paths, list):
            paths = []
        if paths:
            specs.append(
                UploadSpec(
                    name=None,
                    type="shared",
                    paths=[str(p) for p in paths],
                    ignore_paths=_list_str(
                        raw.get("ignore-paths", raw.get("ignore_paths"))
                    ),
                    capture_on=_norm_capture_on(
                        raw.get("capture-on", raw.get("capture_on"))
                    ),
                )
            )

    for entry in raw.get("upload", []) or []:
        if isinstance(entry, dict):
            specs.append(_parse_upload_dict(entry))

    return specs


def _list_str(raw: Any) -> List[str]:
    if raw is None:
        return []
    if isinstance(raw, str):
        return [raw]
    return [str(x) for x in raw]


def parse_download_rule(step: Dict[str, Any]) -> Union[object, bool, List[str]]:
    """
    Return:
      _ALL_DOWNLOAD — restore all prior shared layers (default).
      False — download: false
      list of strings — selective by artifact name (and unnamed layers if list empty? no — names only).
    """
    raw = step.get("artifacts")
    if not isinstance(raw, dict) or "download" not in raw:
        return _ALL_DOWNLOAD
    d = raw["download"]
    if d is False:
        return False
    if d is True or d is None:
        return _ALL_DOWNLOAD
    if isinstance(d, list):
        return [str(x) for x in d]
    return _ALL_DOWNLOAD


def should_capture(capture_on: str, step_ok: bool) -> bool:
    if capture_on == "always":
        return True
    if capture_on == "success":
        return step_ok
    if capture_on == "failed":
        return not step_ok
    return True


def _collect_excluded_paths(repo: Path, ignore_patterns: List[str]) -> Set[Path]:
    repo = repo.resolve()
    out: Set[Path] = set()
    for pat in ignore_patterns:
        if not pat.strip():
            continue
        for abs_path in glob.glob(str(repo / pat), recursive=True):
            p = Path(abs_path).resolve()
            if p.is_dir():
                for f in p.rglob("*"):
                    if f.is_file():
                        out.add(f.resolve())
            elif p.is_file():
                out.add(p)
    return out


def expand_artifact_files(
    repo: Path, patterns: List[str], ignore_patterns: List[str]
) -> List[Path]:
    """Resolve glob patterns relative to repo; return sorted unique files."""
    repo = repo.resolve()
    excluded = _collect_excluded_paths(repo, ignore_patterns)
    found: Set[Path] = set()

    for raw in patterns:
        pat = str(raw).strip()
        if not pat:
            continue
        for abs_path in glob.glob(str(repo / pat), recursive=True):
            p = Path(abs_path)
            if not p.exists():
                continue
            try:
                p.resolve().relative_to(repo)
            except ValueError:
                continue
            rp = p.resolve()
            if rp.is_dir():
                for f in rp.rglob("*"):
                    if f.is_file() and f.resolve() not in excluded:
                        try:
                            f.resolve().relative_to(repo)
                        except ValueError:
                            continue
                        found.add(f.resolve())
                continue
            if rp.is_file():
                if rp in excluded:
                    continue
                found.add(rp)

    return sorted(found)


def copy_files_into_layer(repo: Path, files: List[Path], layer_root: Path) -> int:
    """Copy files preserving paths relative to repo. Returns file count."""
    repo = repo.resolve()
    layer_root.mkdir(parents=True, exist_ok=True)
    n = 0
    for src in files:
        src = src.resolve()
        rel = src.relative_to(repo)
        dest = layer_root / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dest)
        n += 1
    return n


def merge_layer_into_repo(layer_root: Path, repo: Path) -> None:
    """Overlay captured files onto the working tree."""
    repo = repo.resolve()
    layer_root = layer_root.resolve()
    if not layer_root.exists():
        return
    for src in sorted(layer_root.rglob("*")):
        if not src.is_file():
            continue
        rel = src.relative_to(layer_root)
        dest = repo / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dest)


@dataclass
class SharedLayer:
    name: Optional[str]
    root: Path


class ArtifactSession:
    """
    Tracks shared artifact layers produced by prior steps and restores them
    before later steps according to each step's `artifacts.download` rule.
    """

    def __init__(self, repo_path: Path) -> None:
        self.repo = repo_path.resolve()
        self.base = self.repo / ".bb-run" / "artifacts" / f"run_{os.getpid()}_{uuid.uuid4().hex[:8]}"
        self.base.mkdir(parents=True, exist_ok=True)
        self.shared_layers: List[SharedLayer] = []
        self._layer_seq = 0

    def prepare_for_step(self, step: Dict[str, Any]) -> None:
        """Restore prior shared artifacts before the step runs."""
        rule = parse_download_rule(step)
        if rule is False:
            print("📥 Artifacts: skipping restore (artifacts.download: false)")
            return
        if rule is _ALL_DOWNLOAD:
            for layer in self.shared_layers:
                merge_layer_into_repo(layer.root, self.repo)
            if self.shared_layers:
                print(
                    f"📥 Artifacts: restored {len(self.shared_layers)} shared layer(s)"
                )
            return
        if isinstance(rule, list):
            wanted = {x for x in rule}
            if not wanted:
                print(
                    "📥 Artifacts: selective download list empty — nothing restored"
                )
                return
            merged = 0
            for layer in self.shared_layers:
                if layer.name is not None and layer.name in wanted:
                    merge_layer_into_repo(layer.root, self.repo)
                    merged += 1
            if merged == 0:
                for layer in self.shared_layers:
                    if layer.name is None:
                        merge_layer_into_repo(layer.root, self.repo)
                        merged += 1
            if merged:
                print(
                    f"📥 Artifacts: restored {merged} layer(s) (selective download)"
                )
            return

    def capture_after_step(self, step: Dict[str, Any], step_ok: bool) -> None:
        """Capture declared artifacts after a step finishes."""
        for spec in iter_upload_specs(step):
            if not should_capture(spec.capture_on, step_ok):
                continue
            files = expand_artifact_files(
                self.repo, spec.paths, spec.ignore_paths
            )
            if not files:
                label = spec.name or "paths"
                print(f"📦 Artifacts: nothing matched for [{label}]")
                continue

            self._layer_seq += 1
            layer_root = self.base / f"L{self._layer_seq}"
            n = copy_files_into_layer(self.repo, files, layer_root)

            if spec.type == "shared":
                self.shared_layers.append(SharedLayer(name=spec.name, root=layer_root))
                tag = spec.name or "shared"
                print(f"📦 Artifacts: saved [{tag}] ({n} file(s)) for later steps")
            elif spec.type == "scoped":
                scoped_dir = self.base / "scoped" / (spec.name or f"layer_{self._layer_seq}")
                shutil.copytree(layer_root, scoped_dir, dirs_exist_ok=True)
                print(
                    f"📦 Artifacts: saved scoped [{spec.name or 'unnamed'}] ({n} file(s), not passed on)"
                )
            elif spec.type == "test-reports":
                tr_dir = self.base / "test-reports" / (spec.name or f"layer_{self._layer_seq}")
                shutil.copytree(layer_root, tr_dir, dirs_exist_ok=True)
                print(
                    f"📦 Artifacts: saved test-reports [{spec.name or 'unnamed'}] ({n} file(s))"
                )
