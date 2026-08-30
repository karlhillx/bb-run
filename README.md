# bb-run

[![PyPI](https://img.shields.io/pypi/v/bb-run.svg)](https://pypi.org/project/bb-run/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python](https://img.shields.io/badge/python-3.12%2B-blue)](https://pypi.org/project/bb-run/)
[![Test](https://github.com/karlhillx/bb-run/actions/workflows/test.yml/badge.svg)](https://github.com/karlhillx/bb-run/actions/workflows/test.yml)

**Run Bitbucket Pipelines locally.** bb-run reads `bitbucket-pipelines.yml` and runs it in **Docker** or on the **host**, including **parallel** steps, **fail-fast**, **artifacts**, **services**, **caches**, and **after-script**.

## Why bb-run?

- **Test before pushing** - Catch CI failures locally before committing
- **Fast iteration** - No waiting for Bitbucket's pipeline queue
- **Works on uv repos** - Auto-picks a target when there is no `default` pipeline; falls back to host when Docker is down
- **Two modes** - Docker for an environment closer to Bitbucket; host mode needs **no Docker** for script-only steps
- **Parallel steps** - `parallel:` groups run concurrently; group and per-step `fail-fast` stop sibling processes when a failing step demands it
- **Services and caches** - Sidecars (e.g. RabbitMQ) and `definitions.caches` so integration steps can pass locally
- **Small install** - One runtime dependency: **PyYAML** (see `pyproject.toml`). Docker is only required for `--mode docker` and for steps that declare `services:`

## Installation

### uvx (recommended — zero install)

Works in any checkout that has `bitbucket-pipelines.yml`, including uv-based Jacobs-family repos:

```bash
cd /path/to/your/repo
uvx bb-run
```

Persistent install on your `PATH`:

```bash
uv tool install bb-run
bb-run --validate
```

### via pipx (isolated CLI)

```bash
pipx install bb-run
```

### via pip

```bash
pip install bb-run
```

### If `bb-run` is not on your `PATH`

```bash
python3 -m bbrun --version
python3 -m bbrun --validate
```

### Homebrew

Install from the [karlhillx/tap](https://github.com/karlhillx/homebrew-tap) tap:

```bash
brew install karlhillx/tap/bb-run
```

This bundles bb-run and its runtime dependency (PyYAML) into an isolated Homebrew-managed Python environment. Docker is still only required for `--mode docker` and for pipeline services.

There is not yet a formula in [homebrew-core](https://github.com/Homebrew/homebrew-core) (`brew install bb-run` with no tap). That path requires meeting Homebrew’s notability bar (roughly 75+ GitHub stars / 30+ forks) and maintainer review.

### from source

```bash
git clone https://github.com/karlhillx/bb-run.git
cd bb-run
uv sync
uv run python -m bbrun --version
```

## Using bb-run reliably

- Run commands from the **repository root** (the directory that contains `bitbucket-pipelines.yml`), or pass **`--repo /path/to/that/root`**. From a subdirectory, bb-run **walks up** until it finds the YAML.
- Prefer **`bb-run --validate`** first; it checks the file without Docker. If you do not have Docker, `--mode auto` (the default) uses **host** for runs.
- On macOS/Linux where `pip install` is restricted (PEP 668), prefer **`uvx`**, **`uv tool`**, **`pipx`**, or a venv.

### uv / Jacobs-family repos

Pipelines that look like pylynx-mq, orchestrator, and the rest of that uv template typically have **no `default` pipeline**. They use `pull-requests.**` / `branches.master`, `definitions.caches` (`uv`, `pre-commit`), and RabbitMQ as a `services:` sidecar.

```bash
cd ../pylynx-mq
uvx bb-run                          # auto target + auto mode
uvx bb-run --step "Unit tests"      # one named step
uvx bb-run --step "Code quality"
uvx bb-run --dry-run --json         # plan only
```

Integration and scenario steps start RabbitMQ via Docker and publish it on `127.0.0.1` (those scripts set `RABBIT_HOST=127.0.0.1`). Unit and lint steps do not need Docker when you use host mode.

## Quick Start

### Validate a pipeline (instant)

```bash
cd /path/to/your/repo   # where bitbucket-pipelines.yml lives
bb-run --validate
```

### Run the resolved pipeline

```bash
bb-run
```

With no `--target`, bb-run picks `branches.<current-git-branch>` when that exists, otherwise `default`, otherwise `pull-requests.**`, otherwise the first listed target.

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

### Preview a run without executing commands

```bash
bb-run --dry-run
bb-run --target branches.feature/my-work --branch feature/my-work --dry-run
bb-run --dry-run --json
```

### Run one named step

```bash
bb-run --step "Unit tests"
bb-run --only "Code quality" --only "Unit tests"
```

## Target Syntax

bb-run uses the same target naming as Bitbucket Pipelines:

- `default`
- `branches.<branch-name>`
- `tags.<tag-name>`
- `custom.<name>` for pipelines under `pipelines: custom:`
- `pull-requests.<pattern>` for pipelines under `pipelines: pull-requests:`

For `branches.*`, `tags.*`, and `pull-requests.*`, bb-run first tries an exact key match and then falls back to Bitbucket-style wildcard keys like `feature/*`, `release/**`, `v*`, or `**`.

## Modes

### Auto (default)

Uses Docker when `docker info` succeeds; otherwise host. Pass `--mode docker` or `--mode host` to force a mode.

### Docker Mode

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

If any child in the group declares `services:`, bb-run runs those children **sequentially** so sidecar ports (for example RabbitMQ on 5672) do not clash.

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

## Services

Steps may list names from [`definitions.services`](https://support.atlassian.com/bitbucket-cloud/docs/cache-and-service-container-definitions/):

```yaml
definitions:
  services:
    rabbitmq:
      image: rabbitmq:4.2
```

bb-run starts each sidecar with Docker, publishes **EXPOSE** ports on `127.0.0.1`, waits for TCP, and tears the container down after the step (including Ctrl-C). The built-in `docker` service is not started. Use **`--no-services`** to skip sidecars.

Service steps need a working Docker daemon even in `--mode host`.

## Caches

Step `caches:` entries use Bitbucket predefined names (`pip`, `node`, `yarn`, …) plus `definitions.caches` path maps (`uv: ~/.cache/uv`). Snapshots live under **`.bb-run/caches/`** in the repo (gitignored). Host mode copies to/from the declared path; Docker mode bind-mounts the store. Use **`--no-cache`** to skip.

## Artifacts

bb-run models [Bitbucket pipeline artifacts](https://support.atlassian.com/bitbucket-cloud/docs/use-artifacts-in-steps/) so later steps can rely on captured files even if you delete them mid-pipeline:

- **List form** — `artifacts: [dist/**, reports/*.txt]`
- **Object form** — `artifacts: { paths: [...], download: false }` plus optional **`upload:`** entries with **`name`**, **`type`** (`shared` / `scoped` / `test-reports`), **`paths`**, **`ignore-paths`**, and **`capture-on`** (`success` / `failed` / `always`)
- **`download`** — default is to restore all prior **shared** layers before a step; **`download: false`** skips that restore; a **list of names** restores only those shared artifacts (plus unnamed list-style captures as a fallback when nothing matches)

Captured trees are stored under **`.bb-run/artifacts/`** in the repo (ignored by git). **Shared** layers are replayed onto the clone directory before each step that downloads them. **Scoped** and **test-reports** uploads are saved for inspection but are **not** injected into later steps.

**Caveats:** With **`--mode host`** or a bind-mounted Docker workspace, files left on disk by an earlier step are still visible even when **`download: false`**; bb-run only controls replay from its cache, not deleting your working tree. Parallel groups capture each child **after** the whole group finishes, reading the final workspace (Bitbucket isolates children more strictly).

## after-script

`after-script` runs in a **new** shell after `script`, whether the script succeeded or failed. `BITBUCKET_EXIT_CODE` is set from the script. The step fails if **either** block fails.

## Examples

### Python / uv project

```bash
cd my-python-project
uvx bb-run
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

`--verbose` prints the resolved target, extra `-v` variables, full scripts, services, cache mounts, and the Docker argv.

## Configuration

bb-run automatically looks for `bitbucket-pipelines.yml` in your current directory and parent directories. Use `--repo` to specify a different path:

```bash
bb-run --repo /path/to/repo
```

## Exit Codes

bb-run uses conventional exit codes so it composes well in scripts and CI:

| Code | Meaning |
|------|---------|
| `0` | Success (pipeline passed, or validation/listing succeeded) |
| `1` | Runtime failure (a step failed, file missing, or pipeline invalid) |
| `2` | Usage error (bad arguments, e.g. malformed `-v KEY=VALUE`) |
| `130` | Interrupted with `Ctrl-C` |

## Use as a library

bb-run ships type hints (`py.typed`) and a small public API, so you can drive it from Python:

```python
from bbrun import HostRunner, DockerRunner, PipelineValidator, resolve_auto_target

# Validate without running
validator = PipelineValidator(".")
if validator.validate():
    validator.show_summary()

# Run the default pipeline on the host
runner = HostRunner(".")
ok = runner.run(target="default", branch="main", variables={"ENVIRONMENT": "staging"})
raise SystemExit(0 if ok else 1)
```

`DockerRunner` and `HostRunner` share a common `BaseRunner`; both expose the same
`run(...)` signature and return `True` on success.

## Supported vs Unsupported Bitbucket Features

**Supported (today):**

- `default`, `branches.<name>`, `tags.<name>`, `custom.<name>`, and `pull-requests.<pattern>` targets
- Bitbucket-style wildcard target keys (`feature/*`, `release/**`, `v*`, `**`)
- Auto target selection and walk-up to `bitbucket-pipelines.yml`
- Step `script` and `after-script` execution (sequential; after-script in a new shell)
- `parallel:` groups with group-level and per-step `fail-fast`
- Artifacts: shared / scoped / test-reports uploads, `capture-on`, and selective `download`
- `definitions.services` sidecars with localhost port publish
- `definitions.caches` and common predefined cache names
- Per-step Docker images (Docker mode)
- Bitbucket-style environment variables and user-supplied `-v KEY=VALUE`

**Not yet supported / simplified:**

- Pipes (listed but not executed)
- The built-in `docker` service (Docker-in-Docker)
- Deployment environments, manual triggers, and step size
- Step conditions

## Requirements

- **Python** 3.12+ (`requires-python` in `pyproject.toml`)
- **PyYAML** 6.x (installed automatically with `bb-run`)
- **Docker** CLI (optional; required for `--mode docker` and for `services:`)

### Local development

```bash
uv sync
uv run pytest
uv run pytest --cov=bbrun --cov-report=xml tests/
uv run ruff check bbrun tests
uv run ty check
```

## Environment Variables

bb-run sets these Bitbucket-specific environment variables:

| Variable | Description |
|----------|-------------|
| `CI` | Set to `true` |
| `BITBUCKET_BUILD_NUMBER` | Build number (set to `"1"`) |
| `BITBUCKET_CLONE_DIR` | Repo root on the host; in Docker mode the path **inside** the container (`/opt/atlassian/pipelines/agent/build`) |
| `BITBUCKET_COMMIT` | Git commit SHA (or `local` if unavailable) |
| `BITBUCKET_BRANCH` | Branch name (from `--branch` or default) |
| `BITBUCKET_TAG` | Tag name (from `--tag`, or empty) |
| `BITBUCKET_REPO_SLUG` | Repository directory name |
| `BITBUCKET_REPO_UUID` | Unique run ID for this process |
| `BITBUCKET_PIPELINE_UUID` | UUID for this bb-run invocation |
| `BITBUCKET_STEP_UUID` | UUID for the current step |
| `BITBUCKET_WORKSPACE` | Set to `"local"` |
| `BITBUCKET_GIT_HTTP_ORIGIN` | Best-effort `origin` HTTPS URL |
| `BITBUCKET_GIT_SSH_ORIGIN` | Best-effort `origin` SSH URL |
| `BITBUCKET_EXIT_CODE` | Script exit code, set for `after-script` only |
| `BITBUCKET_PARALLEL_STEP` | Zero-based index inside a `parallel:` group (parallel steps only) |
| `BITBUCKET_PARALLEL_STEP_COUNT` | Number of steps in that parallel group (parallel steps only) |

## Troubleshooting

### "bitbucket-pipelines.yml not found"

You are not in the repo (or a subdirectory of it), or the file name does not match exactly. **`cd`** into the project that contains the YAML, or use **`--repo`**.

### "No steps found for target"

The **`--target`** name does not match your file, or auto-select could not find a pipeline. List names with:

```bash
bb-run --list-targets
```

Repos without a `default` pipeline are normal; bb-run will use `pull-requests.**` or `branches.<git-branch>` when those exist.

### "Docker is not available"

Omit `--mode` to auto-fall back to host, or force it:

```bash
bb-run --mode host
```

Steps that declare `services:` still need Docker unless you pass `--no-services`.

### "step requires services but Docker is not available"

Start Docker Desktop / the daemon, or skip sidecars with `--no-services` (integration tests that expect RabbitMQ will then fail).

### `uvx: command not found`

Install [uv](https://docs.astral.sh/uv/) (`curl -LsSf https://astral.sh/uv/install.sh | sh` or `brew install uv`), then retry `uvx bb-run`.

### "pip: command not found"

bb-run automatically translates `pip` to `pip3` and adds `--break-system-packages` for PEP 668 environments.

### `pytest: error: unrecognized arguments: --cov=...`

Coverage flags come from the **pytest-cov** plugin. Use the `dev` extra:

```bash
uv sync
uv run pytest --cov=bbrun --cov-report=xml tests/
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
