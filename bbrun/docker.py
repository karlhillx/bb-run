"""Docker runner: executes pipeline steps inside Docker containers."""

from __future__ import annotations

import functools
import os
import subprocess
import sys
from pathlib import Path

from .runner import BaseRunner

CONTAINER_BUILD_DIR = "/opt/atlassian/pipelines/agent/build"


@functools.lru_cache(maxsize=1)
def _docker_pull_supports_progress_flag() -> bool:
    """True if this Docker CLI accepts ``docker pull --progress``."""
    try:
        r = subprocess.run(
            ["docker", "pull", "--help"],
            capture_output=True,
            text=True,
            timeout=8,
        )
        combined = (r.stdout or "") + (r.stderr or "")
        return r.returncode == 0 and "--progress" in combined
    except (OSError, subprocess.TimeoutExpired):
        return False


class DockerRunner(BaseRunner):
    """Runs pipeline steps in Docker containers."""

    docker_mode = True

    def __init__(self, repo_path: Path | str) -> None:
        super().__init__(repo_path)

    # -- environment / header --------------------------------------------

    def _clone_dir(self) -> str:
        return CONTAINER_BUILD_DIR

    def _extra_env(self) -> dict[str, str]:
        return {"HOME": "/root"}

    def _print_mode_lines(self, image: str) -> None:
        print("Mode: DOCKER")
        print(f"Image: {image}")

    def _preflight(self) -> bool:
        if not self._docker_available():
            print("Error: Docker is not available")
            print("Use --mode host to run on your host machine instead")
            return False
        return True

    # -- docker helpers ---------------------------------------------------

    def _docker_available(self) -> bool:
        """Check if the Docker daemon is reachable."""
        try:
            result = subprocess.run(
                ["docker", "info"],
                capture_output=True,
                timeout=10,
            )
            return result.returncode == 0
        except (subprocess.TimeoutExpired, FileNotFoundError):
            return False

    def _image_exists(self, image: str) -> bool:
        """Check if a Docker image is present locally."""
        result = subprocess.run(
            ["docker", "image", "inspect", image],
            capture_output=True,
        )
        return result.returncode == 0

    def _pull_image(self, image: str) -> bool:
        """Pull a Docker image, streaming Docker's own progress to the terminal."""
        print(f"Pulling Docker image: {image}", flush=True)
        interactive = sys.stderr.isatty()
        if interactive:
            print(
                "Tip: each fs layer can take a while; lines update when a layer completes.",
                flush=True,
            )

        cmd = ["docker", "pull"]
        if _docker_pull_supports_progress_flag():
            # tty: animated bars on a real terminal; plain: steady line-based output.
            cmd.extend(["--progress", "tty" if interactive else "plain"])
        cmd.append(image)

        env = os.environ.copy()
        if interactive:
            # Editors/CI often set CI=1, which makes Docker suppress TTY progress.
            env.pop("CI", None)

        proc = subprocess.Popen(cmd, env=env)
        # Heartbeat: plain progress can look "stuck" for minutes on large layers.
        while proc.poll() is None:
            try:
                proc.wait(timeout=20)
            except subprocess.TimeoutExpired:
                print(
                    "  … still pulling (large images can take several minutes)",
                    flush=True,
                )

        ok = proc.returncode == 0
        if not ok:
            print(f"Failed to pull image: {image}")
        return ok

    # -- step spawning ----------------------------------------------------

    def _docker_spawn_step(
        self, step: dict, default_image: str, env: dict, label: str
    ) -> subprocess.Popen | None:
        """Start a Docker-backed step; return Popen or None if nothing to run."""
        image = step.get("image", default_image)
        if not self._image_exists(image):
            print(f"Image not found locally: {image}")
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
        for key, value in env.items():
            docker_cmd.extend(["-e", f"{key}={value}"])
        docker_cmd.append(image)

        if "script" in step:
            script = step["script"]
            bash_cmd = " && ".join(script) if isinstance(script, list) else script
            docker_cmd.extend(["/bin/bash", "-c", bash_cmd])
            print(f"{label}Executing: {bash_cmd[:60]}...")
            return subprocess.Popen(docker_cmd, cwd=self.repo_path, env=env)
        if "pipe" in step:
            print(f"{label}Pipe: {step['pipe']}")
            print(f"{label}Note: Pipes are not executed in Docker mode (simplified)")
            return None
        print(f"{label}Warning: Step has no script or pipe")
        return None

    def _spawn_step(
        self, step: dict, env: dict, label: str
    ) -> subprocess.Popen | None:
        return self._docker_spawn_step(step, self.default_image, env, label)

    def _run_step(
        self, step: dict, step_name: str, default_image: str, env: dict
    ) -> bool:
        """Execute a single step in Docker (kept for direct/library use)."""
        self.default_image = default_image
        return self._execute_step(step, step_name, env)
