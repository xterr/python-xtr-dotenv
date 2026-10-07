"""Unit tests for :class:`xtr_dotenv.command.DotenvDumpCommand`."""

from __future__ import annotations

import io
import json
import os
from typing import TYPE_CHECKING, cast, final

import pytest
from xtr_console import ConsoleStyle, ExitCode
from xtr_dependency_injection import KernelInterface, KernelReport

from xtr_dotenv import PathError
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
    # The dump is checked as JSON below.
    payload: object = json.loads(path.read_text(encoding="utf-8"))  # pyright: ignore[reportAny]
    return cast("dict[str, str]", payload)


def _kernel(project_dir: Path, environment: str = "dev") -> _FakeKernel:
    return _FakeKernel(project_dir, environment)


def _style() -> ConsoleStyle:
    buffer = io.StringIO()
    return ConsoleStyle(
        buffer,
        buffer,
        width=100,
        decorated=False,
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


async def test_dump_file_is_created_private(tmp_path: Path) -> None:
    # E3: the dump may carry the .local layers' secrets, so it is 0o600.
    base = tmp_path / ".env"
    _ = base.write_text("A=1\n", encoding="utf-8")
    kernel = _kernel(tmp_path)

    _ = await DotenvDumpCommand()(_style(), kernel, DotenvConfig(path=".env"))

    mode = (tmp_path / ".env.local.json").stat().st_mode & 0o777
    assert oct(mode) == oct(0o600)


async def test_dump_tightens_an_existing_world_readable_file(tmp_path: Path) -> None:
    base = tmp_path / ".env"
    _ = base.write_text("A=1\n", encoding="utf-8")
    dump_path = tmp_path / ".env.local.json"
    _ = dump_path.write_text("{}", encoding="utf-8")
    dump_path.chmod(0o644)
    kernel = _kernel(tmp_path)

    _ = await DotenvDumpCommand()(_style(), kernel, DotenvConfig(path=".env"))

    assert oct(dump_path.stat().st_mode & 0o777) == oct(0o600)


async def test_dump_tightens_the_file_before_writing_the_content(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # An existing wide file must not hold the dump for even an instant.
    _ = (tmp_path / ".env").write_text("A=1\n", encoding="utf-8")
    dump_path = tmp_path / ".env.local.json"
    _ = dump_path.write_text("{}", encoding="utf-8")
    dump_path.chmod(0o644)
    tightened: list[tuple[int, int]] = []
    real_fchmod = os.fchmod

    def spy(descriptor: int, mode: int) -> None:
        tightened.append((mode, os.fstat(descriptor).st_size))
        real_fchmod(descriptor, mode)

    monkeypatch.setattr(os, "fchmod", spy)

    _ = await DotenvDumpCommand()(_style(), _kernel(tmp_path), DotenvConfig(path=".env"))

    assert tightened == [(0o600, 0)]


async def test_dump_refuses_a_symbolic_link_at_its_path(tmp_path: Path) -> None:
    _ = (tmp_path / ".env").write_text("A=1\n", encoding="utf-8")
    target = tmp_path / "elsewhere.json"
    _ = target.write_text("{}", encoding="utf-8")
    (tmp_path / ".env.local.json").symlink_to(target)

    with pytest.raises(PathError):
        _ = await DotenvDumpCommand()(_style(), _kernel(tmp_path), DotenvConfig(path=".env"))

    assert target.read_text(encoding="utf-8") == "{}"
