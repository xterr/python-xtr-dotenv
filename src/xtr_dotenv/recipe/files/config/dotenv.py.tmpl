"""One description of the dotenv cascade: entry points and commands both read it.

``DOTENV`` is the single source of truth. ``kernel.py`` boots the environment from it
before the kernel builds, and ``dotenv:dump`` and ``debug:dotenv`` read the same object
from the container. Change the cascade here, and nowhere else.
"""

from __future__ import annotations

from typing import Final

from xtr_dependency_injection import configure
from xtr_dotenv.bundle import DotenvConfig

__all__ = ["DOTENV", "dotenv"]

DOTENV: Final = DotenvConfig(
    path="%kernel.project_dir%/.env",
    env_key="APP_ENV",
    debug_key="APP_DEBUG",
    default_env="dev",
    test_envs=("test",),
    prod_envs=("prod",),
    debug_envs=("dev", "local", "test"),
)


@configure
def dotenv() -> DotenvConfig:
    """Hand the container the one cascade description."""
    return DOTENV
