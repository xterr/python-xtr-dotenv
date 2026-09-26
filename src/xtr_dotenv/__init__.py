"""Layered dotenv files loaded into the environment, and the same layers behind settings.

Real applications keep several ``.env`` files layered so a developer
laptop, a CI runner and a production host each end up with the settings
that suit, without any one file knowing about the other. This library is
the loader every layer runs through, plus a pydantic-settings source that
feeds a typed model from the same cascade.

The two entry points a typical application needs are:

* :class:`~xtr_dotenv.dotenv.Dotenv` — call ``Dotenv().boot_env(project_dir / ".env")``
  at the process' entry point, before anything reads a settings model.
* :class:`~xtr_dotenv.dotenv_settings.DotenvSettings` — a
  :class:`~pydantic_settings.BaseSettings` base that gets the layered
  values *without* mutating :data:`os.environ` itself.
"""

from __future__ import annotations

from importlib.metadata import PackageNotFoundError, version

from .dotenv import PATH_VAR, TRACKING_VAR, Dotenv
from .dotenv_settings import DotenvSettings
from .dotenv_settings_source import DotenvSettingsSource
from .exception import (
    DotenvError,
    FormatError,
    PathError,
    VariableCircularReferenceError,
)

try:
    __version__ = version("xtr-dotenv")
except PackageNotFoundError:  # pragma: no cover
    # Running from a source tree with no installed metadata to read.
    __version__ = "0+unknown"

__all__ = [
    "PATH_VAR",
    "TRACKING_VAR",
    "Dotenv",
    "DotenvError",
    "DotenvSettings",
    "DotenvSettingsSource",
    "FormatError",
    "PathError",
    "VariableCircularReferenceError",
    "__version__",
]
