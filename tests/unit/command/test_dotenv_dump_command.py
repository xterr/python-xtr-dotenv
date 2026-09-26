"""Unit tests for :class:`xtr_dotenv.command.DotenvDumpCommand`."""

from __future__ import annotations

import io
import json
from typing import TYPE_CHECKING, cast, final

import pytest
from rich.console import Console
from xtr_console import ConsoleStyle, ExitCode
from xtr_dependency_injection import KernelInterface, KernelReport

from xtr_dotenv.bundle import DotenvConfig
from xtr_dotenv.command.dotenv_dump_command import DotenvDumpCommand

if TYPE_CHECKING:
    from pathlib import Path

pytestmark = pytest.mark.anyio


@final
class _FakeKernel(KernelInterface):
    """Full :class:`KernelInterface` stand-in; the command reads two fields."""

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


def _load_dump(path: Path) -> dict[str, str]:
    payload: object = json.loads(path.read_text(encoding="utf-8"))  # pyright: ignore[reportAny]
    return cast("dict[str, str]", payload)


def _kernel(project_dir: Path, environment: str = "dev") -> _FakeKernel:
    return _FakeKernel(project_dir, environment)


def _style() -> ConsoleStyle:
    buffer = io.StringIO()
    return ConsoleStyle(
        console=Console(file=buffer, width=100, no_color=True, force_terminal=False),
        error_console=Console(file=buffer, width=100, no_color=True, force_terminal=False),
    )


async def test_dump_writes_the_compiled_cascade(tmp_path: Path) -> None:
    base = tmp_path / ".env"
    _ = base.write_text("APP_ENV=dev\nA=1\nB=$A/x\n", encoding="utf-8")
    kernel = _kernel(tmp_path)
    result = await DotenvDumpCommand()(_style(), kernel, DotenvConfig(path=".env"))
    assert result == ExitCode.SUCCESS
    dump = _load_dump(tmp_path / ".env.local.json")
    assert dump["A"] == "1"
    assert dump["B"] == "1/x"
    assert dump["APP_ENV"] == "dev"


async def test_dump_omits_bookkeeping_variables(tmp_path: Path) -> None:
    base = tmp_path / ".env"
    _ = base.write_text("A=1\n", encoding="utf-8")
    kernel = _kernel(tmp_path)
    _ = await DotenvDumpCommand()(_style(), kernel, DotenvConfig(path=".env"))
    dump = _load_dump(tmp_path / ".env.local.json")
    assert "XTR_DOTENV_VARS" not in dump
    assert "XTR_DOTENV_PATH" not in dump


async def test_dump_reports_failure_on_bad_file(tmp_path: Path) -> None:
    base = tmp_path / ".env"
    _ = base.write_text("BAD LINE\n", encoding="utf-8")
    kernel = _kernel(tmp_path)
    result = await DotenvDumpCommand()(_style(), kernel, DotenvConfig(path=".env"))
    assert result == ExitCode.FAILURE


async def test_dump_uses_explicit_env_argument(tmp_path: Path) -> None:
    base = tmp_path / ".env"
    _ = base.write_text("APP_ENV=dev\nX=base\n", encoding="utf-8")
    _ = (tmp_path / ".env.prod").write_text("X=fromprod\n", encoding="utf-8")
    kernel = _kernel(tmp_path, "dev")
    _ = await DotenvDumpCommand()(_style(), kernel, DotenvConfig(path=".env"), env="prod")
    dump = _load_dump(tmp_path / ".env.local.json")
    assert dump["X"] == "fromprod"
