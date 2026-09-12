"""Tests for terminal output helpers."""

from bbrun.ui import Ui, format_duration, resolve_color


def test_format_duration_buckets():
    assert format_duration(0.04) == "<0.1s"
    assert format_duration(1.23) == "1.2s"
    assert format_duration(12.4) == "12s"
    assert format_duration(65) == "1m 05s"
    assert format_duration(3661) == "1h 01m"


def test_ascii_symbols_when_unicode_off():
    ui = Ui(color=False, quiet=False, unicode=False)
    assert ui.ok == "ok"
    assert ui.fail == "fail"
    assert ui.sep == "-"


def test_unicode_symbols_when_enabled():
    ui = Ui(color=False, quiet=False, unicode=True)
    assert ui.ok == "✓"
    assert ui.fail == "✗"


def test_quiet_hides_info_but_not_errors(capsys):
    ui = Ui(color=False, quiet=True, unicode=False)
    ui.info("hidden")
    ui.error("shown")
    captured = capsys.readouterr()
    assert "hidden" not in captured.out
    assert "shown" in captured.err


def test_resolve_color_never_and_always(monkeypatch):
    monkeypatch.delenv("NO_COLOR", raising=False)
    monkeypatch.delenv("FORCE_COLOR", raising=False)
    assert resolve_color("never") is False
    assert resolve_color("always") is True


def test_resolve_color_respects_no_color(monkeypatch):
    monkeypatch.setenv("NO_COLOR", "1")
    monkeypatch.delenv("FORCE_COLOR", raising=False)
    assert resolve_color("auto") is False
