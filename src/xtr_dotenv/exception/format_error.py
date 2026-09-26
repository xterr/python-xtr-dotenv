"""A line in a dotenv file the parser could not read."""

from __future__ import annotations

from .dotenv_error import DotenvError

__all__ = ["FormatError"]


class FormatError(DotenvError, ValueError):
    """A line in a dotenv file the parser could not read.

    Raised where the bad line lives — a bad binding, or a key without ``=`` —
    rather than pretending the file loaded and letting a caller trip over a
    value that is not there.

    Also a :class:`ValueError`, so code already guarding parsing with
    ``except ValueError`` keeps working without learning a new exception.

    Attributes:
        path: The file the line came from, as it was given to the loader.
        line: The 1-based line number in ``path``.
        reason: What about the line could not be read.
    """

    path: str
    line: int
    reason: str

    def __init__(self, path: str, line: int, reason: str) -> None:
        """Record where the bad line is, and why it could not be read."""
        self.path = path
        self.line = line
        self.reason = reason
        super().__init__(f"{path}:{line}: {reason}")
