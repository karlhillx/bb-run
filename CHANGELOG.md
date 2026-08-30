# Changelog

All notable changes to this project are documented here. This project follows [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Fixed

- Pin `astral-sh/setup-uv` to `v10.0.1`. That action no longer publishes moving major tags, so `@v10` does not resolve.

## [1.3.0] — 2026-08-30

### Added

- uv-first install: `uvx bb-run` and `uv tool install bb-run`. This repo develops with `uv sync` (PEP 735 `dev` group by default).
- Walk-up discovery of `bitbucket-pipelines.yml` when `--repo` is `.` (or omitted). An explicit `--repo PATH` is used as-is.
- Auto `--target` when omitted: `branches.<git-branch>` if that has steps, then `default`, then `pull-requests.**` (or the first PR key), then the first listed target. `--branch` still defaults to `LOCAL` (`BITBUCKET_BRANCH`).
- `--mode auto` (new default): Docker when `docker info` succeeds, otherwise host.
- `--step` / `--only` to run named steps; `--tag` for `BITBUCKET_TAG`; `--no-services` and `--no-cache`.
- `after-script` in a new shell with `BITBUCKET_EXIT_CODE`. The step fails if script or after-script fails.
- `definitions.services` sidecars (EXPOSE ports on `127.0.0.1`) in host and Docker modes. The built-in `docker` service is skipped. Parallel groups that declare services run sequentially so ports do not clash.
- `definitions.caches` plus common predefined cache names, stored under `.bb-run/caches/`.
- Richer env: `CI`, `BITBUCKET_TAG`, `BITBUCKET_PIPELINE_UUID`, `BITBUCKET_STEP_UUID`, git origin URLs.
- `--dry-run` plan includes scripts, after-script, services, and caches. `--json` is limited to `--list-targets`, `--validate`, and `--dry-run`.
- Validator summary lists `custom` and `pull-requests` pipelines.
- Library exports: `find_repo_root`, `resolve_auto_target`. Runners still default to `target="default"`.
- Type-check `bbrun` with [ty](https://docs.astral.sh/ty/) (`uv run ty check`) in the `dev` group and CI.

### Changed

- Require Python **3.12+** (`requires-python`, Ruff, ty, and CI). `uvx` still fetches a compatible interpreter when the system Python is older.
- Packaging: Hatchling build backend, PEP 639 `license-files`, and PEP 735 `dependency-groups` (`test` and `dev`; `uv sync` installs `dev` by default).
- Raised floors: PyYAML 6.0.3, pytest 9.1, pytest-cov 7.1, ruff 0.16, ty 0.0.75.
- CI uses `astral-sh/setup-uv@v10`, `actions/checkout@v6`, `docker/setup-buildx-action@v4`, and tests Python 3.12 / 3.13 / 3.14.
- Docker image is `python:3.12-slim`, installs via uv, and copies the CLI from `docker:28-cli`.
- `--target` no longer defaults to `default`; `--mode` no longer defaults to `docker`.
- `--verbose` prints the resolved target, branch, tag, extra `-v` values, step filter, and (in Docker mode) the `docker run` argv. Host mode prints the full joined script.

### Fixed

- Docker mode no longer copies the host environment into containers (leaked `GIT_ASKPASS`, macOS `PATH`, and other local helpers).
- CLI stdout/stderr are line-buffered so banners are not delayed behind child output when piped.

## [1.2.0] — 2026-06-09

### Added

- Public, typed library API: `bbrun` now exports `BaseRunner`, `DockerRunner`, `HostRunner`, `PipelineValidator`, and `get_steps_for_target`, with a `py.typed` marker for downstream type checkers.
- Documentation for exit codes and for using bb-run as a Python library.

### Changed

- Introduced a shared `BaseRunner` that consolidates the environment scaffolding, step loop, parallel-group handling, and result reporting previously duplicated between the Docker and host runners. `DockerRunner` and `HostRunner` now only implement mode-specific behavior.
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
