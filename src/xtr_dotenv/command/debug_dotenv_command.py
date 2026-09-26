"""``debug:dotenv``: list the cascade files and each variable's value per file."""

from __future__ import annotations

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
from xtr_dotenv.dotenv import Dotenv
from xtr_dotenv.exception import DotenvError

__all__ = ["DebugDotenvCommand"]


@as_command("debug:dotenv")
@final
class DebugDotenvCommand:
    """List every file in the cascade and each variable's value per file.

    Missing files are shown too, in order, so a debugger can see exactly
    what the loader would have done. ``name`` filters the value listing to
    a single variable, which is what a "why is this value what it is?"
    session usually needs.
    """

    async def __call__(
        self,
        io: ConsoleStyle,
        kernel: Injected[KernelInterface],
        config: Injected[DotenvConfig],
        name: str | None = None,
    ) -> int:
        """Print the cascade files and (optionally) one variable across them."""
        base_path = config.base_path(kernel.project_dir)
        env = kernel.environment
        cascade_paths = _cascade_paths(base_path, env, config.test_envs)
        io.section(f"Cascade for env={env!r} at {base_path}")
        io.table(
            ("File", "Status"),
            tuple(
                (str(candidate), "loaded" if candidate.exists() else "missing")
                for candidate in cascade_paths
            ),
        )
        per_file: list[tuple[str, dict[str, str]]] = []
        for candidate in cascade_paths:
            if not candidate.exists():
                continue
            try:
                loader = Dotenv(env_key=config.env_key, environ={config.env_key: env})
                # Parse a single file to see what IT contributes; expansion is
                # done against the env key alone so the output is per-file.
                parsed = loader.parse(candidate.read_text(encoding="utf-8"), str(candidate))
            except DotenvError as error:
                io.error(f"{candidate}: {error}")
                return ExitCode.FAILURE
            per_file.append((str(candidate), parsed))
        rows: list[tuple[str, str, str]] = []
        for file_label, values in per_file:
            for var_name, value in sorted(values.items()):
                if name is not None and var_name != name:
                    continue
                rows.append((file_label, var_name, value))
        if rows:
            io.table(("File", "Variable", "Value"), tuple(rows))
        elif name is not None:
            io.note(f"variable {name!r} not present in any cascade file")
        return ExitCode.SUCCESS


def _cascade_paths(base: Path, env: str, test_envs: tuple[str, ...]) -> list[Path]:
    """List the cascade files in the order the loader would try them."""
    paths: list[Path] = [base]
    dist = Path(f"{base}.dist")
    if not base.exists() and dist.exists():
        paths.append(dist)
    if env not in test_envs:
        paths.append(Path(f"{base}.local"))
    if env != "local":
        paths.append(Path(f"{base}.{env}"))
        paths.append(Path(f"{base}.{env}.local"))
    return paths
