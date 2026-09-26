"""``dotenv:dump``: compile the cascade for one env into ``<path>.local.json``."""

from __future__ import annotations

import json
from pathlib import Path
from typing import final

from xtr_console import ConsoleStyle, ExitCode, as_command
from xtr_dependency_injection import (  # noqa: TC002 — engine reads annotations at runtime.
    Injected,
    KernelInterface,
)

from xtr_dotenv.bundle.dotenv_config import (  # noqa: TC001 — engine reads annotations at runtime.
    DotenvConfig,
)
from xtr_dotenv.dotenv import PATH_VAR, TRACKING_VAR, Dotenv
from xtr_dotenv.exception import DotenvError

__all__ = ["DotenvDumpCommand"]


@as_command("dotenv:dump")
@final
class DotenvDumpCommand:
    """Compile the layered cascade for one env into ``<path>.local.json``.

    The dump is what :meth:`Dotenv.boot_env` reads for a fast start. It is
    computed on a **fresh environ** carrying only the env key (never real
    secrets), so the file it writes is safe to commit and travels with the
    build.
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
        _write(dump_path, json.dumps(payload, indent=2, sort_keys=True))
        io.success(f"wrote {dump_path} ({len(payload)} values)")
        return ExitCode.SUCCESS


def _write(path: Path, content: str) -> None:
    """Blocking write, isolated so the async ``__call__`` stays lint-clean."""
    _ = path.write_text(content, encoding="utf-8")


def _extract(sandbox: dict[str, str]) -> dict[str, str]:
    """Drop the internal bookkeeping variables before serialising."""
    return {name: value for name, value in sandbox.items() if name not in {TRACKING_VAR, PATH_VAR}}
