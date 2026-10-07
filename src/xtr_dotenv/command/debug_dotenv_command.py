"""``debug:dotenv``: list the cascade files and each variable's value per file."""

from __future__ import annotations

import os
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
    session usually needs. Values are masked unless ``--show-values`` is
    passed, so the output is safe to paste into a bug report.
    """

    async def __call__(
        self,
        io: ConsoleStyle,
        kernel: Injected[KernelInterface],
        config: Injected[DotenvConfig],
        name: str | None = None,
        *,
        show_values: bool = False,
    ) -> int:
        """Print the cascade files and (optionally) one variable across them.

        Values are masked unless ``show_values`` is set.
        """
        base_path = config.base_path(kernel.project_dir)
        # The loader's own cascade, read against a copy of this process's
        # environment: the files decide the environment unless a real
        # variable does, exactly as they did when the process loaded them.
        try:
            env, files = Dotenv(env_key=config.env_key, environ=dict(os.environ)).cascade(
                str(base_path), default_env=kernel.environment, test_envs=config.test_envs
            )
        except DotenvError as error:
            io.error(str(error))
            return ExitCode.FAILURE
        cascade_paths = [Path(file) for file in files]
        io.section(f"Cascade for env={env!r} at {base_path}")
        self._report_environment(io, config, base_path, env, kernel.environment)
        io.table(
            ("File", "Status"),
            tuple(
                (str(candidate), "loaded" if candidate.exists() else "missing")
                for candidate in cascade_paths
            ),
        )
        per_file = self._parse_each_file(io, config, cascade_paths, env)
        if per_file is None:
            return ExitCode.FAILURE
        rows = _value_rows(per_file, name, show_values=show_values)
        if rows:
            io.table(("File", "Variable", "Value"), tuple(rows))
        elif name is not None:
            io.note(f"variable {name!r} not present in any cascade file")
        if not show_values:
            io.note("values are masked; pass --show-values to reveal them")
        return ExitCode.SUCCESS

    def _parse_each_file(
        self,
        io: ConsoleStyle,
        config: DotenvConfig,
        cascade_paths: list[Path],
        env: str,
    ) -> list[tuple[str, dict[str, str]]] | None:
        """Parse every existing cascade file alone, or ``None`` after printing an error."""
        per_file: list[tuple[str, dict[str, str]]] = []
        for candidate in cascade_paths:
            if not candidate.exists():
                continue
            try:
                loader = Dotenv(env_key=config.env_key, environ={config.env_key: env})
                # Parse a single file to see what IT contributes; expansion is
                # done against the env key alone so the output is per-file.
                parsed = loader.parse(candidate.read_text(encoding="utf-8"), str(candidate))
            except (DotenvError, OSError, UnicodeDecodeError) as error:
                io.error(f"{candidate}: {error}")
                return None
            per_file.append((str(candidate), parsed))
        return per_file

    def _report_environment(
        self,
        io: ConsoleStyle,
        config: DotenvConfig,
        base_path: Path,
        env: str,
        default_env: str,
    ) -> None:
        """Print the environment, whether it is production, and the debug flag.

        The debug flag is read exactly as :meth:`Dotenv.boot_env` sets it —
        on a sandbox copy of this process's environment — so ``debug_key`` and
        ``prod_envs`` drive the same decision the application would make.
        """
        sandbox = dict(os.environ)
        try:
            _ = Dotenv(
                env_key=config.env_key,
                debug_key=config.debug_key,
                environ=sandbox,
                prod_envs=config.prod_envs,
            ).boot_env(str(base_path), default_env=default_env, test_envs=config.test_envs)
        except DotenvError:
            # The cascade table above already surfaced the real failure; the
            # debug flag is simply unknown when the files cannot be read.
            return
        production = "yes" if env in config.prod_envs else "no"
        io.table(
            ("Setting", "Value"),
            (
                ("environment", env),
                ("production", production),
                (f"debug ({config.debug_key})", sandbox.get(config.debug_key, "0")),
            ),
        )


def _value_rows(
    per_file: list[tuple[str, dict[str, str]]],
    name: str | None,
    *,
    show_values: bool,
) -> list[tuple[str, str, str]]:
    """Flatten the per-file values into display rows, masked unless asked, filtered by ``name``."""
    rows: list[tuple[str, str, str]] = []
    for file_label, values in per_file:
        for var_name, value in sorted(values.items()):
            if name is not None and var_name != name:
                continue
            rows.append((file_label, var_name, _display(value, show_values=show_values)))
    return rows


def _display(value: str, *, show_values: bool) -> str:
    """Return ``value`` as shown: masked unless ``show_values`` or empty."""
    if show_values or not value:
        return value
    return "*" * 8
