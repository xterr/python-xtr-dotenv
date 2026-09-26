"""A :class:`~pydantic_settings.BaseSettings` base wired to the dotenv cascade.

A subclass declares the cascade options as ``ClassVar`` attributes, so the
model's runtime shape stays purely field-driven and pydantic-settings does
not warn about unknown config keys. Source priority is:

1. init keyword arguments
2. real environment variables
3. the dotenv cascade
4. secret files
5. field defaults

which matches the guarantee that a real environment variable always wins
over a file, and a caller-supplied value wins over both.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, ClassVar, cast

from pydantic_settings import BaseSettings

from xtr_dotenv.dotenv_settings_source import DotenvSettingsSource

if TYPE_CHECKING:
    from pydantic_settings import PydanticBaseSettingsSource

__all__ = ["DotenvSettings"]


class DotenvSettings(BaseSettings):
    """Base class whose subclasses take the dotenv cascade behind the real env.

    Override the ``_dotenv_*`` class variables to point the cascade at a
    different file, a different environment key, or to add extra test-like
    environments where the ``.local`` overlay must not run.
    """

    _dotenv_path: ClassVar[str] = ".env"
    _dotenv_env_key: ClassVar[str] = "APP_ENV"
    _dotenv_default_env: ClassVar[str] = "dev"
    _dotenv_test_envs: ClassVar[tuple[str, ...]] = ("test",)

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls: type[BaseSettings],
        init_settings: PydanticBaseSettingsSource,
        env_settings: PydanticBaseSettingsSource,
        dotenv_settings: PydanticBaseSettingsSource,
        file_secret_settings: PydanticBaseSettingsSource,
    ) -> tuple[PydanticBaseSettingsSource, ...]:
        """Return the source order: init, env, cascade, secrets."""
        del dotenv_settings  # Replaced by DotenvSettingsSource below.
        source = DotenvSettingsSource(
            settings_cls,
            path=cls._dotenv_path,
            env_key=cls._dotenv_env_key,
            default_env=cls._dotenv_default_env,
            test_envs=cls._dotenv_test_envs,
        )
        return (
            init_settings,
            env_settings,
            cast("PydanticBaseSettingsSource", source),
            file_secret_settings,
        )
