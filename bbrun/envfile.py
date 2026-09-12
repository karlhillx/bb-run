"""Load ``KEY=VALUE`` files and hide secret-looking values in logs."""

from __future__ import annotations

import re
from collections.abc import Mapping
from pathlib import Path

_ENV_KEY = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_SECRET_TOKENS = frozenset(
    {
        "SECRET",
        "TOKEN",
        "PASSWORD",
        "PASSWD",
        "PASSPHRASE",
        "AUTH",
        "CREDENTIAL",
        "CREDENTIALS",
        "PRIVATE",
    }
)


class EnvFileError(ValueError):
    """Invalid or unreadable env file."""


def parse_env_file(path: Path) -> dict[str, str]:
    """
    Parse a dotenv-style file.

    Supports blank lines, ``#`` comments, optional ``export ``, and
    single- or double-quoted values. Later keys in the same file win.
    """
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise EnvFileError(f"could not read env file {path}: {exc}") from exc

    values: dict[str, str] = {}
    for lineno, raw in enumerate(text.splitlines(), 1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[7:].strip()
        if "=" not in line:
            raise EnvFileError(f"{path}:{lineno}: expected KEY=VALUE")
        key, value = line.split("=", 1)
        key = key.strip()
        if not key or not _ENV_KEY.match(key):
            raise EnvFileError(f"{path}:{lineno}: invalid variable name {key!r}")
        values[key] = _unquote(value.strip())
    return values


def _unquote(value: str) -> str:
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {'"', "'"}:
        return value[1:-1]
    return value


def redact_variables(variables: Mapping[str, str]) -> dict[str, str]:
    """Replace secret-looking values with ``***`` for verbose logs."""
    redacted: dict[str, str] = {}
    for key, value in variables.items():
        redacted[key] = "***" if _looks_secret(key) else value
    return redacted


def _looks_secret(key: str) -> bool:
    upper = key.upper().replace("-", "_")
    if upper in {"KEY", "API_KEY"} or upper.endswith("_KEY"):
        return True
    tokens = set(upper.split("_"))
    if tokens & _SECRET_TOKENS:
        return True
    compact = upper.replace("_", "")
    return "APIKEY" in compact
