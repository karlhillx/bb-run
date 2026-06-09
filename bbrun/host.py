"""Host runner: executes pipeline steps directly on the local machine."""

from __future__ import annotations

import contextlib
import os
import shutil
import signal
import subprocess
from pathlib import Path

from .runner import BaseRunner


class HostRunner(BaseRunner):
    """Runs pipeline steps directly on the host machine (no Docker)."""

    docker_mode = False

    def __init__(self, repo_path: Path | str) -> None:
        super().__init__(repo_path)

    def _print_mode_lines(self, image: str) -> None:
        print("Mode: HOST (runs on your machine)")
        print(f"Note: Uses '{image}' as reference for command mapping")

    def _translate_command(self, cmd: str) -> str:
        """Adapt common Bitbucket image commands to a host environment."""
        # Translate 'python' to 'python3' if python isn't available.
        if not shutil.which("python") and cmd.startswith("python "):
            cmd = "python3" + cmd[6:]

        # Translate 'pip ' to 'pip3 ' if pip isn't available.
        if not shutil.which("pip") and cmd.startswith("pip ") and not cmd.startswith("pip3 "):
            cmd = "pip3 " + cmd[4:]

        # Add --break-system-packages for PEP 668.
        if "pip3 install" in cmd and "--break-system-packages" not in cmd:
            cmd = cmd.replace("pip3 install", "pip3 install --break-system-packages")
            print("  (added --break-system-packages for PEP 668)")

        return cmd

    def _host_spawn_step(
        self, step: dict, env: dict, label: str
    ) -> subprocess.Popen | None:
        """Start a host shell step; return Popen or None if nothing to run."""
        if "script" in step:
            script = step["script"]
            commands = script if isinstance(script, list) else [script]
            parts = [self._translate_command(c) for c in commands]
            full = " && ".join(parts)
            print(f"{label}$ {full[:200]}{'...' if len(full) > 200 else ''}")
            return subprocess.Popen(
                full,
                shell=True,
                cwd=self.repo_path,
                env=env,
                start_new_session=True,
            )
        if "pipe" in step:
            print(f"{label}⚠️  Pipe: {step.get('pipe', '')}")
            print(f"{label}    (pipes not executed in host mode)")
            return None
        print(f"{label}Warning: Step has no script or pipe")
        return None

    def _spawn_step(
        self, step: dict, env: dict, label: str
    ) -> subprocess.Popen | None:
        return self._host_spawn_step(step, env, label)

    def _terminate_proc(self, proc: subprocess.Popen) -> None:
        """Terminate the step's whole process group, falling back to the child."""
        try:
            os.killpg(proc.pid, signal.SIGTERM)
        except (ProcessLookupError, PermissionError, OSError):
            with contextlib.suppress(ProcessLookupError, OSError):
                proc.terminate()
