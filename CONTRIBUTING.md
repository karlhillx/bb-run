# Contributing

Thanks for helping improve bb-run.

## Development setup

```bash
git clone https://github.com/karlhillx/bb-run.git
cd bb-run
python3.12 -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -e ".[dev]"
```

## Checks before a PR

```bash
python -m pytest tests/
ruff check bbrun
```

Optional coverage (requires `dev` / `test` extra):

```bash
python -m pytest --cov=bbrun --cov-report=term-missing tests/
```

## Releases

Maintainers: follow [RELEASING.md](RELEASING.md) and keep [CHANGELOG.md](CHANGELOG.md) in sync with user-visible changes.

## Security

See [SECURITY.md](SECURITY.md) for how to report vulnerabilities.
