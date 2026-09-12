"""Docker runner: executes pipeline steps inside Docker containers."""

from __future__ import annotations

import functools
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from .runner import BaseRunner
from .ui import get_ui

CONTAINER_BUILD_DIR = "/opt/atlassian/pipelines/agent/build"

_HELPER_DIRS = (
    Path("/Applications/Docker.app/Contents/Resources/bin"),
    Path("/Applications/OrbStack.app/Contents/MacOS"),
    Path.home() / ".orbstack" / "bin",
    Path("/opt/homebrew/bin"),
    Path("/usr/local/bin"),
)


def apply_docker_git_filemode(env: dict[str, str], *, platform: str = sys.platform) -> None:
    """
    Make git (and pre-commit) trust the index executable bit.

    Docker Desktop bind-mounts keep ``stat`` modes (644) but ``os.access(X_OK)``
    as root returns True for every file. ``check-executables-have-shebangs``
    then fails on ordinary sources. Linux hosts are left alone.
    """
    if platform == "linux":
        return
    count = 0
    raw = env.get("GIT_CONFIG_COUNT", "")
    if raw.isdigit():
        count = int(raw)
    for index in range(count):
        key = env.get(f"GIT_CONFIG_KEY_{index}", "").lower()
        if key == "core.filemode":
            env[f"GIT_CONFIG_VALUE_{index}"] = "false"
            return
    env[f"GIT_CONFIG_KEY_{count}"] = "core.filemode"
    env[f"GIT_CONFIG_VALUE_{count}"] = "false"
    env["GIT_CONFIG_COUNT"] = str(count + 1)


def docker_cli_env(*, anonymous_config: Path | None = None) -> dict[str, str]:
    """Host env for the Docker CLI (not the container)."""
    env = os.environ.copy()
    extras = [str(path) for path in _HELPER_DIRS if path.is_dir()]
    if extras:
        env["PATH"] = os.pathsep.join([*extras, env.get("PATH", "")])
    if anonymous_config is not None:
        env["DOCKER_CONFIG"] = str(anonymous_config)
    return env


def docker_config_dir() -> Path:
    raw = os.environ.get("DOCKER_CONFIG")
    if raw:
        return Path(raw)
    return Path.home() / ".docker"


def configured_credential_helpers() -> list[str]:
    """``docker-credential-*`` names from ``config.json`` (credsStore / credHelpers)."""
    config_file = docker_config_dir() / "config.json"
    try:
        data = json.loads(config_file.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    if not isinstance(data, dict):
        return []
    names: list[str] = []
    store = data.get("credsStore")
    if isinstance(store, str) and store.strip():
        names.append(f"docker-credential-{store.strip()}")
    helpers = data.get("credHelpers")
    if isinstance(helpers, dict):
        for value in helpers.values():
            if isinstance(value, str) and value.strip():
                names.append(f"docker-credential-{value.strip()}")
    return list(dict.fromkeys(names))


def missing_docker_credential_helper() -> str | None:
    """Return a configured helper that is not on PATH, if any."""
    path = docker_cli_env().get("PATH", "")
    for name in configured_credential_helpers():
        if shutil.which(name, path=path) is None:
            return name
    return None


_DAEMON_DOWN_MARKERS = (
    "cannot connect to the docker daemon",
    "is the docker daemon running",
    "failed to connect to the docker api",
    "error during connect",
)


def docker_daemon_status() -> tuple[bool, str]:
    """Return ``(reachable, human detail)`` for the current Docker context."""
    env = docker_cli_env()
    if shutil.which("docker", path=env.get("PATH", "")) is None:
        return False, "docker CLI not found"
    try:
        result = subprocess.run(
            ["docker", "info"],
            capture_output=True,
            timeout=10,
            text=True,
            env=env,
        )
    except subprocess.TimeoutExpired:
        return False, "docker info timed out"
    except (FileNotFoundError, OSError):
        return False, "docker CLI not found"
    if result.returncode == 0:
        return True, "Docker daemon is available"
    text = f"{result.stderr or ''}\n{result.stdout or ''}".lower()
    if any(marker in text for marker in _DAEMON_DOWN_MARKERS):
        return False, "Docker daemon is not running"
    return False, "Docker daemon is not running"


def docker_daemon_available() -> bool:
    """True if the Docker CLI can reach a daemon."""
    return docker_daemon_status()[0]


@functools.lru_cache(maxsize=1)
def _docker_pull_supports_progress_flag() -> bool:
    """True if this Docker CLI accepts ``docker pull --progress``."""
    try:
        r = subprocess.run(
            ["docker", "pull", "--help"],
            capture_output=True,
            text=True,
            timeout=8,
            env=docker_cli_env(),
        )
        combined = (r.stdout or "") + (r.stderr or "")
        return r.returncode == 0 and "--progress" in combined
    except (OSError, subprocess.TimeoutExpired):
        return False


def _run_docker_pull(image: str, env: dict[str, str]) -> int:
    """Stream ``docker pull`` and return its exit code."""
    interactive = sys.stderr.isatty()
    cmd = ["docker", "pull"]
    if _docker_pull_supports_progress_flag():
        cmd.extend(["--progress", "tty" if interactive else "plain"])
    cmd.append(image)
    pull_env = dict(env)
    if interactive:
        pull_env.pop("CI", None)
    proc = subprocess.Popen(cmd, env=pull_env)
    while proc.poll() is None:
        try:
            proc.wait(timeout=20)
        except subprocess.TimeoutExpired:
            get_ui().note(
                "still pulling (large images can take several minutes)",
                persist=True,
            )
    return proc.returncode or 0


def pull_docker_image(image: str) -> bool:
    """Pull *image*, retrying without a broken credential helper if needed."""
    ui = get_ui()
    ui.info(f"Pulling Docker image: {image}", persist=True)
    if sys.stderr.isatty():
        ui.note(
            "Each layer can take a while; lines update when a layer completes.",
            persist=True,
        )

    rc = _run_docker_pull(image, docker_cli_env())
    if rc == 0:
        return True

    helper = missing_docker_credential_helper()
    if helper:
        ui.warn(
            f"{helper} is not on PATH. ~/.docker/config.json likely still "
            "points at Docker Desktop (common with OrbStack)."
        )
        ui.note("Retrying the pull without stored registry credentials…", persist=True)
        with tempfile.TemporaryDirectory(prefix="bb-run-docker-") as tmp:
            Path(tmp, "config.json").write_text("{}\n", encoding="utf-8")
            rc = _run_docker_pull(image, docker_cli_env(anonymous_config=Path(tmp)))
        if rc == 0:
            ui.note(
                "Pulled with an anonymous Docker config. Public images are fine. "
                'To silence this, remove "credsStore" from ~/.docker/config.json.',
                persist=True,
            )
            return True

    ui.error(f"Failed to pull image: {image}")
    ui.note("Use --mode host to run scripts on your machine instead.", persist=True)
    return False


class DockerRunner(BaseRunner):
    """Runs pipeline steps in Docker containers."""

    docker_mode = True

    def __init__(self, repo_path: Path | str) -> None:
        super().__init__(repo_path)

    # -- environment / header --------------------------------------------

    def _clone_dir(self) -> str:
        return CONTAINER_BUILD_DIR

    def _base_env(self) -> dict[str, str]:
        """Do not leak host PATH, GIT_ASKPASS, or Cursor helpers into the image."""
        return {}

    def _extra_env(self) -> dict[str, str]:
        return {"HOME": "/root"}

    def _mode_summary(self, image: str) -> tuple[str, str]:
        return "docker", ""

    def _preflight(self) -> bool:
        ok, detail = docker_daemon_status()
        if ok:
            return True
        ui = get_ui()
        ui.error("Docker is not available")
        ui.note(detail, persist=True)
        ui.note(
            "Start Docker Desktop or OrbStack, then retry --mode docker. "
            "Use --mode host to run on this machine instead.",
            persist=True,
        )
        return False

    # -- docker helpers ---------------------------------------------------

    def _image_exists(self, image: str) -> bool:
        """Check if a Docker image is present locally."""
        result = subprocess.run(
            ["docker", "image", "inspect", image],
            capture_output=True,
            env=docker_cli_env(),
        )
        return result.returncode == 0

    def _pull_image(self, image: str) -> bool:
        return pull_docker_image(image)

    # -- step spawning ----------------------------------------------------

    def _docker_spawn_step(
        self,
        step: dict,
        default_image: str,
        env: dict,
        label: str,
        script_key: str = "script",
    ) -> subprocess.Popen | None:
        """Start a Docker-backed step; return Popen or None if nothing to run."""
        ui = get_ui()
        image = step.get("image", default_image)
        if not self._image_exists(image):
            ui.info(f"Image not found locally: {image}", persist=True)
            if not self._pull_image(image):
                raise RuntimeError(f"docker pull failed: {image}")

        docker_cmd = [
            "docker",
            "run",
            "--rm",
            "-w",
            CONTAINER_BUILD_DIR,
            "-v",
            f"{self.repo_path}:{CONTAINER_BUILD_DIR}:rw",
        ]
        docker_cmd.extend(self._docker_extra_args)
        container_env = dict(env)
        apply_docker_git_filemode(container_env)
        for key, value in container_env.items():
            docker_cmd.extend(["-e", f"{key}={value}"])
        docker_cmd.append(image)

        script = step.get(script_key)
        if script:
            bash_cmd = " && ".join(script) if isinstance(script, list) else script
            docker_cmd.extend(["/bin/bash", "-c", bash_cmd])
            ui.info(f"{label}$ {bash_cmd[:60]}...")
            if self.verbose:
                ui.note(f"{label}docker: {' '.join(docker_cmd)}")
            return subprocess.Popen(
                docker_cmd, cwd=self.repo_path, env=docker_cli_env()
            )
        if script_key == "script" and "pipe" in step:
            ui.warn(f"{label}Pipe: {step['pipe']} (not executed in Docker mode)")
            return None
        ui.warn(f"{label}Step has no {script_key} or pipe")
        return None

    def _spawn_step(
        self,
        step: dict,
        env: dict,
        label: str,
        script_key: str = "script",
    ) -> subprocess.Popen | None:
        return self._docker_spawn_step(
            step, self.default_image, env, label, script_key=script_key
        )

    def _run_step(
        self, step: dict, step_name: str, default_image: str, env: dict
    ) -> bool:
        """Execute a single step in Docker (kept for direct/library use)."""
        self.default_image = default_image
        return self._execute_step(step, step_name, env)
