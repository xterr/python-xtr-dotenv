"""``dotenv:dump``: compile the cascade for one env into ``<path>.local.json``."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Final, final

import anyio.to_thread
from xtr_console import ConsoleStyle, ExitCode, as_command
from xtr_dependency_injection import (  # noqa: TC002 — engine reads annotations at runtime.
    Injected,
    KernelInterface,
)

from xtr_dotenv.bundle.dotenv_config import (  # noqa: TC001 — engine reads annotations at runtime.
    DotenvConfig,
)
from xtr_dotenv.dotenv import PATH_VAR, TRACKING_VAR, Dotenv
from xtr_dotenv.exception import DotenvError, PathError

__all__ = ["DotenvDumpCommand"]

_WRITE_FLAGS: Final = os.O_WRONLY | os.O_CREAT | os.O_TRUNC | getattr(os, "O_NOFOLLOW", 0)
"""Create or truncate the dump, refusing a symbolic link where the platform can."""


@as_command("dotenv:dump")
@final
class DotenvDumpCommand:
    """Compile the layered cascade for one env into ``<path>.local.json``.

    The dump is what :meth:`Dotenv.boot_env` reads for a fast start. It is
    computed on a fresh environ carrying only the env key, so no real
    environment variable lands in it — but it carries whatever the cascade's
    files carry, the ``.local`` overlays included, so gitignore it as those
    files are.
    """

    async def __call__(
        self,
        io: ConsoleStyle,
        kernel: Injected[KernelInterface],
        config: Injected[DotenvConfig],
        env: str | None = None,
    ) -> int:
        """Write the compiled cascade for ``env`` (default: the kernel's env)."""
        target_env = env if env is not None else kernel.environment
        base_path = config.base_path(kernel.project_dir)
        sandbox: dict[str, str] = {config.env_key: target_env}
        loader = Dotenv(env_key=config.env_key, environ=sandbox)
        try:
            _ = loader.load_env(
                str(base_path),
                default_env=target_env,
                test_envs=config.test_envs,
            )
        except DotenvError as error:
            io.error(f"cannot compile cascade: {error}")
            return ExitCode.FAILURE
        payload = _extract(sandbox)
        dump_path = Path(f"{base_path}.local.json")
        content = json.dumps(payload, indent=2, sort_keys=True)
        await anyio.to_thread.run_sync(_write, dump_path, content)
        io.success(f"wrote {dump_path} ({len(payload)} values)")
        return ExitCode.SUCCESS


def _write(path: Path, content: str) -> None:
    """Create the dump ``0o600`` and write it; the caller runs this off the event loop.

    The dump carries whatever the ``.local`` layers carry, so it is a
    secret-bearing file: it is created private, and an existing world-readable
    one is tightened on its descriptor before a byte of content reaches it, so
    the dump never sits in a file that is still wide. A symbolic link at the
    path is refused rather than written through — where the platform offers
    ``O_NOFOLLOW``, the open refuses one planted after the check too.

    Raises:
        PathError: When a symbolic link sits at the dump path.
    """
    if path.is_symlink():
        raise PathError(str(path))
    descriptor = os.open(path, _WRITE_FLAGS, 0o600)
    with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
        os.fchmod(descriptor, 0o600)
        _ = handle.write(content)


def _extract(sandbox: dict[str, str]) -> dict[str, str]:
    """Drop the internal bookkeeping variables before serialising."""
    return {name: value for name, value in sandbox.items() if name not in {TRACKING_VAR, PATH_VAR}}
