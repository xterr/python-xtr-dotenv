"""A file a loader was told to read, or a command to write, but could not."""

from __future__ import annotations

from .dotenv_error import DotenvError

__all__ = ["PathError"]


class PathError(DotenvError, OSError):
    """A file a loader was told to read, or a command to write, but could not.

    Raised where the work was asked for, so a missing file, a directory in
    its place, a permission error, or a symbolic link where a real file
    belongs fail loudly and where the caller can do something about it — not
    silently as a file with nothing in it.

    Also an :class:`OSError`, so code catching filesystem failures keeps
    working.

    Attributes:
        path: The file that could not be used.
    """

    path: str

    def __init__(self, path: str) -> None:
        """Record the path that could not be used."""
        self.path = path
        super().__init__(f"cannot use dotenv file {path!r}")
