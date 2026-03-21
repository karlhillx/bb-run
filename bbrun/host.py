"""
Host Runner - Executes pipeline steps directly on the host machine
"""

import os
import shutil
import subprocess
from pathlib import Path
from typing import Dict, List, Optional

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
    
    def _run_step(self, step: Dict, step_name: str, env: Dict) -> bool:
        """Execute a single pipeline step on the host."""
        print(f"\n{'='*60}")
        print(f"Step: {step_name}")
        print(f"{'='*60}")
        
        if 'script' in step:
            return self._run_script(step['script'], env)
        elif 'pipe' in step:
            return self._run_pipe(step)
        else:
            print("Warning: Step has no script or pipe")
            return True
    
    def _run_script(self, script: List[str], env: Dict) -> bool:
        """Run a script step."""
        if isinstance(script, list):
            commands = script
        else:
            commands = [script]
        
        for cmd in commands:
            translated = self._translate_command(cmd)
            print(f"$ {translated}")
            
            result = subprocess.run(
                translated,
                shell=True,
                cwd=self.repo_path,
                env=env
            )
            
            if result.returncode != 0:
                print(f"❌ Failed with exit code {result.returncode}")
                return False
        
        return True
    
    def _run_pipe(self, step: Dict) -> bool:
        """Handle a pipe step (not executed in host mode)."""
        pipe = step.get('pipe', '')
        print(f"⚠️  Pipe: {pipe}")
        print("    (pipes not executed in host mode)")
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
        all_passed = True
        
        for i, item in enumerate(steps):
            step = item.get('step', item)
            step_name = step.get('name', f'Step {i+1}')
            
            if not self._run_step(step, step_name, env):
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