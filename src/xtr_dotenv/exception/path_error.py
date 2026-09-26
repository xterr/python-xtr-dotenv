"""A file a loader was told to read, but could not."""

from __future__ import annotations

from .dotenv_error import DotenvError

__all__ = ["PathError"]


class PathError(DotenvError, OSError):
    """A file a loader was told to read, but could not.

    Raised where the load was asked for, so a missing file, a directory in
    its place, or a permission error fail loudly and where the caller can do
    something about it — not silently as a file with nothing in it.

    Also an :class:`OSError`, so code catching filesystem failures keeps
    working.

    Attributes:
        path: The file the loader was asked to read.
    """

    path: str

    def __init__(self, path: str) -> None:
        """Record the path that could not be read."""
        self.path = path
        super().__init__(f"cannot read dotenv file {path!r}")
