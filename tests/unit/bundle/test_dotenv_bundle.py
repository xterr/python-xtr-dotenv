"""Unit tests for :class:`xtr_dotenv.bundle.DotenvBundle`."""

from __future__ import annotations

import pytest
from xtr_dependency_injection.testing import assert_zero_config

from xtr_dotenv.bundle import DotenvBundle, DotenvConfig

pytestmark = pytest.mark.anyio


async def test_zero_config_boots_and_shuts_down() -> None:
    await assert_zero_config(DotenvBundle)


def test_config_refuses_empty_path() -> None:
    with pytest.raises(ValueError, match="path"):
        _ = DotenvConfig(path="")


def test_config_refuses_empty_env_key() -> None:
    with pytest.raises(ValueError, match="env_key"):
        _ = DotenvConfig(env_key="")


def test_config_refuses_empty_test_envs() -> None:
    with pytest.raises(ValueError, match="test_envs"):
        _ = DotenvConfig(test_envs=())


def test_config_refuses_empty_prod_envs() -> None:
    with pytest.raises(ValueError, match="prod_envs"):
        _ = DotenvConfig(prod_envs=())
