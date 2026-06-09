# Changelog

All notable changes to this project are documented here. This project follows [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

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

[Unreleased]: https://github.com/karlhillx/bb-run/compare/v1.2.0...HEAD
[1.2.0]: https://github.com/karlhillx/bb-run/compare/v1.1.0...v1.2.0
[1.1.0]: https://github.com/karlhillx/bb-run/releases/tag/v1.1.0
