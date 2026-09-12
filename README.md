```text
╔═══════════════════════════════════════════════════════════════════════════╗
║                                                                           ║
║             ██████╗ ██████╗       ██████╗ ██╗   ██╗███╗   ██╗             ║
║             ██╔══██╗██╔══██╗      ██╔══██╗██║   ██║████╗  ██║             ║
║             ██████╔╝██████╔╝█████╗██████╔╝██║   ██║██╔██╗ ██║             ║
║             ██╔══██╗██╔══██╗╚════╝██╔══██╗██║   ██║██║╚██╗██║             ║
║             ██████╔╝██████╔╝      ██║  ██║╚██████╔╝██║ ╚████║             ║
║             ╚═════╝ ╚═════╝       ╚═╝  ╚═╝ ╚═════╝ ╚═╝  ╚═══╝             ║
║                                                                           ║
║                      Run Bitbucket Pipelines locally                      ║
║                                                                           ║
╚═══════════════════════════════════════════════════════════════════════════╝
```

# bb-run

[![PyPI](https://img.shields.io/pypi/v/bb-run.svg)](https://pypi.org/project/bb-run/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python](https://img.shields.io/badge/python-3.12%2B-blue)](https://pypi.org/project/bb-run/)
[![Test](https://github.com/karlhillx/bb-run/actions/workflows/test.yml/badge.svg)](https://github.com/karlhillx/bb-run/actions/workflows/test.yml)

**Run Bitbucket Pipelines locally.** bb-run reads `bitbucket-pipelines.yml` and runs it in **Docker** or on the **host**, including **parallel** steps, **fail-fast**, **artifacts**, **services**, **caches**, and **after-script**.

## Why bb-run?

- **Test before pushing** - Catch CI failures locally before committing
- **Fast iteration** - No waiting for Bitbucket's pipeline queue
- **Works on uv repos** - Auto-picks a target when there is no `default` pipeline; `--mode auto` (the default) uses Docker if the daemon is up, otherwise host
- **Two modes** - Docker for an environment closer to Bitbucket; host mode needs **no Docker** for script-only steps (service sidecars still need Docker)
- **Parallel steps** - `parallel:` groups run concurrently; group and per-step `fail-fast` stop sibling processes when a failing step demands it
- **Services and caches** - Sidecars (e.g. RabbitMQ) and `definitions.caches` so integration steps can pass locally
- **Clear local output** - Step `1/N` banners, timings, and a one-line pass/fail summary; `bb-run --doctor` checks your machine first
- **Small install** - One runtime dependency: **PyYAML** (see `pyproject.toml`). Docker is only required for `--mode docker` and for steps that declare `services:`

## Installation

### uvx (recommended — zero install)

Works in any checkout that has `bitbucket-pipelines.yml`:

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

- From a subdirectory, `bb-run` (default `--repo .`) **walks up** to the nearest `bitbucket-pipelines.yml`. An explicit `--repo /path` is used as-is and is not walked.
- Prefer **`bb-run --doctor`** then **`bb-run --validate`**; doctor checks Docker, YAML, and the auto target without running scripts. `--mode auto` (the default) uses Docker when `docker info` succeeds, otherwise **host**.
- On macOS/Linux where `pip install` is restricted (PEP 668), prefer **`uvx`**, **`uv tool`**, **`pipx`**, or a venv.

### uv-style pipelines (no `default`)

Many uv + Bitbucket templates only define `pull-requests.**` and `branches.master`, plus `definitions.caches` (`uv`, `pre-commit`) and a RabbitMQ `services:` sidecar.

```bash
cd /path/to/that/repo
uvx bb-run                          # auto target + auto mode
uvx bb-run --mode docker            # require containers (no host fallback)
uvx bb-run --step "Unit tests"      # one named step
uvx bb-run --dry-run --json         # plan only
```

`--target` is chosen from the current git branch when that pipeline exists. `BITBUCKET_BRANCH` is still `LOCAL` unless you pass `--branch`. Integration steps that declare `services:` need a Docker daemon even in host mode. Private git dependencies need credentials available to the step; Docker mode does **not** copy host `GIT_ASKPASS` / `PATH` into the container.

## Quick Start

### Check your machine

```bash
cd /path/to/your/repo   # where bitbucket-pipelines.yml lives
bb-run --doctor
```

`--doctor` reports Python, the pipeline file, Docker (including whether the CLI is missing or the daemon is stopped), the mode bb-run would use, and the auto-selected target. It does not run scripts. `--doctor --json` includes `docker_detail`.

### Validate a pipeline (instant)

```bash
cd /path/to/your/repo   # where bitbucket-pipelines.yml lives
bb-run --validate
bb-run --check          # alias for --validate
```

### Run the resolved pipeline

```bash
bb-run
```

With no `--target`, the CLI picks `branches.<current-git-branch>` when that resolves to steps, otherwise `default`, otherwise `pull-requests.**` (or the first `pull-requests` key), otherwise the first listed target. This auto-select is CLI-only; `HostRunner.run()` / `DockerRunner.run()` still default to `target="default"`.

A typical run looks like this:

```
bb-run 1.3.0

  Repository  /path/to/your/repo
  Target      default  (auto)
  Mode        host  (Docker daemon is not running; using host)
  Branch      LOCAL
  Plan        2 steps

Step 1/2  Unit tests
$ pytest -q
ok  Unit tests  (1.2s)

Step 2/2  Lint
$ ruff check .
ok  Lint  (0.4s)

ok  Pipeline passed  ·  2 steps  ·  1.6s
```

Color and `✓` / `✗` are used on an interactive terminal. `NO_COLOR=1` or `--color never` keeps plain ASCII. `--quiet` hides bb-run banners and keeps step output plus the final summary.

### Run a specific branch

```bash
bb-run --target branches.main
bb-run -t branches.main
```

### Simulate a feature branch

```bash
bb-run --branch feature/my-work
```

`--branch` sets `BITBUCKET_BRANCH` (default `LOCAL`). It does not change target selection; use `--target` for that.

### Tag pipelines

```bash
bb-run --target tags.v1.2.3 --tag v1.2.3
```

### Run on your host (no Docker)

```bash
bb-run --mode host
```

### Pass variables

```bash
bb-run -v ENVIRONMENT=staging -v API_KEY=secret
bb-run --env-file .env
bb-run --env-file .env -v ENVIRONMENT=staging   # -v wins
```

`--env-file` reads dotenv-style `KEY=VALUE` lines (`#` comments and `export ` are allowed). `--verbose` prints extra variable **keys**; values that look like secrets (`API_KEY`, `TOKEN`, `PASSWORD`, …) are shown as `***`.

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
bb-run --no-services --no-cache   # skip sidecars and cache restore/save
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

Uses Docker when `docker info` succeeds; otherwise host. Pass **`--mode docker`** to require containers (fails if the daemon is down) or **`--mode host`** to skip Docker.

### Docker Mode

Runs steps in Docker containers matching Bitbucket's build environment.

```bash
bb-run --mode docker
```

**Pros:** Closer to Bitbucket (image `PATH`, per-step `image:`)  
**Cons:** Requires Docker; images may take time to download

The container does not inherit your host environment. Only Bitbucket variables, `HOME=/root`, `--env-file` / `-v KEY=VALUE`, and (on macOS/Windows) `core.filemode=false` are passed in. That keeps macOS `PATH` / `GIT_ASKPASS` out of the Linux image, and stops Docker Desktop bind-mounts from making every file look executable to pre-commit.

### Host Mode

Runs steps directly on your local machine.

```bash
bb-run --mode host
```

**Pros:** Fast, no image downloads  
**Cons:** May differ from Bitbucket's environment (Python vs Python3, etc.)

Host mode starts from your process environment (then overlays Bitbucket variables and `-v`). `pip` → `pip3` and `--break-system-packages` apply here only.

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

Step `caches:` entries use Bitbucket predefined names (`pip`, `node`, `yarn`, …) plus `definitions.caches` path maps (`uv: ~/.cache/uv`). Snapshots live under **`.bb-run/caches/`** in the repo (gitignored). Host mode uses home-directory caches in place and still snapshots repo-relative paths such as `node_modules`. Docker mode bind-mounts a separate tree at **`.bb-run/caches/docker/`** so tools like pre-commit do not see macOS paths inside the Linux container. Use **`--no-cache`** to skip.

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

`--verbose` prints extra `-v` / `--env-file` keys (secret-looking values redacted) and any `--step` filter. Host mode then prints the full joined script (normally truncated). Docker mode prints the `docker run` argv. Services and caches already print during a normal run.

```bash
bb-run --quiet              # banners off; step output and the final summary stay
bb-run --color never        # no ANSI colors
```

## Configuration

With the default `--repo .`, bb-run uses `bitbucket-pipelines.yml` in the current directory, or walks parents until it finds one. `--repo /path` must already be that directory (no walk-up):

```bash
bb-run --repo /path/to/repo
```

`--json` is only valid with `--list-targets`, `--validate`, `--dry-run`, or `--doctor`.

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
from bbrun import HostRunner, PipelineValidator, find_repo_root, resolve_auto_target

# Walk-up and auto-target are helpers; runners do not call them for you
repo = find_repo_root(".") or "."
validator = PipelineValidator(repo)
if validator.validate():
    validator.show_summary()

config = validator.load() or {}
ok = HostRunner(repo).run(
    target=resolve_auto_target(config, None),
    branch="main",
    variables={"ENVIRONMENT": "staging"},
)
raise SystemExit(0 if ok else 1)
```

`DockerRunner` and `HostRunner` share `BaseRunner` and the same `run(...)` signature (returns `True` on success). Optional kwargs: `tag`, `step_names`, `enable_services`, `enable_caches`, `verbose`, `target_reason`, `mode_reason`.

## Supported vs Unsupported Bitbucket Features

**Supported (today):**

- `default`, `branches.<name>`, `tags.<name>`, `custom.<name>`, and `pull-requests.<pattern>` targets
- Bitbucket-style wildcard target keys (`feature/*`, `release/**`, `v*`, `**`)
- Auto target selection and walk-up to `bitbucket-pipelines.yml` (CLI; or call `resolve_auto_target` / `find_repo_root`)
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

bb-run itself reads:

| Variable | Description |
|----------|-------------|
| `BB_RUN_MODE` | Default `--mode` (`auto`, `docker`, or `host`) |
| `NO_COLOR` | Disable color when `--color auto` |
| `FORCE_COLOR` | Enable color when `--color auto` even if stdout is not a TTY |
| `BB_RUN_DEBUG` | Print a traceback on unexpected errors (same as `--verbose` for crashes) |

bb-run sets these Bitbucket-specific environment variables:

| Variable | Description |
|----------|-------------|
| `CI` | Set to `true` |
| `BITBUCKET_BUILD_NUMBER` | Build number (set to `"1"`) |
| `BITBUCKET_CLONE_DIR` | Repo root on the host; in Docker mode the path **inside** the container (`/opt/atlassian/pipelines/agent/build`) |
| `BITBUCKET_COMMIT` | Git commit SHA (or `local` if unavailable) |
| `BITBUCKET_BRANCH` | From `--branch` (default `LOCAL`, not the current git branch) |
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

`--mode auto` (the default) uses the host when the CLI is missing **or** the daemon is stopped. Start Docker Desktop / OrbStack, then:

```bash
bb-run --mode docker    # require containers; do not fall back to host
bb-run --mode host      # scripts on this machine
```

Steps that declare `services:` still need Docker unless you pass `--no-services`. `bb-run --doctor` prints the specific reason (`docker CLI not found` vs `Docker daemon is not running`).

### "step requires services but Docker is not available"

Start Docker Desktop / the daemon, or skip sidecars with `--no-services` (integration tests that expect RabbitMQ will then fail). `bb-run --doctor` shows whether Docker is reachable.

### `uvx: command not found`

Install [uv](https://docs.astral.sh/uv/) (`curl -LsSf https://astral.sh/uv/install.sh | sh` or `brew install uv`), then retry `uvx bb-run`.

### "pip: command not found"

In **host** mode, bb-run rewrites a leading `pip ` to `pip3 ` when `pip` is missing, and adds `--break-system-packages` on `pip3 install`. Docker mode uses whatever the image provides.

### `pytest: error: unrecognized arguments: --cov=...`

Coverage flags come from the **pytest-cov** plugin. `uv sync` installs the `dev` group (includes pytest-cov):

```bash
uv sync
uv run pytest --cov=bbrun --cov-report=xml tests/
```

### Permission denied under `~/.cache/uv`

Host mode does **not** copy `~/.cache/uv` (or other home-directory caches) in and out of `.bb-run/caches/` — it uses the live host cache as-is. uv marks git pack files read-only, so overlaying that tree used to crash. Repo-relative caches such as `node_modules` are still snapshotted. Use `--no-cache` to skip cache handling entirely.

### `InvalidManifestError` / `.pre-commit-hooks.yaml is not a file` (Docker)

pre-commit’s cache database stores **absolute** clone paths. A snapshot taken on the host (`/Users/…/.cache/pre-commit/…`) is not valid inside the Linux container (`/root/.cache/pre-commit`). bb-run keeps Docker caches under `.bb-run/caches/docker/` and resets a layer whose `db.db` still has host paths. Use `--mode host` if you want the live Mac cache, or `--no-cache` to skip restore.

### Run stayed on the host instead of Docker

`--mode auto` (the default) uses Docker only when `docker info` can reach a daemon. If Docker Desktop or OrbStack is installed but **not running**, bb-run falls back to host. Start the engine, then:

```bash
bb-run --mode docker
```

`--mode docker` fails instead of silently using the host. `bb-run --doctor` shows whether the daemon is reachable.

### `check-executables-have-shebangs` fails in Docker on a Mac

Docker Desktop bind-mounts report every file as executable to `os.access()` even when `ls` shows `644`. pre-commit then wants a shebang on `README.md`, `.py` files, and so on. Host mode is fine because macOS modes are real.

bb-run sets `core.filemode=false` in the container so git uses the index (`100644` vs `100755`), matching Bitbucket. Re-run with `--mode docker`.

### Private git dependencies fail in Docker

Docker mode does not forward host git helpers (`GIT_ASKPASS`, SSH agent extras on `PATH`, and similar). Use `--mode host` so the step sees your existing credentials, or arrange HTTPS/SSH auth inside the image.

### Image pull failures

Registry rate limits or a missing tag may cause image downloads to fail. Try:
1. Waiting and retrying later
2. Using `--mode host` temporarily
3. Updating the pipeline `image:` tag if it is stale
4. Configuring a Docker mirror

### `docker-credential-desktop` / "error getting credentials"

The Docker daemon is up, but `docker pull` cannot run the helper named in `~/.docker/config.json`. This is common on a Mac that used Docker Desktop and now uses OrbStack: `credsStore` is still `"desktop"`.

bb-run retries the pull without stored credentials (enough for public GHCR images). To fix it for good:

```bash
# Option A — run on the host instead of pulling the Bitbucket image
bb-run --mode host

# Option B — stop asking Docker Desktop for credentials (OrbStack)
# Edit ~/.docker/config.json and remove the "credsStore" line, or set it to "".
```

`bb-run --doctor` warns when that helper is configured but not on `PATH`.

## License

MIT License - see [LICENSE](LICENSE) for details.

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md). User-facing changes should be noted in [CHANGELOG.md](CHANGELOG.md). Security reports: [SECURITY.md](SECURITY.md).

## Links

- [PyPI](https://pypi.org/project/bb-run/)
- [GitHub Repository](https://github.com/karlhillx/bb-run)
- [Issue Tracker](https://github.com/karlhillx/bb-run/issues)
