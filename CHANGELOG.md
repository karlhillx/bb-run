# Changelog

All notable changes to this project are documented here. This project follows [Semantic Versioning](https://semver.org/spec/v2.0.0.html).


## [1.3.0] — 2026-09-12

### Added

- uv-first install: `uvx bb-run` and `uv tool install bb-run`. This repo develops with `uv sync` (PEP 735 `dev` group by default).
- Walk-up discovery of `bitbucket-pipelines.yml` when `--repo` is `.` (or omitted). An explicit `--repo PATH` is used as-is.
- Auto `--target` when omitted: `branches.<git-branch>` if that has steps, then `default`, then `pull-requests.**` (or the first PR key), then the first listed target. `--branch` still defaults to `LOCAL` (`BITBUCKET_BRANCH`).
- `--mode auto` (new default): Docker when `docker info` succeeds, otherwise host. `--mode docker` does not fall back to the host.
- `--step` / `--only` to run named steps; `--tag` for `BITBUCKET_TAG`; `--no-services` and `--no-cache`.
- `after-script` in a new shell with `BITBUCKET_EXIT_CODE`. The step fails if script or after-script fails.
- `definitions.services` sidecars (EXPOSE ports on `127.0.0.1`) in host and Docker modes. The built-in `docker` service is skipped. Parallel groups that declare services run sequentially so ports do not clash.
- `definitions.caches` plus common predefined cache names. Host snapshots live under `.bb-run/caches/`; Docker bind-mounts a separate tree at `.bb-run/caches/docker/`.
- Richer env: `CI`, `BITBUCKET_TAG`, `BITBUCKET_PIPELINE_UUID`, `BITBUCKET_STEP_UUID`, git origin URLs.
- `--dry-run` plan includes scripts, after-script, services, and caches. `--json` is limited to `--list-targets`, `--validate`, `--dry-run`, and `--doctor`.
- Validator summary lists `custom` and `pull-requests` pipelines.
- Library exports: `find_repo_root`, `resolve_auto_target`. Runners still default to `target="default"`.
- Type-check `bbrun` with [ty](https://docs.astral.sh/ty/) (`uv run ty check`) in the `dev` group and CI.
- Reassuring run output: `bb-run` version header, step `1/N` banners, per-step and total timings, and a one-line pass/fail summary.
- `--doctor` (and `--doctor --json`) checks Python, the pipeline file, Docker, git branch, and the auto-selected target without running scripts. JSON includes `docker_detail` (`docker CLI not found`, `Docker daemon is not running`, or `Docker daemon is available`).
- `--env-file PATH` loads dotenv-style `KEY=VALUE` pairs (`-v` wins). Repeatable.
- `--quiet` / `-q` hides bb-run banners; step output and the final summary stay.
- `--color auto|always|never` (default `auto`; honors `NO_COLOR` and `FORCE_COLOR`).
- `--check` as an alias for `--validate`.
- `BB_RUN_MODE` sets the default `--mode`. `BB_RUN_DEBUG` prints a traceback on unexpected errors.

### Changed

- Require Python **3.12+** (`requires-python`, Ruff, ty, and CI). `uvx` still fetches a compatible interpreter when the system Python is older.
- Packaging: Hatchling build backend, PEP 639 `license-files`, and PEP 735 `dependency-groups` (`test` and `dev`; `uv sync` installs `dev` by default).
- Raised floors: PyYAML 6.0.3, pytest 9.1, pytest-cov 7.1, ruff 0.16, ty 0.0.75.
- CI uses `astral-sh/setup-uv@v10.0.1`, `actions/checkout@v6`, `docker/setup-buildx-action@v4`, and tests Python 3.12 / 3.13 / 3.14.
- Docker image is `python:3.12-slim`, installs via uv, and copies the CLI from `docker:28-cli`.
- `--target` no longer defaults to `default`; `--mode` no longer defaults to `docker`.
- `--verbose` prints extra variable keys with secret-looking values redacted, plus (in Docker mode) the `docker run` argv. Host mode prints the full joined script.
- Errors go to stderr. Unexpected exceptions print a short message instead of a traceback unless `--verbose` or `BB_RUN_DEBUG` is set.

### Fixed

- Docker mode no longer copies the host environment into containers (leaked `GIT_ASKPASS`, macOS `PATH`, and other local helpers).
- CLI stdout/stderr are line-buffered so banners are not delayed behind child output when piped.
- Pin `astral-sh/setup-uv` to `v10.0.1`. That action no longer publishes moving major tags, so `@v10` does not resolve.
- Cache and artifact directories under `.bb-run/` are created only when they are used.
- Broken pipes (`bb-run | head`) exit cleanly instead of raising `BrokenPipeError`.
- Ship the `py.typed` marker so type checkers treat `bbrun` as typed.
- Docker CLI calls keep the host PATH (so `docker` and credential helpers can be found). Container variables are passed only as `-e`.
- If `docker pull` fails because `docker-credential-desktop` (or another configured helper) is missing, bb-run retries once with an empty Docker config so public images like GHCR still pull. `--doctor` reports a missing helper.
- Host mode no longer copies snapshots onto live home caches such as `~/.cache/uv`. Overlaying uv's read-only git pack files aborted the pipeline. Those caches are used in place. Repo-relative caches such as `node_modules` are still snapshotted. Permission errors while copying cannot abort the run.
- A Docker `pre-commit` cache whose `db.db` still has host paths is reset (`InvalidManifestError`: `.pre-commit-hooks.yaml is not a file`).
- Auto mode says when the Docker CLI is present but the daemon is stopped, instead of a generic “Docker not available”.
- On macOS/Windows, Docker mode sets `core.filemode=false` in the container so git and pre-commit use the index executable bit. Docker Desktop bind-mounts keep `644` in `stat` but `os.access(X_OK)` as root is true for every file, which made `check-executables-have-shebangs` fail.

## [1.2.0] — 2026-06-09

### Added

- Public, typed library API: `bbrun` now exports `BaseRunner`, `DockerRunner`, `HostRunner`, `PipelineValidator`, and `get_steps_for_target`, with a `py.typed` marker for downstream type checkers.
- Documentation for exit codes and for using bb-run as a Python library.

### Changed

- Introduced a shared `BaseRunner` that consolidates the environment scaffolding, the step loop, parallel-group handling, and result reporting previously duplicated between the Docker and host runners. `DockerRunner` and `HostRunner` now only implement mode-specific behavior.
- Modernized the codebase to Python 3.12 idioms: built-in generics, `X | None` unions, `contextlib.suppress`, and a stricter Ruff lint profile (`E`, `F`, `I`, `UP`, `B`, `C4`, `SIM`).
- Refreshed packaging metadata: richer PyPI classifiers, keywords, a `Changelog` URL, and an SPDX `MIT` license expression.

### Fixed

- Corrected the README "Supported vs Unsupported" matrix, which incorrectly listed parallel steps, artifacts, and wildcard targets as unsupported.

## [1.1.0] — 2026-04-28

### Added

- `python -m bbrun` when the `bb-run` entrypoint is not on `PATH`.
- `bbrun/errors.py` with clearer messages for failed step launches and non-zero script exits.
- Parallel groups now list which children failed and print errors when a child process cannot be started.
- Target resolution now supports wildcard branch, tag, and pull-request keys such as `feature/*`, `release/**`, `v*`, and `**`.
- `--dry-run` shows the selected pipeline plan without executing commands; combine with `--json` for automation.
- GitHub issue templates, `SECURITY.md`, `CONTRIBUTING.md`, and `RELEASING.md`.

## [1.0.0] — 2025-03-21

Initial stable release on PyPI: Bitbucket Pipelines YAML runner in Docker or host mode, parallel steps, fail-fast, and artifact modeling.

[Unreleased]: https://github.com/karlhillx/bb-run/compare/v1.3.0...HEAD
[1.3.0]: https://github.com/karlhillx/bb-run/compare/v1.2.0...v1.3.0
[1.2.0]: https://github.com/karlhillx/bb-run/compare/v1.1.0...v1.2.0
[1.1.0]: https://github.com/karlhillx/bb-run/releases/tag/v1.1.0
