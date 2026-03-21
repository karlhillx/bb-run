# bb-run

[![Version](https://img.shields.io/badge/dynamic/toml?url=https%3A%2F%2Fraw.githubusercontent.com%2Fkarlhillx%2Fbb-run%2Fmain%2Fpyproject.toml&query=project.version&label=version)](https://github.com/karlhillx/bb-run/blob/main/pyproject.toml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python 3.12+](https://img.shields.io/badge/python-3.12%2B-blue.svg)](https://github.com/karlhillx/bb-run/blob/main/pyproject.toml)
[![Test](https://github.com/karlhillx/bb-run/actions/workflows/test.yml/badge.svg)](https://github.com/karlhillx/bb-run/actions/workflows/test.yml)

**Run Bitbucket Pipelines locally.** bb-run faithfully executes your `bitbucket-pipelines.yml` on your local machine using Docker or directly on your host.

## Why bb-run?

- **Test before pushing** - Catch CI failures locally before committing
- **Fast iteration** - No waiting for Bitbucket's pipeline queue
- **Debug easily** - Run in verbose mode, inspect outputs directly
- **Two modes** - Docker for Bitbucket-accurate execution, Host for quick local testing
- **No dependencies** - Works with just Python and Docker (optional)

## Installation

### via pip

Install from **[PyPI](https://pypi.org/project/bb-run/)**:

```bash
pip install bb-run
```

### via Homebrew

```bash
brew install karlhillx/tap/bb-run
```

### from source

```bash
git clone https://github.com/karlhillx/bb-run.git
cd bb-run
pip install -e .
```

## Quick Start

### Validate a pipeline (instant)

```bash
bb-run --validate
```

### Run the default pipeline

```bash
bb-run
```

### Run a specific branch

```bash
bb-run --target branches.main
bb-run -t branches.main
```

### Simulate a feature branch

```bash
bb-run --branch feature/my-work
```

### Run on your host (no Docker)

```bash
bb-run --mode host
```

### Pass variables

```bash
bb-run -v ENVIRONMENT=staging -v API_KEY=secret
```

### List available targets

```bash
bb-run --list-targets
```

## Modes

### Docker Mode (default)

Runs steps in Docker containers matching Bitbucket's build environment.

```bash
bb-run --mode docker
```

**Pros:** Faithful reproduction of Bitbucket's environment  
**Cons:** Requires Docker, images may take time to download

### Host Mode

Runs steps directly on your local machine.

```bash
bb-run --mode host
```

**Pros:** Fast, no image downloads  
**Cons:** May differ from Bitbucket's environment (Python vs Python3, etc.)

## Examples

### Python project

```bash
cd my-python-project
bb-run
```

### Node.js project

```bash
cd my-node-project
bb-run --target branches.main
```

### Run with verbose output

```bash
bb-run --verbose
```

## Configuration

bb-run automatically looks for `bitbucket-pipelines.yml` in your current directory. Use `--repo` to specify a different path:

```bash
bb-run --repo /path/to/repo
```

## Requirements

- Python 3.12+
- PyYAML
- Docker (for Docker mode)

### Local development (virtualenv)

Use Python 3.12 for the project venv so `python --version` matches `requires-python` in `pyproject.toml`:

```bash
# macOS (Homebrew)
brew install python@3.12
"$(brew --prefix python@3.12)/bin/python3.12" -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
# or tests + coverage only: pip install -e ".[test]"
python -m pytest
python -m pytest --cov=bbrun --cov-report=xml tests/
ruff check bbrun
```

## Environment Variables

bb-run sets these Bitbucket-specific environment variables:

| Variable | Description |
|----------|-------------|
| `BITBUCKET_BUILD_NUMBER` | Build number (set to "1") |
| `BITBUCKET_CLONE_DIR` | Repository path |
| `BITBUCKET_COMMIT` | Git commit SHA |
| `BITBUCKET_BRANCH` | Branch name |
| `BITBUCKET_REPO_SLUG` | Repository name |
| `BITBUCKET_REPO_UUID` | Unique run ID |
| `BITBUCKET_WORKSPACE` | Workspace (set to "local") |

## Troubleshooting

### "Docker is not available"

Use `--mode host` to run on your local machine instead of in Docker:

```bash
bb-run --mode host
```

### "pip: command not found"

bb-run automatically translates `pip` to `pip3` and adds `--break-system-packages` for PEP 668 environments.

### `pytest: error: unrecognized arguments: --cov=...`

Coverage flags come from the **pytest-cov** plugin. Install the `test` or `dev` extra, then use the same interpreter for pytest:

```bash
pip install -e ".[dev]"
# or: pip install -e ".[test]"
python -m pytest --cov=bbrun --cov-report=xml tests/
```

### Image pull failures

Docker Hub rate limits may cause image downloads to fail. Try:
1. Waiting and retrying later
2. Using `--mode host` temporarily
3. Configuring a Docker mirror

## License

MIT License - see [LICENSE](LICENSE) for details.

## Contributing

Contributions welcome! Please open an issue or submit a PR.

## Publishing to PyPI

The package name **`bb-run`** must exist on PyPI (first upload is manual or via this workflow after [trusted publishing](https://docs.pypi.org/trusted-publishers/adding-a-publisher/) is configured).

1. In PyPI, add a **pending publisher** for this GitHub repo and workflow `publish.yml`, environment **`pypi`**.
2. In GitHub → **Settings → Environments**, create environment **`pypi`** (no secrets needed for trusted publishing).
3. Bump `version` in `pyproject.toml`, merge, then **create a GitHub Release** (or run the workflow manually after a release).

Badges in this README use **GitHub** (version from `pyproject.toml` on `main`) so they stay valid before the first PyPI release. After publishing, you can add e.g. `https://img.shields.io/pypi/v/bb-run.svg`.

## Links

- [PyPI project](https://pypi.org/project/bb-run/) (live after first successful upload)
- [GitHub Repository](https://github.com/karlhillx/bb-run)
- [Issue Tracker](https://github.com/karlhillx/bb-run/issues)