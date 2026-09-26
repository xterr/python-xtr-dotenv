"""Unit tests for :class:`xtr_dotenv.dotenv.Dotenv`."""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

import pytest

from xtr_dotenv import (
    TRACKING_VAR,
    Dotenv,
    FormatError,
    PathError,
    VariableCircularReferenceError,
)

if TYPE_CHECKING:
    from pathlib import Path


def _sandbox() -> dict[str, str]:
    return {}


def _write(path: Path, name: str, contents: str) -> Path:
    file = path / name
    _ = file.write_text(contents, encoding="utf-8")
    return file


# ─────────────────────────────────────────────────────────────
# parse()
# ─────────────────────────────────────────────────────────────


def test_parse_reads_key_value_pairs() -> None:
    result = Dotenv(environ=_sandbox()).parse("A=1\nB=hello\n")
    assert result == {"A": "1", "B": "hello"}


def test_parse_skips_comments_and_blank_lines() -> None:
    result = Dotenv(environ=_sandbox()).parse("# comment\n\nA=1\n")
    assert result == {"A": "1"}


def test_parse_expands_against_parsed_so_far() -> None:
    result = Dotenv(environ=_sandbox()).parse("A=1\nB=$A/x\n")
    assert result == {"A": "1", "B": "1/x"}


def test_parse_expands_against_environ() -> None:
    result = Dotenv(environ={"HOME": "/root"}).parse("PATH=$HOME/bin\n")
    assert result["PATH"] == "/root/bin"


def test_parse_expands_braced_forms() -> None:
    result = Dotenv(environ=_sandbox()).parse("X=${MISSING:-fallback}\nY=${A:-z\\}}\n")
    assert result["X"] == "fallback"
    assert result["Y"] == "z}"


@pytest.mark.parametrize(
    ("line", "reason"),
    [
        ('Y=${A:-"z"}', "unsupported character '\"'"),
        ("Y=${A:-${B:-deep}}", "unsupported character '$'"),
        ("Y=${A", "unclosed braces"),
        ("Y=${A:-x", "unclosed braces"),
    ],
)
def test_parse_refuses_what_it_cannot_expand(line: str, reason: str) -> None:
    with pytest.raises(FormatError, match=re.escape(reason)) as info:
        _ = Dotenv(environ=_sandbox()).parse(f"OK=1\n{line}\n")

    assert info.value.line == 2


def test_an_escaped_or_single_quoted_brace_is_not_an_expansion() -> None:
    result = Dotenv(environ=_sandbox()).parse("A=\\${B\nC='${D'\n")

    assert result == {"A": "${B", "C": "${D"}


def test_parse_treats_single_quoted_values_as_literal() -> None:
    result = Dotenv(environ={"HOME": "/root"}).parse("A='$HOME'\n")
    assert result == {"A": "$HOME"}


def test_parse_escaped_dollar_is_literal() -> None:
    result = Dotenv(environ=_sandbox()).parse(r'PASSWORD="a\$b"' + "\n")
    assert result["PASSWORD"] == "a$b"


def test_parse_raises_format_error_with_line() -> None:
    with pytest.raises(FormatError) as info:
        _ = Dotenv(environ=_sandbox()).parse("A=1\nBADLINE\n")
    error = info.value
    assert error.path == ".env"
    assert error.line == 2
    assert "BADLINE" in error.reason or "missing '='" in error.reason


# ─────────────────────────────────────────────────────────────
# load() / overload() / populate()
# ─────────────────────────────────────────────────────────────


def test_load_writes_into_environ(tmp_path: Path) -> None:
    file = _write(tmp_path, ".env", "A=1\nB=2\n")
    environ: dict[str, str] = {}
    _ = Dotenv(environ=environ).load(str(file))
    assert environ["A"] == "1"
    assert environ["B"] == "2"
    assert "A" in environ["XTR_DOTENV_VARS"]


def test_load_missing_path_raises_path_error(tmp_path: Path) -> None:
    with pytest.raises(PathError) as info:
        _ = Dotenv(environ=_sandbox()).load(str(tmp_path / "nope"))
    assert info.value.path == str(tmp_path / "nope")


def test_load_does_not_override_real_variable(tmp_path: Path) -> None:
    file = _write(tmp_path, ".env", "PORT=5000\n")
    environ = {"PORT": "8080"}
    _ = Dotenv(environ=environ).load(str(file))
    assert environ["PORT"] == "8080"


def test_overload_overrides_real_variable(tmp_path: Path) -> None:
    file = _write(tmp_path, ".env", "PORT=5000\n")
    environ = {"PORT": "8080"}
    _ = Dotenv(environ=environ).overload(str(file))
    assert environ["PORT"] == "5000"


def test_tracked_names_replaced_by_later_load(tmp_path: Path) -> None:
    a = _write(tmp_path, ".env", "X=first\n")
    b = _write(tmp_path, ".env.later", "X=second\n")
    environ: dict[str, str] = {}
    dotenv = Dotenv(environ=environ)
    _ = dotenv.load(str(a))
    _ = dotenv.load(str(b))
    assert environ["X"] == "second"


# ─────────────────────────────────────────────────────────────
# Variable expansion inside load
# ─────────────────────────────────────────────────────────────


def test_load_self_reference_sees_external_default(tmp_path: Path) -> None:
    file = _write(tmp_path, ".env", "A=${A:-x}\n")
    environ: dict[str, str] = {}
    _ = Dotenv(environ=environ).load(str(file))
    assert environ["A"] == "x"


def test_load_self_reference_sees_environ_value(tmp_path: Path) -> None:
    file = _write(tmp_path, ".env", "A=${A:-x}\n")
    environ = {"A": "outer"}
    _ = Dotenv(environ=environ).overload(str(file))
    # Overload replaces the real value, but the self-reference on the RHS
    # still saw the real environ value first.
    assert environ["A"] == "outer"


def test_circular_reference_raises(tmp_path: Path) -> None:
    file = _write(tmp_path, ".env", "A=$B\nB=$A\n")
    with pytest.raises(VariableCircularReferenceError) as info:
        _ = Dotenv(environ=_sandbox()).load(str(file))
    assert set(info.value.names) == {"A", "B"}


# ─────────────────────────────────────────────────────────────
# load_env cascade
# ─────────────────────────────────────────────────────────────


def test_cascade_uses_dist_when_base_missing(tmp_path: Path) -> None:
    _ = _write(tmp_path, ".env.dist", "X=fromdist\n")
    environ: dict[str, str] = {}
    _ = Dotenv(environ=environ).load_env(str(tmp_path / ".env"))
    assert environ["X"] == "fromdist"


def test_cascade_uses_default_env_when_key_unset(tmp_path: Path) -> None:
    _ = _write(tmp_path, ".env", "X=base\n")
    environ: dict[str, str] = {}
    _ = Dotenv(environ=environ).load_env(str(tmp_path / ".env"), default_env="staging")
    assert environ["APP_ENV"] == "staging"


def test_cascade_env_from_env_file(tmp_path: Path) -> None:
    _ = _write(tmp_path, ".env", "APP_ENV=prod\n")
    environ: dict[str, str] = {}
    _ = Dotenv(environ=environ).load_env(str(tmp_path / ".env"))
    assert environ["APP_ENV"] == "prod"


def test_cascade_skips_local_in_test_env(tmp_path: Path) -> None:
    _ = _write(tmp_path, ".env", "APP_ENV=test\nX=base\n")
    _ = _write(tmp_path, ".env.local", "X=frombad\n")
    environ: dict[str, str] = {}
    _ = Dotenv(environ=environ).load_env(str(tmp_path / ".env"))
    assert environ["X"] == "base"


def test_cascade_local_env_stops_before_env_specific(tmp_path: Path) -> None:
    _ = _write(tmp_path, ".env", "APP_ENV=local\nX=base\n")
    _ = _write(tmp_path, ".env.local", "X=fromlocal\n")
    _ = _write(tmp_path, ".env.local.local", "X=wrong\n")
    environ: dict[str, str] = {}
    _ = Dotenv(environ=environ).load_env(str(tmp_path / ".env"))
    assert environ["X"] == "fromlocal"


def test_cascade_loads_env_specific_and_env_local(tmp_path: Path) -> None:
    _ = _write(tmp_path, ".env", "APP_ENV=dev\nX=base\n")
    _ = _write(tmp_path, ".env.dev", "X=fromdev\n")
    _ = _write(tmp_path, ".env.dev.local", "X=fromdevlocal\n")
    environ: dict[str, str] = {}
    _ = Dotenv(environ=environ).load_env(str(tmp_path / ".env"))
    assert environ["X"] == "fromdevlocal"


def test_cascade_records_path_variable(tmp_path: Path) -> None:
    _ = _write(tmp_path, ".env", "X=1\n")
    base = str(tmp_path / ".env")
    environ: dict[str, str] = {}
    _ = Dotenv(environ=environ).load_env(base)
    assert environ["XTR_DOTENV_PATH"] == base


def test_cascade_real_env_wins_over_files(tmp_path: Path) -> None:
    _ = _write(tmp_path, ".env", "X=frombase\n")
    _ = _write(tmp_path, ".env.dev", "X=fromdev\n")
    environ = {"X": "real"}
    _ = Dotenv(environ=environ).load_env(str(tmp_path / ".env"))
    assert environ["X"] == "real"


# ─────────────────────────────────────────────────────────────
# boot_env
# ─────────────────────────────────────────────────────────────


def test_boot_env_reads_dump_when_available(tmp_path: Path) -> None:
    _ = _write(tmp_path, ".env", "APP_ENV=prod\nX=fromfile\n")
    _ = _write(tmp_path, ".env.local.json", '{"APP_ENV": "prod", "X": "fromdump"}')
    environ: dict[str, str] = {}
    _ = Dotenv(environ=environ).boot_env(str(tmp_path / ".env"))
    assert environ["X"] == "fromdump"
    assert environ["APP_ENV"] == "prod"


def test_boot_env_falls_back_when_dump_env_mismatches(tmp_path: Path) -> None:
    _ = _write(tmp_path, ".env", "APP_ENV=dev\nX=fromfile\n")
    _ = _write(tmp_path, ".env.local.json", '{"APP_ENV": "prod", "X": "fromdump"}')
    environ = {"APP_ENV": "dev"}
    _ = Dotenv(environ=environ).boot_env(str(tmp_path / ".env"))
    assert environ["X"] == "fromfile"


def test_boot_env_normalises_debug_true_for_dev(tmp_path: Path) -> None:
    _ = _write(tmp_path, ".env", "APP_ENV=dev\n")
    environ: dict[str, str] = {}
    _ = Dotenv(environ=environ).boot_env(str(tmp_path / ".env"))
    assert environ["APP_DEBUG"] == "1"


def test_boot_env_normalises_debug_false_for_prod(tmp_path: Path) -> None:
    _ = _write(tmp_path, ".env", "APP_ENV=prod\n")
    environ: dict[str, str] = {}
    _ = Dotenv(environ=environ).boot_env(str(tmp_path / ".env"))
    assert environ["APP_DEBUG"] == "0"


def test_boot_env_respects_existing_debug_value(tmp_path: Path) -> None:
    _ = _write(tmp_path, ".env", "APP_ENV=prod\nAPP_DEBUG=yes\n")
    environ: dict[str, str] = {}
    _ = Dotenv(environ=environ).boot_env(str(tmp_path / ".env"))
    assert environ["APP_DEBUG"] == "1"


def test_set_prod_envs_shifts_debug_default(tmp_path: Path) -> None:
    _ = _write(tmp_path, ".env", "APP_ENV=staging\n")
    environ: dict[str, str] = {}
    _ = Dotenv(environ=environ).set_prod_envs(("staging", "prod")).boot_env(str(tmp_path / ".env"))
    assert environ["APP_DEBUG"] == "0"


def test_a_value_may_reference_one_a_later_file_defines(tmp_path: Path) -> None:
    base = _write(tmp_path, ".env", "URL=http://${HOST}/api\nHOST=placeholder\n")
    _ = _write(tmp_path, ".env.local", "HOST=db.local\n")
    environ = _sandbox()

    _ = Dotenv(environ=environ).load_env(str(base))

    assert environ["URL"] == "http://db.local/api"


def test_a_real_variable_wins_inside_an_expansion_too(tmp_path: Path) -> None:
    base = _write(tmp_path, ".env", "HOST=from-file\nURL=http://${HOST}\n")
    environ = {"HOST": "from-env"}

    _ = Dotenv(environ=environ).load(str(base))

    assert environ["HOST"] == "from-env"
    assert environ["URL"] == "http://from-env"


def test_an_assigning_default_defines_the_variable(tmp_path: Path) -> None:
    base = _write(tmp_path, ".env", "A=${B:=fallback}\n")
    environ = _sandbox()

    _ = Dotenv(environ=environ).load(str(base))

    assert (environ["A"], environ["B"]) == ("fallback", "fallback")


def test_the_defaulted_environment_is_tracked_as_loaded(tmp_path: Path) -> None:
    base = _write(tmp_path, ".env", "X=1\n")
    environ = _sandbox()

    _ = Dotenv(environ=environ).load_env(str(base), default_env="staging")

    assert environ["APP_ENV"] == "staging"
    assert "APP_ENV" in environ[TRACKING_VAR].split(",")


@pytest.mark.parametrize(("raw", "expected"), [("maybe", "0"), ("2", "1"), ("off", "0")])
def test_boot_env_reads_the_debug_flag_as_a_flag(tmp_path: Path, raw: str, expected: str) -> None:
    base = _write(tmp_path, ".env", "X=1\n")
    environ = {"APP_DEBUG": raw}

    _ = Dotenv(environ=environ).boot_env(str(base))

    assert environ["APP_DEBUG"] == expected
