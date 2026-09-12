"""Tests for local cache restore/save."""

import shutil
import sqlite3
from pathlib import Path

from bbrun.caches import (
    PREDEFINED_CACHES,
    CacheSession,
    resolve_cache_path,
    step_cache_names,
)


def test_resolve_predefined_and_custom() -> None:
    assert resolve_cache_path("pip", {}, home="/root") == "/root/.cache/pip"
    assert "node" in PREDEFINED_CACHES
    custom = resolve_cache_path("uv", {"uv": "~/.cache/uv"}, home="/root")
    assert custom == "/root/.cache/uv"


def test_unknown_cache_is_none() -> None:
    assert resolve_cache_path("not-a-cache", {}, home="/tmp") is None


def test_step_cache_names() -> None:
    assert step_cache_names({"caches": ["uv", "pre-commit"]}) == ["uv", "pre-commit"]
    assert step_cache_names({"caches": "pip"}) == ["pip"]
    assert step_cache_names({}) == []


def test_host_cache_restore_and_save(tmp_path: Path) -> None:
    dest = tmp_path / "hot"
    dest.mkdir()
    session = CacheSession(tmp_path, {"uv": str(dest)}, enabled=True, docker_mode=False)
    layer = session.store / "uv"
    layer.mkdir(parents=True)
    (layer / "pkg.txt").write_text("cached", encoding="utf-8")

    mounts = session.prepare_for_step({"caches": ["uv"]})
    assert mounts == []
    assert (dest / "pkg.txt").read_text(encoding="utf-8") == "cached"

    (dest / "new.txt").write_text("fresh", encoding="utf-8")
    session.capture_after_step({"caches": ["uv"]})
    assert (layer / "new.txt").read_text(encoding="utf-8") == "fresh"


def test_empty_layer_does_not_clobber_dest(tmp_path: Path) -> None:
    dest = tmp_path / "hot"
    dest.mkdir()
    (dest / "keep.txt").write_text("safe", encoding="utf-8")
    session = CacheSession(tmp_path, {"uv": str(dest)}, enabled=True, docker_mode=False)
    session.prepare_for_step({"caches": ["uv"]})
    assert (dest / "keep.txt").read_text(encoding="utf-8") == "safe"


def test_disabled_cache_is_noop(tmp_path: Path) -> None:
    session = CacheSession(tmp_path, {"uv": str(tmp_path / "x")}, enabled=False)
    assert session.prepare_for_step({"caches": ["uv"]}) == []
    assert not (tmp_path / ".bb-run").exists()


def test_docker_mode_returns_mounts(tmp_path: Path) -> None:
    session = CacheSession(
        tmp_path, {"uv": "~/.cache/uv"}, enabled=True, docker_mode=True
    )
    mounts = session.prepare_for_step({"caches": ["uv"]})
    assert mounts[0] == "-v"
    assert mounts[1].endswith(":/root/.cache/uv")
    assert "/.bb-run/caches/docker/uv:" in mounts[1].replace("\\", "/")


def test_docker_cache_store_is_isolated_from_host(tmp_path: Path) -> None:
    host = CacheSession(tmp_path, {}, docker_mode=False)
    docker = CacheSession(tmp_path, {}, docker_mode=True)
    assert docker.store == host.store / "docker"


def _write_precommit_db(layer: Path, clone_path: str) -> None:
    layer.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(layer / "db.db")
    con.execute("CREATE TABLE repos (repo TEXT, ref TEXT, path TEXT)")
    con.execute(
        "INSERT INTO repos VALUES (?, ?, ?)",
        ("https://github.com/pre-commit/pre-commit-hooks", "v6.0.0", clone_path),
    )
    con.commit()
    con.close()


def test_docker_resets_precommit_cache_with_host_paths(tmp_path: Path) -> None:
    session = CacheSession(
        tmp_path,
        {"pre-commit": "~/.cache/pre-commit"},
        enabled=True,
        docker_mode=True,
    )
    layer = session.store / "pre-commit"
    _write_precommit_db(layer, "/Users/karlhill/.cache/pre-commit/repo4btey1rg")
    poison = layer / "repo4btey1rg"
    poison.mkdir()
    (poison / "stale.txt").write_text("host", encoding="utf-8")

    mounts = session.prepare_for_step({"caches": ["pre-commit"]})
    assert mounts[1].endswith(":/root/.cache/pre-commit")
    assert not (layer / "db.db").exists()
    assert not poison.exists()


def test_docker_keeps_precommit_cache_with_container_paths(tmp_path: Path) -> None:
    session = CacheSession(
        tmp_path,
        {"pre-commit": "~/.cache/pre-commit"},
        enabled=True,
        docker_mode=True,
    )
    layer = session.store / "pre-commit"
    _write_precommit_db(layer, "/root/.cache/pre-commit/repo4btey1rg")

    session.prepare_for_step({"caches": ["pre-commit"]})
    assert (layer / "db.db").is_file()


def test_restore_overwrites_readonly_cache_file(tmp_path: Path) -> None:
    dest = tmp_path / "hot"
    dest.mkdir()
    frozen = dest / "pack.idx"
    frozen.write_text("old", encoding="utf-8")
    frozen.chmod(0o444)

    session = CacheSession(tmp_path, {"uv": str(dest)}, enabled=True, docker_mode=False)
    layer = session.store / "uv"
    layer.mkdir(parents=True)
    (layer / "pack.idx").write_text("new", encoding="utf-8")

    session.prepare_for_step({"caches": ["uv"]})
    assert frozen.read_text(encoding="utf-8") == "new"


def test_restore_does_not_crash_on_readonly_identical_file(tmp_path: Path) -> None:
    dest = tmp_path / "hot"
    dest.mkdir()
    frozen = dest / "pack.idx"
    frozen.write_text("same", encoding="utf-8")

    session = CacheSession(tmp_path, {"uv": str(dest)}, enabled=True, docker_mode=False)
    layer = session.store / "uv"
    layer.mkdir(parents=True)
    cached = layer / "pack.idx"
    shutil.copy2(frozen, cached)
    frozen.chmod(0o444)
    cached.chmod(0o444)

    session.prepare_for_step({"caches": ["uv"]})
    assert frozen.read_text(encoding="utf-8") == "same"


def test_host_does_not_overlay_home_cache(tmp_path: Path, monkeypatch) -> None:
    fake_home = tmp_path / "home"
    dest = fake_home / ".cache" / "uv"
    dest.mkdir(parents=True)
    (dest / "keep.txt").write_text("live", encoding="utf-8")
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: fake_home))

    session = CacheSession(
        tmp_path, {"uv": "~/.cache/uv"}, enabled=True, docker_mode=False
    )
    layer = session.store / "uv"
    layer.mkdir(parents=True)
    (layer / "keep.txt").write_text("stale", encoding="utf-8")

    session.prepare_for_step({"caches": ["uv"]})
    assert (dest / "keep.txt").read_text(encoding="utf-8") == "live"

    session.capture_after_step({"caches": ["uv"]})
    assert (layer / "keep.txt").read_text(encoding="utf-8") == "stale"
