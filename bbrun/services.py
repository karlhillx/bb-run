"""Start and tear down Bitbucket ``definitions.services`` sidecars."""

from __future__ import annotations

import json
import socket
import subprocess
import time
from dataclasses import dataclass, field
from typing import Any


@dataclass
class ServiceSpec:
    name: str
    image: str
    variables: dict[str, str] = field(default_factory=dict)


def resolve_service_specs(config: dict[str, Any], step: dict[str, Any]) -> list[ServiceSpec]:
    """Resolve step ``services:`` names against ``definitions.services``."""
    raw_names = step.get("services") or []
    if isinstance(raw_names, str):
        raw_names = [raw_names]
    if not isinstance(raw_names, list):
        return []

    defs = ((config or {}).get("definitions") or {}).get("services") or {}
    if not isinstance(defs, dict):
        defs = {}

    specs: list[ServiceSpec] = []
    for raw_name in raw_names:
        name = str(raw_name)
        if name == "docker":
            print("Note: built-in 'docker' service is not started locally")
            continue
        entry = defs.get(name)
        if not isinstance(entry, dict):
            print(f"Warning: unknown service {name!r} (not in definitions.services)")
            continue
        image = entry.get("image")
        if not image:
            print(f"Warning: service {name!r} has no image")
            continue
        variables = entry.get("variables") or {}
        if not isinstance(variables, dict):
            variables = {}
        specs.append(
            ServiceSpec(
                name=name,
                image=str(image),
                variables={str(k): str(v) for k, v in variables.items()},
            )
        )
    return specs


def image_exposed_ports(image: str) -> list[int]:
    """Port numbers from ``Config.ExposedPorts``, or empty if unknown."""
    try:
        result = subprocess.run(
            [
                "docker",
                "image",
                "inspect",
                image,
                "--format",
                "{{json .Config.ExposedPorts}}",
            ],
            capture_output=True,
            text=True,
            timeout=15,
        )
    except (OSError, subprocess.TimeoutExpired):
        return []
    if result.returncode != 0:
        return []
    try:
        data = json.loads(result.stdout.strip() or "null")
    except json.JSONDecodeError:
        return []
    if not isinstance(data, dict):
        return []
    ports: list[int] = []
    for key in data:
        num = str(key).split("/", 1)[0]
        if num.isdigit():
            ports.append(int(num))
    return ports


def wait_tcp(host: str, port: int, timeout: float = 30.0) -> bool:
    """Return True if *host:port* accepts a TCP connection before *timeout*."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            with socket.create_connection((host, port), timeout=1.0):
                return True
        except OSError:
            time.sleep(0.25)
    return False


def _ensure_image(image: str) -> bool:
    inspect = subprocess.run(
        ["docker", "image", "inspect", image],
        capture_output=True,
        timeout=15,
    )
    if inspect.returncode == 0:
        return True
    print(f"Pulling service image: {image}", flush=True)
    pull = subprocess.run(["docker", "pull", image], timeout=600)
    return pull.returncode == 0


class ServiceSession:
    """Lifecycle for sidecar containers used by one step (or a sequential group)."""

    def __init__(
        self,
        *,
        enabled: bool = True,
        docker_mode: bool = False,
        run_id: str,
    ) -> None:
        self.enabled = enabled
        self.docker_mode = docker_mode
        self.run_id = run_id
        self.network = f"bb-run-{run_id}"
        self._containers: list[str] = []
        self._network_created = False

    def start(self, specs: list[ServiceSpec]) -> bool:
        """Start sidecars. Returns False if the step cannot run."""
        if not specs:
            return True
        if not self.enabled:
            print("🔌 Services: skipped (--no-services)")
            return True
        from .docker import docker_daemon_available

        if not docker_daemon_available():
            names = ", ".join(s.name for s in specs)
            print(f"Error: step requires services ({names}) but Docker is not available")
            print("Install Docker or pass --no-services")
            return False

        if self.docker_mode and not self._ensure_network():
            return False

        for spec in specs:
            if not self._start_one(spec):
                self.stop()
                return False
        return True

    def stop(self) -> None:
        """Remove started containers and the optional user network."""
        for name in reversed(self._containers):
            subprocess.run(
                ["docker", "rm", "-f", name],
                capture_output=True,
                timeout=30,
            )
        self._containers.clear()
        if self._network_created:
            subprocess.run(
                ["docker", "network", "rm", self.network],
                capture_output=True,
                timeout=15,
            )
            self._network_created = False

    def docker_run_args(self) -> list[str]:
        """Extra ``docker run`` args so the step container shares the network."""
        if self.docker_mode and self._network_created:
            return ["--network", self.network]
        return []

    def _ensure_network(self) -> bool:
        if self._network_created:
            return True
        result = subprocess.run(
            ["docker", "network", "create", self.network],
            capture_output=True,
            text=True,
            timeout=15,
        )
        if result.returncode != 0:
            print(f"Error: could not create Docker network {self.network}")
            if result.stderr:
                print(result.stderr.strip())
            return False
        self._network_created = True
        return True

    def _start_one(self, spec: ServiceSpec) -> bool:
        if not _ensure_image(spec.image):
            print(f"Error: failed to pull service image {spec.image}")
            return False

        ports = image_exposed_ports(spec.image)
        container = f"bb-run-{self.run_id}-{spec.name}"
        cmd = ["docker", "run", "-d", "--rm", "--name", container]
        if self.docker_mode:
            if not self._ensure_network():
                return False
            cmd.extend(["--network", self.network, "--network-alias", spec.name])
        for port in ports:
            cmd.extend(["-p", f"{port}:{port}"])
        for key, value in spec.variables.items():
            cmd.extend(["-e", f"{key}={value}"])
        cmd.append(spec.image)

        print(f"🔌 Service: starting {spec.name} ({spec.image})", flush=True)
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
        if result.returncode != 0:
            print(f"Error: could not start service {spec.name!r}")
            err = (result.stderr or result.stdout or "").strip()
            if err:
                print(err)
            return False

        self._containers.append(container)
        for port in ports:
            if not wait_tcp("127.0.0.1", port, timeout=45.0):
                print(
                    f"Error: service {spec.name!r} did not accept connections "
                    f"on 127.0.0.1:{port}"
                )
                return False
            print(f"🔌 Service: {spec.name} ready on 127.0.0.1:{port}")
        if not ports:
            print(f"🔌 Service: {spec.name} started (no EXPOSE ports to wait on)")
        return True
