# bb-run

[![PyPI](https://img.shields.io/pypi/v/bb-run.svg)](https://pypi.org/project/bb-run/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python](https://img.shields.io/badge/python-3.12%2B-blue)](https://pypi.org/project/bb-run/)
[![Test](https://github.com/karlhillx/bb-run/actions/workflows/test.yml/badge.svg)](https://github.com/karlhillx/bb-run/actions/workflows/test.yml)

**Run Bitbucket Pipelines locally.** bb-run reads `bitbucket-pipelines.yml` and runs it in **Docker** (default) or on the **host**, including **parallel** steps, **fail-fast**, and **artifacts**.

## Why bb-run?

- **Test before pushing** - Catch CI failures locally before committing
- **Fast iteration** - No waiting for Bitbucket's pipeline queue
- **Debug easily** - Run in verbose mode and inspect output directly
- **Two modes** - Docker for an environment closer to Bitbucket; host mode needs **no Docker**
- **Parallel steps** - `parallel:` groups run concurrently; group and per-step `fail-fast` stop sibling processes when a failing step demands it
- **Artifacts** - Shared / scoped uploads, `capture-on`, and selective `download` (see below)
- **Small install** - One runtime dependency: **PyYAML** (see `pyproject.toml`). Docker is only required for `--mode docker`

## Installation

### via pip

```bash
pip install bb-run
```

### via pipx (isolated CLI)

If you prefer not to use a project virtualenv:

```bash
pipx install bb-run
```

**Recommended for most CLI users:** **pipx** keeps bb-run out of system Python and usually puts `bb-run` on your `PATH` without extra setup.

### If `bb-run` is not on your `PATH`

After `pip install --user` or some IDE setups, the script directory may be missing from `PATH`. Run the same CLI via Python:

```bash
python3 -m bbrun --version
python3 -m bbrun --validate
```

### Homebrew

There is **no official Homebrew formula** in this repository yet. Use **pip** or **pipx** above for the supported install path.

To package for Homebrew later: submit a formula to [homebrew-core](https://github.com/Homebrew/homebrew-core) (tagged releases + tests that do not require Docker are typical expectations), or maintain a **third-party tap** and document it in your fork; see [Homebrew docs](https://docs.brew.sh/).

### from source

```bash
git clone https://github.com/karlhillx/bb-run.git
cd bb-run
pip install -e .
```

To run tests or Ruff locally, use the **dev** extra (includes pytest, pytest-cov, and ruff):

```bash
pip install -e ".[dev]"
```

## Using bb-run reliably

- Run commands from the **repository root** (the directory that contains `bitbucket-pipelines.yml`), or pass **`--repo /path/to/that/root`**.
- Prefer **`bb-run --validate`** first; it checks the file without Docker. If you do not have Docker, use **`--mode host`** for runs (see [Modes](#modes)).
- On macOS/Linux where `pip install` is restricted (PEP 668), use a venv, **`pipx`**, or:  
  `python3 -m pip install --user bb-run`  
  (then ensure that user script directory is on your `PATH`).

## Quick Start

### Validate a pipeline (instant)

```bash
cd /path/to/your/repo   # where bitbucket-pipelines.yml lives
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

### List targets as JSON

```bash
bb-run --list-targets --json
```

## Target Syntax

bb-run uses the same target naming as Bitbucket Pipelines:

- `default`
- `branches.<branch-name>`
- `tags.<tag-name>`
- `custom.<name>` for pipelines under `pipelines: custom:`
- `pull-requests.<pattern>` for pipelines under `pipelines: pull-requests:`

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

## Parallel steps

Bitbucket-style `parallel` blocks are supported in **Docker** and **host** mode. Child steps run at the same time. While a parallel group runs, each container / shell receives **`BITBUCKET_PARALLEL_STEP`** (0-based index) and **`BITBUCKET_PARALLEL_STEP_COUNT`**, matching [Bitbucket’s parallel variables](https://support.atlassian.com/bitbucket-cloud/docs/parallel-step-options/#Default-variables-for-parallel-steps).

```yaml
pipelines:
  default:
    - parallel:
        fail-fast: true
        steps:
          - step:
              name: Integration A
              script:
                - ./integration.sh --batch 1
          - step:
              name: Integration B
              script:
                - ./integration.sh --batch 2
```

You can set **`fail-fast: false`** on an individual step inside the group so its failure does not stop the others (when the group uses fail-fast).

## Artifacts

bb-run models [Bitbucket pipeline artifacts](https://support.atlassian.com/bitbucket-cloud/docs/use-artifacts-in-steps/) so later steps can rely on captured files even if you delete them mid-pipeline:

- **List form** — `artifacts: [dist/**, reports/*.txt]`
- **Object form** — `artifacts: { paths: [...], download: false }` plus optional **`upload:`** entries with **`name`**, **`type`** (`shared` / `scoped` / `test-reports`), **`paths`**, **`ignore-paths`**, and **`capture-on`** (`success` / `failed` / `always`)
- **`download`** — default is to restore all prior **shared** layers before a step; **`download: false`** skips that restore; a **list of names** restores only those shared artifacts (plus unnamed list-style captures as a fallback when nothing matches)

Captured trees are stored under **`.bb-run/artifacts/`** in the repo (ignored by git). **Shared** layers are replayed onto the clone directory before each step that downloads them. **Scoped** and **test-reports** uploads are saved for inspection but are **not** injected into later steps.

**Caveats:** With **`--mode host`** or a bind-mounted Docker workspace, files left on disk by an earlier step are still visible even when **`download: false`**; bb-run only controls replay from its cache, not deleting your working tree. Parallel groups capture each child **after** the whole group finishes, reading the final workspace (Bitbucket isolates children more strictly).

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

`--verbose` currently prints **`-v` / `--variables`** values before the run; more detail may be added later.

## Configuration

bb-run automatically looks for `bitbucket-pipelines.yml` in your current directory. Use `--repo` to specify a different path:

```bash
bb-run --repo /path/to/repo
```

## Supported vs Unsupported Bitbucket Features

**Supported (today):**

- `default`, `branches.<name>`, `tags.<name>`, `custom.<name>`, and `pull-requests.<pattern>` targets
- Step `script` execution (sequential)
- Basic environment variables (Bitbucket-style values)
- Docker images per step (Docker mode)

**Not yet supported / simplified:**

- Pipes (listed but not executed)
- Parallel steps or step conditions
- Services, caches, and artifacts
- Deployment environments, manual triggers, or step size

## Requirements

- **Python** 3.12+ (`requires-python` in `pyproject.toml`)
- **PyYAML** 6.x (installed automatically with `bb-run`)
- **Docker** CLI (optional; only for `--mode docker`, the default)

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
| `BITBUCKET_BUILD_NUMBER` | Build number (set to `"1"`) |
| `BITBUCKET_CLONE_DIR` | Repo root on the host; in Docker mode the path **inside** the container (`/opt/atlassian/pipelines/agent/build`) |
| `BITBUCKET_COMMIT` | Git commit SHA (or `local` if unavailable) |
| `BITBUCKET_BRANCH` | Branch name (from `--branch` or default) |
| `BITBUCKET_REPO_SLUG` | Repository directory name |
| `BITBUCKET_REPO_UUID` | Unique run ID for this process |
| `BITBUCKET_WORKSPACE` | Set to `"local"` |
| `BITBUCKET_PARALLEL_STEP` | Zero-based index inside a `parallel:` group (parallel steps only) |
| `BITBUCKET_PARALLEL_STEP_COUNT` | Number of steps in that parallel group (parallel steps only) |

## Troubleshooting

### "bitbucket-pipelines.yml not found"

You are not in the repo root, or the file name does not match exactly. **`cd`** into the project that contains the YAML, or use **`--repo`**.

### "No steps found for target"

The **`--target`** name does not match your file. List names with:

```bash
bb-run --list-targets
```

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

See [CONTRIBUTING.md](CONTRIBUTING.md). User-facing changes should be noted in [CHANGELOG.md](CHANGELOG.md). Security reports: [SECURITY.md](SECURITY.md).

## Links

- [PyPI](https://pypi.org/project/bb-run/)
- [GitHub Repository](https://github.com/karlhillx/bb-run)
- [Issue Tracker](https://github.com/karlhillx/bb-run/issues)
