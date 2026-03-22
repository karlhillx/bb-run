# Releasing bb-run

PyPI uploads use **trusted publishing** from GitHub Actions (see [.github/workflows/publish.yml](.github/workflows/publish.yml) and [PyPI: adding a publisher](https://docs.pypi.org/trusted-publishers/adding-a-publisher/)).

## Checklist

1. **Changelog** — Move items from `CHANGELOG.md` **Unreleased** into a dated section for the new version (e.g. `## [1.0.1] — YYYY-MM-DD`).
2. **Version** — Set `version` in `pyproject.toml` to match the tag you will publish.
3. **Commit** — Push to `main` (or your release branch) with the changelog and version bump.
4. **Tag** — Create an annotated tag: `git tag -a v1.0.1 -m "Release 1.0.1"` then `git push origin v1.0.1`.
5. **GitHub Release** — In the repo, **Releases → Draft a new release**, choose the tag, publish. That triggers the **Publish to PyPI** workflow.

Use **workflow_dispatch** on that workflow only if you need a manual retry after fixing PyPI/GitHub configuration.

## Pre-release sanity

- `python -m pytest tests/`
- `ruff check bbrun`
- `python -m bbrun --version` (after `pip install -e .`)
