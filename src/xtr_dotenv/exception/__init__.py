"""Every error this library raises.

All of them derive from :class:`DotenvError`, so one ``except`` catches
anything a layered dotenv load can go wrong with, and a narrower one handles
one cause. Each carries the data a caller needs as typed attributes rather
than forcing a message to be parsed.
"""

from __future__ import annotations

from .dotenv_error import DotenvError
from .format_error import FormatError
from .path_error import PathError
from .variable_circular_reference_error import VariableCircularReferenceError

__all__ = [
    "DotenvError",
    "FormatError",
    "PathError",
    "VariableCircularReferenceError",
]
