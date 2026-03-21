"""
Host Runner - Executes pipeline steps directly on the host machine
"""

import os
import shutil
import subprocess
from pathlib import Path
from typing import Dict, List, Optional

from .artifacts import ArtifactSession
from .pipeline import parse_parallel_block, run_parallel_group, unwrap_step_item
from .validator import PipelineValidator


class HostRunner:
    """Runs pipeline steps directly on the host machine."""
    
    def __init__(self, repo_path: Path):
        self.repo_path = Path(repo_path)
        self.pipeline_file = self.repo_path / "bitbucket-pipelines.yml"
        self.variables = {}
        self.validator = PipelineValidator(repo_path)
    
    def _build_env(self, branch: str) -> Dict[str, str]:
        """Build environment variables."""
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
            'BITBUCKET_CLONE_DIR': str(self.repo_path),
            'BITBUCKET_COMMIT': commit,
            'BITBUCKET_BRANCH': branch,
            'BITBUCKET_REPO_SLUG': self.repo_path.name,
            'BITBUCKET_REPO_UUID': f'bb-run-{os.getpid()}',
            'BITBUCKET_WORKSPACE': 'local',
        })
        
        env.update(self.variables)
        
        return env
    
    def _translate_command(self, cmd: str) -> str:
        """Translate commands for host compatibility."""
        # Translate 'python' to 'python3' if python isn't available
        if not shutil.which('python') and cmd.startswith('python '):
            cmd = 'python3' + cmd[6:]
        
        # Translate 'pip ' to 'pip3 ' if pip isn't available
        if not shutil.which('pip') and cmd.startswith('pip ') and not cmd.startswith('pip3 '):
            cmd = 'pip3 ' + cmd[4:]
        
        # Add --break-system-packages for PEP 668
        if 'pip3 install' in cmd and '--break-system-packages' not in cmd:
            cmd = cmd.replace('pip3 install', 'pip3 install --break-system-packages')
            print("  (added --break-system-packages for PEP 668)")
        
        return cmd
    
    def _host_spawn_step(
        self, step: Dict, env: Dict, label: str
    ) -> Optional[subprocess.Popen]:
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
            )
        if "pipe" in step:
            pipe = step.get("pipe", "")
            print(f"{label}⚠️  Pipe: {pipe}")
            print(f"{label}    (pipes not executed in host mode)")
            return None
        print(f"{label}Warning: Step has no script or pipe")
        return None

    def _run_step(self, step: Dict, step_name: str, env: Dict) -> bool:
        """Execute a single pipeline step on the host."""
        print(f"\n{'='*60}")
        print(f"Step: {step_name}")
        print(f"{'='*60}")

        proc = self._host_spawn_step(step, env, label="")
        if proc is None:
            return True
        rc = proc.wait()
        if rc != 0:
            print(f"❌ Failed with exit code {rc}")
            return False
        return True

    def _run_parallel(
        self, parallel_block, env: Dict, artifacts: ArtifactSession
    ) -> bool:
        raw, group_ff = parse_parallel_block(parallel_block)
        n = len(raw)
        if n == 0:
            print("Warning: empty parallel group")
            return True

        # Same prior shared artifacts for every parallel child (Bitbucket injects downloads per step).
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
            return self._host_spawn_step(step, child_env, label=label)

        ok, each_ok = run_parallel_group(
            raw, group_fail_fast=group_ff, spawn=spawn
        )
        for i, item in enumerate(raw):
            st = unwrap_step_item(item)
            if isinstance(st, dict) and i < len(each_ok):
                artifacts.capture_after_step(st, each_ok[i])
        if not ok:
            print("❌ Parallel group failed")
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
        
        # Load pipeline
        config = self.validator.load()
        if not config:
            print("Error: Could not load pipeline")
            return False
        
        image = config.get('image', 'atlassian/default-image:latest')
        
        print(f"Repository: {self.repo_path}")
        print(f"Target: {target}")
        print(f"Branch: {branch}")
        print("Mode: HOST (runs on your machine)")
        print(f"Note: Uses '{image}' as reference for command mapping")
        
        # Get steps
        steps = self._get_steps(config, target)
        if not steps:
            print(f"No steps found for target: {target}")
            return False
        
        # Run steps
        env = self._build_env(branch)
        artifacts = ArtifactSession(self.repo_path)
        all_passed = True

        for i, item in enumerate(steps):
            if isinstance(item, dict) and "parallel" in item:
                if not self._run_parallel(item["parallel"], env, artifacts):
                    all_passed = False
                    break
                continue

            step = item.get("step", item)
            step_name = step.get("name", f"Step {i + 1}")

            artifacts.prepare_for_step(step)
            step_ok = self._run_step(step, step_name, env)
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