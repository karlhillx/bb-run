"""
Docker Runner - Executes pipeline steps in Docker containers
"""

import functools
import os
import subprocess
import sys
from pathlib import Path
from typing import Dict, List, Optional

from .artifacts import ArtifactSession
from .errors import explain_process_launch_error, report_step_script_failure
from .pipeline import (
    get_steps_for_target,
    parallel_failure_summaries,
    parse_parallel_block,
    run_parallel_group,
    unwrap_step_item,
)
from .validator import PipelineValidator


@functools.lru_cache(maxsize=1)
def _docker_pull_supports_progress_flag() -> bool:
    """True if this Docker CLI accepts `docker pull --progress`."""
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


class DockerRunner:
    """Runs pipeline steps in Docker containers."""
    
    def __init__(self, repo_path: Path):
        self.repo_path = Path(repo_path)
        self.pipeline_file = self.repo_path / "bitbucket-pipelines.yml"
        self.variables = {}
        self.validator = PipelineValidator(repo_path)
    
    def _docker_available(self) -> bool:
        """Check if Docker is available."""
        try:
            result = subprocess.run(
                ['docker', 'info'],
                capture_output=True,
                timeout=10
            )
            return result.returncode == 0
        except (subprocess.TimeoutExpired, FileNotFoundError):
            return False
    
    def _image_exists(self, image: str) -> bool:
        """Check if Docker image exists locally."""
        result = subprocess.run(
            ['docker', 'image', 'inspect', image],
            capture_output=True
        )
        return result.returncode == 0
    
    def _pull_image(self, image: str) -> bool:
        """Pull a Docker image; stream Docker's own progress to the terminal."""
        print(f"Pulling Docker image: {image}", flush=True)
        interactive = sys.stderr.isatty()
        if interactive:
            print(
                "Tip: each fs layer can take a while; lines update when a layer completes.",
                flush=True,
            )

        cmd = ["docker", "pull"]
        if _docker_pull_supports_progress_flag():
            # tty: animated bars when stderr is a real terminal; plain: steady line-based output.
            cmd.extend(["--progress", "tty" if interactive else "plain"])
        cmd.append(image)

        env = os.environ.copy()
        if interactive:
            # Editors/CI often set CI=1, which makes Docker suppress TTY-style progress.
            env.pop("CI", None)

        proc = subprocess.Popen(cmd, env=env)
        # Heartbeat: plain progress can look "stuck" on one line for minutes on large layers.
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
    
    def _build_env(self, branch: str) -> Dict[str, str]:
        """Build environment variables for the container."""
        env = dict(os.environ)
        
        # Get git commit
        try:
            commit = subprocess.run(
                ['git', 'rev-parse', 'HEAD'],
                capture_output=True,
                text=True,
                cwd=self.repo_path
            ).stdout.strip()
        except Exception:
            commit = 'local'
        
        env.update({
            'BITBUCKET_BUILD_NUMBER': '1',
            'BITBUCKET_CLONE_DIR': '/opt/atlassian/pipelines/agent/build',
            'BITBUCKET_COMMIT': commit,
            'BITBUCKET_BRANCH': branch,
            'BITBUCKET_REPO_SLUG': self.repo_path.name,
            'BITBUCKET_REPO_UUID': f'bb-run-{os.getpid()}',
            'BITBUCKET_WORKSPACE': 'local',
            'HOME': '/root',
        })
        
        # Add user variables
        env.update(self.variables)
        
        return env
    
    def _docker_spawn_step(
        self, step: Dict, default_image: str, env: Dict, label: str
    ) -> Optional[subprocess.Popen]:
        """Start a Docker-backed step; return Popen or None if nothing to run."""
        image = step.get("image", default_image)
        if not self._image_exists(image):
            print(f"Image not found locally: {image}")
            if not self._pull_image(image):
                print(f"Failed to pull image {image}")
                raise RuntimeError(f"docker pull failed: {image}")

        docker_cmd = [
            "docker",
            "run",
            "--rm",
            "-w",
            "/opt/atlassian/pipelines/agent/build",
            "-v",
            f"{self.repo_path}:/opt/atlassian/pipelines/agent/build:rw",
        ]
        for key, value in env.items():
            docker_cmd.extend(["-e", f"{key}={value}"])
        docker_cmd.append(image)

        if "script" in step:
            script = step["script"]
            bash_cmd = (
                " && ".join(script) if isinstance(script, list) else script
            )
            docker_cmd.extend(["/bin/bash", "-c", bash_cmd])
            print(f"{label}Executing: {bash_cmd[:60]}...")
            return subprocess.Popen(
                docker_cmd,
                cwd=self.repo_path,
                env=env,
            )
        if "pipe" in step:
            pipe = step["pipe"]
            print(f"{label}Pipe: {pipe}")
            print(f"{label}Note: Pipes are not executed in Docker mode (simplified)")
            return None
        print(f"{label}Warning: Step has no script or pipe")
        return None

    def _run_step(self, step: Dict, step_name: str, default_image: str, env: Dict) -> bool:
        """Execute a single pipeline step in Docker."""
        print(f"\n{'='*60}")
        print(f"Step: {step_name}")
        print(f"{'='*60}")
        try:
            proc = self._docker_spawn_step(step, default_image, env, label="")
        except RuntimeError as e:
            print(f"❌ {e}")
            return False
        except OSError as e:
            print(f"❌ {explain_process_launch_error(e)}")
            return False
        if proc is None:
            return True
        result = proc.wait()
        if result != 0:
            report_step_script_failure(step_name, result, docker=True)
            return False
        return True

    def _run_parallel(
        self,
        parallel_block,
        default_image: str,
        env: Dict,
        artifacts: ArtifactSession,
    ) -> bool:
        raw, group_ff = parse_parallel_block(parallel_block)
        n = len(raw)
        if n == 0:
            print("Warning: empty parallel group")
            return True

        artifacts.prepare_for_step({})

        ff_note = "fail-fast: on" if group_ff else "fail-fast: off"
        print(f"\n{'='*60}")
        print(f"Parallel group ({n} steps, {ff_note})")
        print(f"{'='*60}")
        for j, item in enumerate(raw):
            st = unwrap_step_item(item)
            nm = st.get("name", f"step {j + 1}") if isinstance(st, dict) else j
            print(f"  • {nm}")

        def spawn(i: int, step: Dict) -> Optional[subprocess.Popen]:
            child_env = dict(env)
            child_env["BITBUCKET_PARALLEL_STEP"] = str(i)
            child_env["BITBUCKET_PARALLEL_STEP_COUNT"] = str(n)
            name = step.get("name", f"step {i + 1}") if isinstance(step, dict) else i
            label = f"[parallel {i + 1}/{n} | {name}] "
            return self._docker_spawn_step(
                step, default_image, child_env, label=label
            )

        ok, each_ok = run_parallel_group(
            raw, group_fail_fast=group_ff, spawn=spawn
        )
        for i, item in enumerate(raw):
            st = unwrap_step_item(item)
            if isinstance(st, dict) and i < len(each_ok):
                artifacts.capture_after_step(st, each_ok[i])
        if not ok:
            print("❌ Parallel group failed")
            for line in parallel_failure_summaries(raw, each_ok):
                print(f"   • {line}")
        return ok
    
    def run(
        self,
        target: str = 'default',
        branch: str = 'LOCAL',
        variables: Optional[Dict] = None,
        verbose: bool = False
    ) -> bool:
        """Run the pipeline for a given target."""
        if variables:
            self.variables.update(variables)

        if verbose and self.variables:
            print(f"(verbose) Extra variables: {self.variables}")

        # Check Docker
        if not self._docker_available():
            print("Error: Docker is not available")
            print("Use --mode host to run on your host machine instead")
            return False
        
        # Load pipeline
        config = self.validator.load()
        if not config:
            print("Error: Could not load pipeline")
            return False
        
        default_image = config.get('image', 'atlassian/default-image:latest')
        
        print(f"Repository: {self.repo_path}")
        print(f"Target: {target}")
        print(f"Branch: {branch}")
        print("Mode: DOCKER")
        print(f"Image: {default_image}")
        
        # Get steps
        steps = self._get_steps(config, target)
        if not steps:
            print(f"No steps found for target: {target}")
            print("Hint: bb-run --list-targets")
            return False
        
        # Run steps
        env = self._build_env(branch)
        artifacts = ArtifactSession(self.repo_path)
        all_passed = True

        for i, item in enumerate(steps):
            if isinstance(item, dict) and "parallel" in item:
                if not self._run_parallel(
                    item["parallel"], default_image, env, artifacts
                ):
                    all_passed = False
                    break
                continue

            step = item.get("step", item)
            step_name = step.get("name", f"Step {i + 1}")

            artifacts.prepare_for_step(step)
            step_ok = self._run_step(step, step_name, default_image, env)
            artifacts.capture_after_step(step, step_ok)
            if not step_ok:
                all_passed = False
                break
        
        if all_passed:
            print(f"\n{'='*60}")
            print("✅ All steps completed successfully!")
            print(f"{'='*60}")
        else:
            print(f"\n{'='*60}")
            print("❌ Pipeline failed!")
            print(f"{'='*60}")
        
        return all_passed
    
    def _get_steps(self, config: Dict, target: str) -> List:
        """Get steps for a given target."""
        return get_steps_for_target(config, target)
