"""
Pipeline YAML Validator
"""

import yaml
from pathlib import Path
from typing import Dict, Optional


class PipelineValidator:
    """Validates and parses bitbucket-pipelines.yml"""
    
    def __init__(self, repo_path: Path):
        self.repo_path = Path(repo_path)
        self.pipeline_file = self.repo_path / "bitbucket-pipelines.yml"
        self._config: Optional[Dict] = None
    
    def load(self) -> Optional[Dict]:
        """Load and parse the pipeline YAML."""
        if not self.pipeline_file.exists():
            return None
        
        try:
            with open(self.pipeline_file, 'r') as f:
                self._config = yaml.safe_load(f)
            return self._config
        except yaml.YAMLError as e:
            print(f"YAML parse error: {e}")
            return None
    
    def validate(self) -> bool:
        """Validate the pipeline configuration."""
        config = self.load()
        
        if not config:
            return False
        
        # Check for required 'pipelines' key
        if 'pipelines' not in config:
            print("Error: Missing 'pipelines' key")
            return False
        
        return True
    
    def show_summary(self) -> None:
        """Print a summary of the pipeline."""
        if not self._config:
            return
        
        image = self._config.get('image', 'atlassian/default-image:latest')
        print(f"\nImage: {image}")
        
        pipelines = self._config.get('pipelines', {})
        
        # Default pipeline
        if 'default' in pipelines:
            print("\n📦 default:")
            for item in pipelines['default']:
                self._show_step(item)
        
        # Branches
        branches = pipelines.get('branches', {})
        if branches:
            print("\n🌿 branches:")
            for branch, items in branches.items():
                print(f"   {branch}:")
                for item in items:
                    self._show_step(item, indent=4)
        
        # Tags
        tags = pipelines.get('tags', {})
        if tags:
            print("\n🏷️  tags:")
            for tag, items in tags.items():
                print(f"   {tag}:")
                for item in items:
                    self._show_step(item, indent=4)
    
    def _show_step(self, item: Dict, indent: int = 2) -> None:
        """Show details of a single step."""
        step = item.get('step', item)
        name = step.get('name', 'unnamed')
        prefix = " " * indent
        
        suffix = ""
        if step.get('deployment'):
            suffix += f" [{step['deployment']}]"
        if step.get('trigger'):
            suffix += f" ({step['trigger']})"
        
        print(f"{prefix}• {name}{suffix}")
        
        for cmd in step.get('script', []):
            if isinstance(cmd, str):
                display = cmd[:70] + "..." if len(cmd) > 70 else cmd
                print(f"{prefix}  → {display}")
            elif isinstance(cmd, dict) and 'pipe' in cmd:
                pipe_name = cmd['pipe']
                vars_str = ""
                if 'variables' in cmd:
                    vars_str = f" ({cmd['variables']})"
                print(f"{prefix}  → pipe: {pipe_name}{vars_str}")
    
    @property
    def config(self) -> Optional[Dict]:
        """Get the loaded configuration."""
        return self._config