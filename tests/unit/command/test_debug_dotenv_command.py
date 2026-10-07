"""Unit tests for :class:`xtr_dotenv.command.DebugDotenvCommand`."""

from __future__ import annotations

import io
from typing import TYPE_CHECKING, final

import pytest
from xtr_console import ConsoleStyle, ExitCode
from xtr_dependency_injection import KernelInterface, KernelReport

from xtr_dotenv.bundle import DotenvConfig
from xtr_dotenv.command.debug_dotenv_command import DebugDotenvCommand

if TYPE_CHECKING:
    from pathlib import Path

pytestmark = pytest.mark.anyio


@final
class _FakeKernel(KernelInterface):
    def __init__(self, project_dir: Path, environment: str = "dev") -> None:
        self._project_dir = project_dir
        self._environment = environment
        self._report = KernelReport()

    @property
    def name(self) -> str:
        return "test"

    @property
    def environment(self) -> str:
        return self._environment

    @property
    def debug(self) -> bool:
        return False

    @property
    def project_dir(self) -> Path:
        return self._project_dir

    @property
    def bundles(self) -> tuple[str, ...]:
        return ("kernel",)

    @property
    def report(self) -> KernelReport:
        return self._report


def _kernel(project_dir: Path, environment: str = "dev") -> _FakeKernel:
    return _FakeKernel(project_dir, environment)


def _capture() -> tuple[ConsoleStyle, io.StringIO]:
    buffer = io.StringIO()
    return ConsoleStyle(buffer, buffer, width=200, decorated=False), buffer


async def test_debug_lists_cascade_files(tmp_path: Path) -> None:
    base = tmp_path / ".env"
    _ = base.write_text("APP_ENV=dev\nA=1\n", encoding="utf-8")
    style, buffer = _capture()
    kernel = _kernel(tmp_path)
    result = await DebugDotenvCommand()(style, kernel, DotenvConfig(path=".env"))
    assert result == ExitCode.SUCCESS
    output = buffer.getvalue()
    assert str(base) in output
    assert "loaded" in output
    assert "missing" in output


async def test_debug_filters_by_variable_name(tmp_path: Path) -> None:
    base = tmp_path / ".env"
    _ = base.write_text("A=one\nB=two\n", encoding="utf-8")
    style, buffer = _capture()
    kernel = _kernel(tmp_path)
    _ = await DebugDotenvCommand()(
        style, kernel, DotenvConfig(path=".env"), name="A", show_values=True
    )
    output = buffer.getvalue()
    assert "one" in output
    assert "two" not in output


async def test_debug_reports_missing_variable(tmp_path: Path) -> None:
    base = tmp_path / ".env"
    _ = base.write_text("A=one\n", encoding="utf-8")
    style, buffer = _capture()
    kernel = _kernel(tmp_path)
    result = await DebugDotenvCommand()(style, kernel, DotenvConfig(path=".env"), name="NOPE")
    assert result == ExitCode.SUCCESS
    assert "not present" in buffer.getvalue()


async def test_debug_fails_on_bad_file(tmp_path: Path) -> None:
    base = tmp_path / ".env"
    _ = base.write_text("BAD LINE\n", encoding="utf-8")
    style, _buffer = _capture()
    kernel = _kernel(tmp_path)
    result = await DebugDotenvCommand()(style, kernel, DotenvConfig(path=".env"))
    assert result == ExitCode.FAILURE


async def test_debug_lists_the_cascade_of_the_environment_the_files_name(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("APP_ENV", raising=False)
    _ = (tmp_path / ".env").write_text("APP_ENV=staging\n", encoding="utf-8")
    style, buffer = _capture()

    result = await DebugDotenvCommand()(style, _kernel(tmp_path), DotenvConfig(path=".env"))

    assert result == ExitCode.SUCCESS
    assert str(tmp_path / ".env.staging") in buffer.getvalue()
    assert str(tmp_path / ".env.dev") not in buffer.getvalue()


async def test_debug_masks_values_by_default(tmp_path: Path) -> None:
    base = tmp_path / ".env"
    _ = base.write_text("A=supersecret\n", encoding="utf-8")
    style, buffer = _capture()

    result = await DebugDotenvCommand()(style, _kernel(tmp_path), DotenvConfig(path=".env"))

    assert result == ExitCode.SUCCESS
    output = buffer.getvalue()
    assert "supersecret" not in output
    assert "********" in output
    assert "--show-values" in output


async def test_debug_reveals_values_with_show_values(tmp_path: Path) -> None:
    base = tmp_path / ".env"
    _ = base.write_text("A=supersecret\n", encoding="utf-8")
    style, buffer = _capture()

    result = await DebugDotenvCommand()(
        style, _kernel(tmp_path), DotenvConfig(path=".env"), show_values=True
    )

    assert result == ExitCode.SUCCESS
    assert "supersecret" in buffer.getvalue()


async def test_debug_reports_debug_flag_and_production_for_dev(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("APP_ENV", raising=False)
    monkeypatch.delenv("APP_DEBUG", raising=False)
    _ = (tmp_path / ".env").write_text("APP_ENV=dev\n", encoding="utf-8")
    style, buffer = _capture()

    result = await DebugDotenvCommand()(style, _kernel(tmp_path), DotenvConfig(path=".env"))

    assert result == ExitCode.SUCCESS
    output = buffer.getvalue()
    assert "production" in output
    assert "no" in output
    assert "debug (APP_DEBUG)" in output


async def test_debug_reports_production_and_debug_off_for_prod_env(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("APP_ENV", raising=False)
    monkeypatch.delenv("APP_DEBUG", raising=False)
    _ = (tmp_path / ".env").write_text("APP_ENV=prod\n", encoding="utf-8")
    style, buffer = _capture()

    result = await DebugDotenvCommand()(
        style, _kernel(tmp_path, "prod"), DotenvConfig(path=".env"), show_values=True
    )

    assert result == ExitCode.SUCCESS
    rows = buffer.getvalue()
    assert "production" in rows
    assert "yes" in rows
