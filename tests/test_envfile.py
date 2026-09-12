"""Tests for dotenv-style env files and secret redaction."""

from pathlib import Path

import pytest

from bbrun.envfile import EnvFileError, parse_env_file, redact_variables


def test_parse_env_file_comments_export_and_quotes(tmp_path: Path):
    path = tmp_path / ".env"
    path.write_text(
        "# comment\n"
        "export ENVIRONMENT=staging\n"
        "API_KEY='secret value'\n"
        'GREETING="hello world"\n'
        "\n"
        "EMPTY=\n",
        encoding="utf-8",
    )
    values = parse_env_file(path)
    assert values["ENVIRONMENT"] == "staging"
    assert values["API_KEY"] == "secret value"
    assert values["GREETING"] == "hello world"
    assert values["EMPTY"] == ""


def test_parse_env_file_rejects_bad_line(tmp_path: Path):
    path = tmp_path / ".env"
    path.write_text("NOT_A_VALUE\n", encoding="utf-8")
    with pytest.raises(EnvFileError, match="KEY=VALUE"):
        parse_env_file(path)


def test_parse_env_file_missing(tmp_path: Path):
    with pytest.raises(EnvFileError, match="could not read"):
        parse_env_file(tmp_path / "missing.env")


def test_redact_variables_masks_secrets():
    shown = redact_variables(
        {
            "ENVIRONMENT": "staging",
            "API_KEY": "abc123",
            "TOKEN": "tok",
            "BITBUCKET_TOKEN": "tok",
            "DB_PASSWORD": "p",
        }
    )
    assert shown["ENVIRONMENT"] == "staging"
    assert shown["API_KEY"] == "***"
    assert shown["TOKEN"] == "***"
    assert shown["BITBUCKET_TOKEN"] == "***"
    assert shown["DB_PASSWORD"] == "***"
