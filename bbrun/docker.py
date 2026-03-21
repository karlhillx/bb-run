"""
Docker Runner - Executes pipeline steps in Docker containers
"""

import functools
import os
import subprocess
import sys
from pathlib import Path
from typing import Dict, List, Optional

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
    
    def _run_step(self, step: Dict, step_name: str, default_image: str, env: Dict) -> bool:
        """Execute a single pipeline step in Docker."""
        print(f"\n{'='*60}")
        print(f"Step: {step_name}")
        print(f"{'='*60}")
        
        # Resolve image
        image = step.get('image', default_image)
        
        # Check/pull image
        if not self._image_exists(image):
            print(f"Image not found locally: {image}")
            if not self._pull_image(image):
                print(f"Failed to pull image {image}")
                return False
        
        # Build docker command
        docker_cmd = [
            'docker', 'run', '--rm',
            '-w', '/opt/atlassian/pipelines/agent/build',
            '-v', f'{self.repo_path}:/opt/atlassian/pipelines/agent/build:rw'
        ]
        
        # Add environment variables
        for key, value in env.items():
            docker_cmd.extend(['-e', f'{key}={value}'])
        
        docker_cmd.append(image)
        
        # Handle script vs pipe
        if 'script' in step:
            script = step['script']
            if isinstance(script, list):
                bash_cmd = ' && '.join(script)
            else:
                bash_cmd = script
            
            docker_cmd.extend(['/bin/bash', '-c', bash_cmd])
            print(f"Executing: {bash_cmd[:60]}...")
        elif 'pipe' in step:
            pipe = step['pipe']
            print(f"Pipe: {pipe}")
            print("Note: Pipes are not executed in Docker mode (simplified)")
            return True
        else:
            print("Warning: Step has no script or pipe")
            return True
        
        # Run
        result = subprocess.run(
            docker_cmd,
            cwd=self.repo_path,
            env=env
        )
        
        if result.returncode != 0:
            print(f"❌ Failed with exit code {result.returncode}")
            return False
        
        return True
    
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
            return False
        
        # Run steps
        env = self._build_env(branch)
        all_passed = True
        
        for i, item in enumerate(steps):
            step = item.get('step', item)
            step_name = step.get('name', f'Step {i+1}')
            
            if not self._run_step(step, step_name, default_image, env):
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
        pipelines = config.get('pipelines', {})
        
        if target == 'default':
            return pipelines.get('default', [])
        
        if target.startswith('branches.'):
            branch_name = target.split('.', 1)[1]
            return pipelines.get('branches', {}).get(branch_name, [])
        
        if target.startswith('tags.'):
            tag_name = target.split('.', 1)[1]
            return pipelines.get('tags', {}).get(tag_name, [])
        
        if target in pipelines:
            return pipelines[target]
        
        return []