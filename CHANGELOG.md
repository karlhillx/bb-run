# Changelog

All notable changes to this project are documented here. This project follows [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- `python -m bbrun` when the `bb-run` entrypoint is not on `PATH`.
- `bbrun/errors.py` with clearer messages for failed step launches and non-zero script exits.
- Parallel groups now list which children failed and print errors when a child process cannot be started.
- Target resolution now supports wildcard branch, tag, and pull-request keys such as `feature/*`, `release/**`, `v*`, and `**`.
- `--dry-run` shows the selected pipeline plan without executing commands; combine with `--json` for automation.
- GitHub issue templates, `SECURITY.md`, `CONTRIBUTING.md`, and `RELEASING.md`.

## [1.0.0] — 2025-03-21

Initial stable release on PyPI: Bitbucket Pipelines YAML runner in Docker or host mode, parallel steps, fail-fast, and artifact modeling.

[Unreleased]: https://github.com/karlhillx/bb-run/compare/v1.0.0...HEAD
[1.0.0]: https://github.com/karlhillx/bb-run/releases/tag/v1.0.0
