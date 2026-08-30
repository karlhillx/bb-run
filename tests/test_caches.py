"""Tests for local cache restore/save."""

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


def test_docker_mode_returns_mounts(tmp_path: Path) -> None:
    session = CacheSession(
        tmp_path, {"uv": "~/.cache/uv"}, enabled=True, docker_mode=True
    )
    mounts = session.prepare_for_step({"caches": ["uv"]})
    assert mounts[0] == "-v"
    assert mounts[1].endswith(":/root/.cache/uv")
