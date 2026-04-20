"""Phase 16 — exception taxonomy + CLI error boundary."""

from __future__ import annotations

from typer.testing import CliRunner

from startup_radar.cli import app
from startup_radar.errors import ConfigError, SourceError, StartupRadarError

runner = CliRunner()


def test_config_error_is_startup_radar_error() -> None:
    """ConfigError inherits from the base and the loader re-export is the same object."""
    from startup_radar.config.loader import ConfigError as LoaderConfigError

    assert issubclass(ConfigError, StartupRadarError)
    assert LoaderConfigError is ConfigError


def test_source_error_message() -> None:
    err = SourceError("boom")
    assert isinstance(err, StartupRadarError)
    assert str(err) == "boom"


def _raise_config_error(**_: object) -> int:
    raise ConfigError("deliberate")


def test_cli_error_boundary_one_line_without_debug(monkeypatch) -> None:
    """`status` propagating a ConfigError → exit 1, single-line 'Error: …', no traceback."""
    monkeypatch.setattr("startup_radar.cli._status", _raise_config_error)
    result = runner.invoke(app, ["status"])
    assert result.exit_code == 1
    assert "Error: deliberate" in result.stderr
    assert "Traceback" not in result.stdout
    assert "Traceback" not in result.stderr


def test_cli_error_boundary_debug_flag_emits_traceback(monkeypatch) -> None:
    """`--debug status` propagating a ConfigError → traceback rendered to stderr."""
    monkeypatch.setattr("startup_radar.cli._status", _raise_config_error)
    result = runner.invoke(app, ["--debug", "status"])
    assert result.exit_code == 1
    assert "Error: deliberate" in result.stderr
    assert "Traceback" in result.stderr
    assert "ConfigError" in result.stderr
