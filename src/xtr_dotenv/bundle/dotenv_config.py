"""Configuration for :class:`~xtr_dotenv.bundle.dotenv_bundle.DotenvBundle`."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Final

from xtr_dotenv.dotenv import Dotenv
from xtr_dotenv.exception.invalid_argument_error import InvalidArgumentError

if TYPE_CHECKING:
    from collections.abc import MutableMapping

__all__ = ["DotenvConfig"]

_PARAMETER: Final = re.compile(r"%[^%]+%")
"""A container parameter reference — only the kernel can resolve one."""


@dataclass(frozen=True, slots=True)
class DotenvConfig:
    """The one description of the dotenv cascade: entry points and commands both read it.

    The bundle itself does no I/O: an application boots the environment
    from this object — ``DOTENV.boot(PROJECT_DIR)`` at its entry point,
    before the kernel is built — and the ``dotenv:dump`` and
    ``debug:dotenv`` commands read the same object from the container.
    What the cascade is lives here, and nowhere else.

    Attributes:
        path: The base ``.env`` path. ``%kernel.project_dir%`` is resolved
            against the project directory by :meth:`base_path`, and every
            other parameter reference by the kernel; a relative path is
            taken from the project directory.
        env_key: The variable naming the active environment.
        debug_key: The variable naming debug mode.
        default_env: The environment the cascade settles on when the
            environment key names none.
        test_envs: Environments where the ``.local`` overlay is skipped.
        prod_envs: Environments declared production — what
            :meth:`~xtr_dotenv.dotenv.Dotenv.boot_env`'s undeclared-environment
            warning and the ``debug:dotenv`` report read.
        debug_envs: Environments where ``boot_env`` leaves debug on by
            default; everywhere else it stays off.

    Raises:
        InvalidArgumentError: When any of ``path``, ``env_key``,
            ``debug_key``, ``default_env``, ``test_envs``, ``prod_envs`` or
            ``debug_envs`` is empty.
    """

    path: str = "%kernel.project_dir%/.env"
    env_key: str = "APP_ENV"
    debug_key: str = "APP_DEBUG"
    default_env: str = "dev"
    test_envs: tuple[str, ...] = ("test",)
    prod_envs: tuple[str, ...] = ("prod",)
    debug_envs: tuple[str, ...] = ("dev", "local", "test")

    def __post_init__(self) -> None:
        """Refuse combinations the loader would silently accept but not mean."""
        if not self.path:
            message = "path must not be empty"
            raise InvalidArgumentError(message)
        if not self.env_key:
            message = "env_key must not be empty"
            raise InvalidArgumentError(message)
        if not self.debug_key:
            message = "debug_key must not be empty"
            raise InvalidArgumentError(message)
        if not self.default_env:
            message = "default_env must not be empty"
            raise InvalidArgumentError(message)
        if not self.test_envs:
            message = "test_envs must not be empty"
            raise InvalidArgumentError(message)
        if not self.prod_envs:
            message = "prod_envs must not be empty"
            raise InvalidArgumentError(message)
        if not self.debug_envs:
            message = "debug_envs must not be empty"
            raise InvalidArgumentError(message)

    def base_path(self, project_dir: Path) -> Path:
        """Return :attr:`path` resolved against ``project_dir``.

        ``%kernel.project_dir%`` — the one parameter reference a caller can
        resolve without a container — is substituted here, so an entry point
        can boot the cascade before the kernel exists; a config the kernel
        handed on is already resolved and passes through unchanged. Any
        other ``%...%`` reference is refused: only the container can resolve
        it, and a caller without one would read a path that does not exist.

        Raises:
            InvalidArgumentError: When the path still names a parameter
                after the project directory is substituted.
        """
        candidate = Path(self.path.replace("%kernel.project_dir%", str(project_dir)))
        resolved = candidate if candidate.is_absolute() else project_dir / candidate
        if _PARAMETER.search(str(resolved)) is not None:
            message = (
                f"path {self.path!r} names a container parameter; only "
                f"%kernel.project_dir% can be resolved before the kernel is built"
            )
            raise InvalidArgumentError(message)
        return resolved

    def loader(self, *, environ: MutableMapping[str, str] | None = None) -> Dotenv:
        """Return the :class:`~xtr_dotenv.dotenv.Dotenv` this description builds.

        The one place the keys and the environment sets become a loader:
        an entry point and the commands run the very same cascade.
        """
        return Dotenv(
            env_key=self.env_key,
            debug_key=self.debug_key,
            environ=environ,
            prod_envs=self.prod_envs,
            debug_envs=self.debug_envs,
        )

    def boot(self, project_dir: Path, *, environ: MutableMapping[str, str] | None = None) -> Dotenv:
        """Load the cascade this description names into ``environ``, and set debug.

        The entry-point call — ``DOTENV.boot(PROJECT_DIR)`` runs before the
        kernel is built, so the base path is resolved against
        ``project_dir`` here, where no container exists to resolve it.
        """
        return self.loader(environ=environ).boot_env(
            str(self.base_path(project_dir)),
            default_env=self.default_env,
            test_envs=self.test_envs,
        )
