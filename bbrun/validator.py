"""
Pipeline YAML Validator
"""

from pathlib import Path
from typing import Any

import yaml

from .artifacts import iter_upload_specs
from .pipeline import parse_parallel_block
from .ui import get_ui


class PipelineValidator:
    """Validates and parses bitbucket-pipelines.yml"""

    def __init__(self, repo_path: Path):
        self.repo_path = Path(repo_path)
        self.pipeline_file = self.repo_path / "bitbucket-pipelines.yml"
        self._config: dict | None = None
        self.last_error: str | None = None

    def load(self) -> dict | None:
        """Load and parse the pipeline YAML. Sets ``last_error`` on failure."""
        self.last_error = None
        if not self.pipeline_file.exists():
            self.last_error = (
                f"{self.pipeline_file.name} not found in {self.repo_path.resolve()}"
            )
            return None

        try:
            with open(self.pipeline_file, encoding="utf-8") as f:
                data = yaml.safe_load(f)
        except yaml.YAMLError as e:
            self.last_error = f"YAML parse error: {e}"
            return None
        except OSError as e:
            self.last_error = f"Error reading {self.pipeline_file}: {e}"
            return None

        if data is None:
            self.last_error = "Pipeline file is empty"
            return None
        if not isinstance(data, dict):
            self.last_error = (
                "Pipeline file must start with a YAML mapping "
                "(object), not a list or plain value."
            )
            return None

        self._config = data
        return self._config

    def validate(self) -> bool:
        """Validate the pipeline configuration and print any error."""
        config = self.load()
        ui = get_ui()
        if not config:
            ui.error(self.last_error or "Invalid or missing bitbucket-pipelines.yml")
            return False

        if "pipelines" not in config:
            self.last_error = "Missing 'pipelines' key"
            ui.error(self.last_error)
            return False

        return True

    def show_summary(self) -> None:
        """Print a summary of the pipeline."""
        if not self._config:
            return

        ui = get_ui()
        image = self._config.get("image", "atlassian/default-image:latest")
        ui.info(f"\nImage: {image}")

        pipelines = self._config.get("pipelines", {})

        if "default" in pipelines:
            ui.info("\ndefault:")
            for item in pipelines["default"]:
                self._show_step(item)

        branches = pipelines.get("branches", {})
        if branches:
            ui.info("\nbranches:")
            for branch, items in branches.items():
                ui.info(f"   {branch}:")
                for item in items:
                    self._show_step(item, indent=4)

        tags = pipelines.get("tags", {})
        if tags:
            ui.info("\ntags:")
            for tag, items in tags.items():
                ui.info(f"   {tag}:")
                for item in items:
                    self._show_step(item, indent=4)

        custom = pipelines.get("custom", {})
        if custom:
            ui.info("\ncustom:")
            for name, items in custom.items():
                ui.info(f"   {name}:")
                for item in items:
                    self._show_step(item, indent=4)

        pull_requests = pipelines.get("pull-requests", {})
        if pull_requests:
            ui.info("\npull-requests:")
            for name, items in pull_requests.items():
                ui.info(f"   {name}:")
                for item in items:
                    self._show_step(item, indent=4)

    def _show_step(self, item: Any, indent: int = 2) -> None:
        """Show details of a single step or parallel group."""
        if not isinstance(item, dict):
            return
        ui = get_ui()
        if "parallel" in item:
            raw, ff = parse_parallel_block(item["parallel"])
            prefix = " " * indent
            mode = "fail-fast" if ff else "no fail-fast"
            ui.info(f"{prefix}parallel ({len(raw)} steps, {mode}):")
            for sub in raw:
                self._show_step(sub, indent + 2)
            return

        step = item.get("step", item)
        if not isinstance(step, dict):
            return
        name = step.get("name", "unnamed")
        prefix = " " * indent
        bullet = ui.bullet

        suffix = ""
        if step.get("deployment"):
            suffix += f" [{step['deployment']}]"
        if step.get("trigger"):
            suffix += f" ({step['trigger']})"

        ui.info(f"{prefix}{bullet} {name}{suffix}")

        raw_art = step.get("artifacts")
        if isinstance(raw_art, dict) and "download" in raw_art:
            ui.info(f"{prefix}  artifacts.download: {raw_art['download']}")
        for spec in iter_upload_specs(step):
            tag = spec.name or "paths"
            ui.info(
                f"{prefix}  artifact upload [{tag}] "
                f"type={spec.type} capture-on={spec.capture_on}"
            )
            for p in spec.paths[:8]:
                ui.info(f"{prefix}     {p}")
            if len(spec.paths) > 8:
                ui.info(f"{prefix}     … ({len(spec.paths)} patterns)")

        for cmd in step.get("script", []):
            if isinstance(cmd, str):
                display = cmd[:70] + "..." if len(cmd) > 70 else cmd
                ui.info(f"{prefix}  $ {display}")
            elif isinstance(cmd, dict) and "pipe" in cmd:
                pipe_name = cmd["pipe"]
                vars_str = ""
                if "variables" in cmd:
                    vars_str = f" ({cmd['variables']})"
                ui.info(f"{prefix}  pipe: {pipe_name}{vars_str}")

    @property
    def config(self) -> dict | None:
        """Get the loaded configuration."""
        return self._config
