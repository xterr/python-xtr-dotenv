"""Configuration for :class:`~xtr_dotenv.bundle.dotenv_bundle.DotenvBundle`."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

__all__ = ["DotenvConfig"]


@dataclass(frozen=True, slots=True)
class DotenvConfig:
    """How the dotenv bundle describes the layered cascade to its commands.

    The bundle itself does no I/O: an application calls
    ``Dotenv().boot_env(...)`` at its entry point before building the
    kernel. What lives here is the description the ``dotenv:dump`` and
    ``debug:dotenv`` commands read to reason about the same cascade.

    Attributes:
        path: The base ``.env`` path. ``%kernel.project_dir%`` and every other
            parameter reference is resolved by the kernel; a relative path is
            taken from the project directory.
        env_key: The variable naming the active environment.
        debug_key: The variable naming debug mode.
        test_envs: Environments where the ``.local`` overlay is skipped.
        prod_envs: Environments considered production for debug defaulting.

    Raises:
        ValueError: When any of ``path``, ``env_key``, ``debug_key``,
            ``test_envs`` or ``prod_envs`` is empty.
    """

    path: str = "%kernel.project_dir%/.env"
    env_key: str = "APP_ENV"
    debug_key: str = "APP_DEBUG"
    test_envs: tuple[str, ...] = ("test",)
    prod_envs: tuple[str, ...] = ("prod",)

    def __post_init__(self) -> None:
        """Refuse combinations the loader would silently accept but not mean."""
        if not self.path:
            message = "path must not be empty"
            raise ValueError(message)
        if not self.env_key:
            message = "env_key must not be empty"
            raise ValueError(message)
        if not self.debug_key:
            message = "debug_key must not be empty"
            raise ValueError(message)
        if not self.test_envs:
            message = "test_envs must not be empty"
            raise ValueError(message)
        if not self.prod_envs:
            message = "prod_envs must not be empty"
            raise ValueError(message)

    def base_path(self, project_dir: Path) -> Path:
        """Return :attr:`path`, taken from ``project_dir`` when it is relative."""
        candidate = Path(self.path)
        return candidate if candidate.is_absolute() else project_dir / candidate
