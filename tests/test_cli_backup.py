"""Tests for `startup-radar backup`. Uses Typer's CliRunner against a tmp_path repo."""

from __future__ import annotations

import tarfile
from pathlib import Path

import pytest
from typer.testing import CliRunner

from startup_radar.cli import app

runner = CliRunner()


def test_backup_default_writes_tarball(fake_repo: Path) -> None:
    """Default path: `backup` writes into backups/ under the (monkeypatched) repo root."""
    result = runner.invoke(app, ["backup", "--no-secrets"])
    assert result.exit_code == 0, result.output
    tarballs = list((fake_repo / "backups").glob("startup-radar-*.tar.gz"))
    assert len(tarballs) == 1
    with tarfile.open(tarballs[0]) as tar:
        names = set(tar.getnames())
    assert "startup_radar.db" in names
    assert "config.yaml" in names
    assert "token.json" not in names
    assert "credentials.json" not in names


def test_backup_db_only(fake_repo: Path) -> None:
    out = fake_repo / "custom" / "db.tar.gz"
    result = runner.invoke(app, ["backup", "-o", str(out), "--db-only"])
    assert result.exit_code == 0, result.output
    with tarfile.open(out) as tar:
        names = set(tar.getnames())
    assert names == {"startup_radar.db"}


def test_backup_db_only_missing_db_fails(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Without the fake_repo fixture there's no DB — --db-only should exit 1."""
    monkeypatch.setattr("startup_radar.cli._repo_root", lambda: tmp_path)
    monkeypatch.setattr("startup_radar.config.loader.CONFIG_FILE", tmp_path / "config.yaml")
    out = tmp_path / "backups" / "x.tar.gz"
    result = runner.invoke(app, ["backup", "-o", str(out), "--db-only"])
    assert result.exit_code == 1
    assert "DB not found" in result.output or "Nothing to back up" in result.output
