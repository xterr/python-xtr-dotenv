"""Unit tests for :class:`xtr_dotenv.bundle.DotenvBundle`."""

from __future__ import annotations

from pathlib import Path

import pytest
from xtr_dependency_injection.testing import assert_zero_config

from xtr_dotenv import DotenvError, InvalidArgumentError
from xtr_dotenv.bundle import DotenvBundle, DotenvConfig

pytestmark = pytest.mark.anyio


async def test_zero_config_boots_and_shuts_down() -> None:
    await assert_zero_config(DotenvBundle)


def test_config_refuses_empty_path() -> None:
    with pytest.raises(InvalidArgumentError, match="path"):
        _ = DotenvConfig(path="")


def test_config_refuses_empty_env_key() -> None:
    with pytest.raises(InvalidArgumentError, match="env_key"):
        _ = DotenvConfig(env_key="")


def test_config_refuses_empty_test_envs() -> None:
    with pytest.raises(InvalidArgumentError, match="test_envs"):
        _ = DotenvConfig(test_envs=())


def test_config_refuses_empty_prod_envs() -> None:
    with pytest.raises(InvalidArgumentError, match="prod_envs"):
        _ = DotenvConfig(prod_envs=())


def test_config_refuses_empty_default_env() -> None:
    with pytest.raises(InvalidArgumentError, match="default_env"):
        _ = DotenvConfig(default_env="")


def test_config_refuses_empty_debug_envs() -> None:
    with pytest.raises(InvalidArgumentError, match="debug_envs"):
        _ = DotenvConfig(debug_envs=())


def test_a_refused_config_value_is_a_dotenv_error_and_a_value_error() -> None:
    with pytest.raises(InvalidArgumentError) as raised:
        _ = DotenvConfig(env_key="")

    assert isinstance(raised.value, DotenvError)
    assert isinstance(raised.value, ValueError)


def test_base_path_substitutes_the_project_dir_token(tmp_path: Path) -> None:
    assert DotenvConfig(path="%kernel.project_dir%/.env").base_path(tmp_path) == tmp_path / ".env"


def test_base_path_takes_a_relative_path_from_the_project_dir(tmp_path: Path) -> None:
    assert DotenvConfig(path=".env").base_path(tmp_path) == tmp_path / ".env"


def test_base_path_passes_an_absolute_path_through(tmp_path: Path) -> None:
    assert DotenvConfig(path="/srv/app/.env").base_path(tmp_path) == Path("/srv/app/.env")


def test_base_path_refuses_a_parameter_only_the_kernel_can_resolve(tmp_path: Path) -> None:
    config = DotenvConfig(path="%env(DATABASE_URL)%/.env")

    with pytest.raises(InvalidArgumentError, match="container parameter"):
        _ = config.base_path(tmp_path)


def test_loader_builds_the_loader_the_description_names() -> None:
    loader = DotenvConfig(env_key="APP_ENV", debug_key="APP_DEBUG").loader()

    assert (loader.env_key, loader.debug_key) == ("APP_ENV", "APP_DEBUG")


def test_boot_round_trips_the_description_through_the_loader(tmp_path: Path) -> None:
    _ = (tmp_path / ".env").write_text("APP_ENV=prod\nX=1\n", encoding="utf-8")
    sandbox: dict[str, str] = {}

    _ = DotenvConfig(path=str(tmp_path / ".env")).boot(tmp_path, environ=sandbox)

    assert (sandbox["APP_ENV"], sandbox["X"], sandbox["APP_DEBUG"]) == ("prod", "1", "0")


def test_boot_resolves_the_project_dir_token(tmp_path: Path) -> None:
    _ = (tmp_path / ".env").write_text("APP_ENV=dev\nX=1\n", encoding="utf-8")
    sandbox: dict[str, str] = {}

    _ = DotenvConfig(path="%kernel.project_dir%/.env").boot(tmp_path, environ=sandbox)

    assert sandbox["X"] == "1"
