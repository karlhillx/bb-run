"""
Pipeline YAML Validator
"""

import yaml
from pathlib import Path
from typing import Any, Dict, Optional

from .artifacts import iter_upload_specs
from .pipeline import parse_parallel_block


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
            with open(self.pipeline_file, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f)
        except yaml.YAMLError as e:
            print(f"YAML parse error: {e}")
            return None
        except OSError as e:
            print(f"Error reading {self.pipeline_file}: {e}")
            return None

        if data is None:
            print("Error: Pipeline file is empty")
            return None
        if not isinstance(data, dict):
            print(
                "Error: Pipeline file must start with a YAML mapping "
                "(object), not a list or plain value."
            )
            return None

        self._config = data
        return self._config
    
    def validate(self) -> bool:
        """Validate the pipeline configuration."""
        if not self.pipeline_file.exists():
            print(
                f"Error: {self.pipeline_file.name} not found in "
                f"{self.repo_path.resolve()}"
            )
            return False

        config = self.load()

        if not config:
            return False

        if "pipelines" not in config:
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
    
    def _show_step(self, item: Any, indent: int = 2) -> None:
        """Show details of a single step or parallel group."""
        if not isinstance(item, dict):
            return
        if "parallel" in item:
            raw, ff = parse_parallel_block(item["parallel"])
            prefix = " " * indent
            mode = "fail-fast" if ff else "no fail-fast"
            print(f"{prefix}parallel ({len(raw)} steps, {mode}):")
            for sub in raw:
                self._show_step(sub, indent + 2)
            return

        step = item.get("step", item)
        if not isinstance(step, dict):
            return
        name = step.get("name", "unnamed")
        prefix = " " * indent
        
        suffix = ""
        if step.get('deployment'):
            suffix += f" [{step['deployment']}]"
        if step.get('trigger'):
            suffix += f" ({step['trigger']})"
        
        print(f"{prefix}• {name}{suffix}")

        raw_art = step.get("artifacts")
        if isinstance(raw_art, dict) and "download" in raw_art:
            print(f"{prefix}  → artifacts.download: {raw_art['download']}")
        for spec in iter_upload_specs(step):
            tag = spec.name or "paths"
            print(
                f"{prefix}  → artifact upload [{tag}] "
                f"type={spec.type} capture-on={spec.capture_on}"
            )
            for p in spec.paths[:8]:
                print(f"{prefix}     {p}")
            if len(spec.paths) > 8:
                print(f"{prefix}     … ({len(spec.paths)} patterns)")

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