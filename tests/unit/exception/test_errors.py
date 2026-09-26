"""Unit tests for the typed attribute contracts of every error."""

from __future__ import annotations

from xtr_dotenv import (
    DotenvError,
    FormatError,
    PathError,
    VariableCircularReferenceError,
)


def test_format_error_carries_path_line_reason() -> None:
    error = FormatError("/etc/app/.env", 42, "bad thing")
    assert error.path == "/etc/app/.env"
    assert error.line == 42
    assert error.reason == "bad thing"
    assert str(error) == "/etc/app/.env:42: bad thing"
    assert isinstance(error, DotenvError)
    assert isinstance(error, ValueError)


def test_path_error_carries_path() -> None:
    error = PathError("/nope")
    assert error.path == "/nope"
    assert "'/nope'" in str(error)
    assert isinstance(error, DotenvError)
    assert isinstance(error, OSError)


def test_variable_circular_reference_error_carries_names() -> None:
    error = VariableCircularReferenceError(("A", "B"))
    assert error.names == ("A", "B")
    assert "A" in str(error)
    assert "B" in str(error)
    assert isinstance(error, DotenvError)
    assert isinstance(error, ValueError)
