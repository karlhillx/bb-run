"""Tests for user-facing error helpers."""

from bbrun.errors import explain_process_launch_error


def test_explain_docker_missing():
    exc = FileNotFoundError(2, "No such file or directory", "docker")
    msg = explain_process_launch_error(exc)
    assert "docker" in msg.lower()
    assert "path" in msg.lower() or "host" in msg.lower()


def test_explain_missing_repo_path():
    exc = FileNotFoundError(2, "No such file", "/repo/.venv/bin/python3")
    msg = explain_process_launch_error(exc)
    assert ".venv/bin/python3" in msg or "python3" in msg
    assert "earlier command" in msg


def test_explain_permission():
    exc = PermissionError(13, "Permission denied", "/x/foo")
    msg = explain_process_launch_error(exc)
    assert "permission" in msg.lower()


def test_explain_generic_oserror():
    exc = OSError(12, "Cannot allocate memory")
    msg = explain_process_launch_error(exc)
    assert "could not start process" in msg.lower()


def test_explain_runtime():
    msg = explain_process_launch_error(RuntimeError("docker pull failed: x"))
    assert "docker pull failed" in msg
