"""The xtr-dotenv bundle: exposes the dotenv commands when a console is present.

The bundle does **not** load files itself. The application is expected to
call ``Dotenv().boot_env(project_dir / ".env")`` at its entry point,
before building the kernel: the kernel and every service it creates rely
on the environment already being layered by the time they read it.

What the bundle does supply is the two commands — ``dotenv:dump`` and
``debug:dotenv`` — that need the container's ``KernelInterface`` to know
the project directory. They are loaded only when the console bundle is
active, so a headless application still boots to zero config.
"""

from __future__ import annotations

from typing import final

from typing_extensions import override
from xtr_dependency_injection import (
    Bundle,
    ContainerBuilder,
    ServiceConfigurator,
    as_bundle,
    bundle_active,
)

from .dotenv_config import DotenvConfig

__all__ = ["DotenvBundle"]


@final
@as_bundle("dotenv", config=DotenvConfig)
class DotenvBundle(Bundle[DotenvConfig]):
    """Wire the dotenv commands into the container when a console is around."""

    @override
    def load_extension(
        self,
        config: DotenvConfig,
        services: ServiceConfigurator,
        builder: ContainerBuilder,
    ) -> None:
        """Load the command module only when a console bundle is active.

        Loading a command module late is the pattern the messenger bundle
        uses too: it keeps the console dependency out of the runtime graph
        for applications that do not run one, and does no I/O at build.
        """
        del config
        if bundle_active(builder, "console"):
            services.load("xtr_dotenv.command")
