"""Unit tests for :class:`xtr_dotenv.DotenvSettingsSource`."""

from __future__ import annotations

import os
from typing import TYPE_CHECKING, ClassVar

import pytest

from xtr_dotenv import DotenvSettings

if TYPE_CHECKING:
    from pathlib import Path


def _write(path: Path, name: str, contents: str) -> Path:
    file = path / name
    _ = file.write_text(contents, encoding="utf-8")
    return file


class _Settings(DotenvSettings):
    """Test-scope model whose cascade path is set per-test via ``_dotenv_path``."""

    _dotenv_path: ClassVar[str] = ""

    database_url: str = "sqlite:///:memory:"
    log_level: str = "INFO"


def _bind(base_path: Path) -> type[_Settings]:
    """Return a subclass of :class:`_Settings` with ``_dotenv_path`` pinned."""

    class Bound(_Settings):
        _dotenv_path: ClassVar[str] = str(base_path)

    return Bound


def test_source_reads_the_cascade(tmp_path: Path) -> None:
    _ = _write(tmp_path, ".env", "database_url=postgres://x\nlog_level=DEBUG\n")
    settings = _bind(tmp_path / ".env")()
    assert settings.database_url == "postgres://x"
    assert settings.log_level == "DEBUG"


def test_source_does_not_mutate_os_environ(tmp_path: Path) -> None:
    _ = _write(tmp_path, ".env", "database_url=postgres://x\n")
    before = os.environ.get("database_url")
    _ = _bind(tmp_path / ".env")()
    after = os.environ.get("database_url")
    assert before == after


def test_real_env_wins_over_cascade(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _ = _write(tmp_path, ".env", "database_url=postgres://from-file\n")
    monkeypatch.setenv("database_url", "postgres://real")
    settings = _bind(tmp_path / ".env")()
    assert settings.database_url == "postgres://real"


def test_init_kwargs_win_over_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _ = _write(tmp_path, ".env", "database_url=postgres://from-file\n")
    monkeypatch.setenv("database_url", "postgres://real")
    settings = _bind(tmp_path / ".env")(database_url="postgres://init")
    assert settings.database_url == "postgres://init"


def test_missing_cascade_falls_back_to_defaults(tmp_path: Path) -> None:
    settings = _bind(tmp_path / "nope")()
    assert settings.database_url == "sqlite:///:memory:"
    assert settings.log_level == "INFO"
