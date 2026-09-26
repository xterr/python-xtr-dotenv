"""A pydantic-settings source that yields the layered dotenv cascade.

The source runs the same cascade :meth:`Dotenv.load_env` runs, but against
a **copy** of :data:`os.environ` — so a model gets the layered values
without any file ever writing into the process environment. Only the
names the cascade actually loaded from files are returned; the real
environment is not shadowed here, because pydantic-settings' own
:class:`EnvSettingsSource` already covers it at a higher priority.
"""

from __future__ import annotations

import os
from typing import TYPE_CHECKING, final

from pydantic_settings import EnvSettingsSource
from typing_extensions import override

from xtr_dotenv.dotenv import PATH_VAR, TRACKING_VAR, Dotenv
from xtr_dotenv.exception import PathError

if TYPE_CHECKING:
    from collections.abc import Mapping

    from pydantic_settings import BaseSettings

__all__ = ["DotenvSettingsSource"]


@final
class DotenvSettingsSource(EnvSettingsSource):
    """Feed a :class:`~pydantic_settings.BaseSettings` model from a dotenv cascade.

    ``path``, ``env_key``, ``default_env`` and ``test_envs`` describe the
    cascade the source runs; every other keyword is forwarded to
    :class:`~pydantic_settings.EnvSettingsSource` so ``case_sensitive``,
    ``env_prefix``, ``env_nested_delimiter`` and friends work as usual.
    """

    def __init__(  # noqa: PLR0913 — the base source itself takes this many.
        self,
        settings_cls: type[BaseSettings],
        *,
        path: str = ".env",
        env_key: str = "APP_ENV",
        default_env: str = "dev",
        test_envs: tuple[str, ...] = ("test",),
        case_sensitive: bool | None = None,
        env_prefix: str | None = None,
        env_nested_delimiter: str | None = None,
        env_ignore_empty: bool | None = None,
        env_parse_none_str: str | None = None,
        env_parse_enums: bool | None = None,
    ) -> None:
        """Record the cascade parameters, then let the base initialise itself."""
        self._path = path
        self._env_key = env_key
        self._default_env = default_env
        self._test_envs = test_envs
        super().__init__(
            settings_cls,
            case_sensitive=case_sensitive,
            env_prefix=env_prefix,
            env_nested_delimiter=env_nested_delimiter,
            env_ignore_empty=env_ignore_empty,
            env_parse_none_str=env_parse_none_str,
            env_parse_enums=env_parse_enums,
        )

    @override
    def _load_env_vars(self) -> Mapping[str, str | None]:
        """Run the cascade on a copy of ``os.environ`` and return only file-loaded names."""
        sandbox: dict[str, str] = dict(os.environ)
        loader = Dotenv(env_key=self._env_key, environ=sandbox)
        try:
            _ = loader.load_env(
                self._path,
                default_env=self._default_env,
                test_envs=self._test_envs,
            )
        except PathError:
            return {}
        # Anything not tracked came from the real environ (or is our own
        # bookkeeping) and belongs to the env source, not to this one.
        tracked_raw = sandbox.get(TRACKING_VAR, "")
        tracked = {
            piece for piece in (fragment.strip() for fragment in tracked_raw.split(",")) if piece
        }
        source: dict[str, str | None] = {name: sandbox[name] for name in tracked if name in sandbox}
        # Never leak our own bookkeeping variables to the model.
        _ = source.pop(TRACKING_VAR, None)
        _ = source.pop(PATH_VAR, None)
        if not self.case_sensitive:
            return {name.lower(): value for name, value in source.items()}
        return source
