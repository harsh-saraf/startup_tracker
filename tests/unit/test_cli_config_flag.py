"""Tests for the top-level ``--config`` flag (Phase 14)."""

from __future__ import annotations

from pathlib import Path

from typer.testing import CliRunner

from startup_radar.cli import app
from startup_radar.config.loader import load_config

runner = CliRunner()


def _write_minimal_config(path: Path) -> None:
    """Write a tmp config.yaml based on the repo's config.example.yaml."""
    example = Path(__file__).resolve().parents[2] / "config.example.yaml"
    path.write_text(example.read_text(encoding="utf-8"))


def test_config_flag_is_used_by_status(tmp_path: Path, monkeypatch) -> None:
    """`startup-radar --config <tmp> status` reads from the tmp path, not the package default."""
    cfg = tmp_path / "custom.yaml"
    _write_minimal_config(cfg)
    db = tmp_path / "sr.db"

    import yaml

    data = yaml.safe_load(cfg.read_text())
    data["output"]["sqlite"]["path"] = str(db)
    cfg.write_text(yaml.safe_dump(data))

    monkeypatch.setattr("startup_radar.cli._repo_root", lambda: tmp_path)
    monkeypatch.setattr("startup_radar.config.loader.CONFIG_FILE", tmp_path / "absent.yaml")

    result = runner.invoke(app, ["--config", str(cfg), "status"])
    assert result.exit_code == 0, result.output
    assert "Branch:" in result.output


def test_config_flag_missing_file_fails(tmp_path: Path) -> None:
    """Typer's ``exists=True`` rejects a non-existent --config path."""
    result = runner.invoke(app, ["--config", str(tmp_path / "nope.yaml"), "status"])
    assert result.exit_code != 0


def test_serve_handoff_env_picked_up_by_loader(tmp_path: Path, monkeypatch) -> None:
    """``STARTUP_RADAR_CONFIG_PATH`` env var is honoured by ``load_config()`` when no
    explicit path is passed. Scoped hand-off for serve→Streamlit subprocess."""
    cfg = tmp_path / "from_env.yaml"
    _write_minimal_config(cfg)

    monkeypatch.setattr("startup_radar.config.loader.CONFIG_FILE", tmp_path / "absent.yaml")
    monkeypatch.setenv("STARTUP_RADAR_CONFIG_PATH", str(cfg))

    loaded = load_config()
    assert loaded is not None


def test_loader_ignores_env_when_explicit_path_given(tmp_path: Path, monkeypatch) -> None:
    """Explicit ``path=`` wins over the serve hand-off env var."""
    explicit = tmp_path / "explicit.yaml"
    _write_minimal_config(explicit)

    monkeypatch.setenv("STARTUP_RADAR_CONFIG_PATH", str(tmp_path / "env.yaml"))

    loaded = load_config(path=explicit)
    assert loaded is not None
