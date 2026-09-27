"""Variables that reference each other, and never resolve."""

from __future__ import annotations

from .dotenv_error import DotenvError

__all__ = ["VariableCircularReferenceError"]


class VariableCircularReferenceError(DotenvError, ValueError):
    """Variables that reference each other, and never resolve.

    Expansion repeats while each pass resolves something; values still
    unresolved once a pass resolves nothing wait on each other, and are
    treated as a cycle rather than left with a suspicious empty value.

    Attributes:
        names: The variable names still unresolved after the final pass.
    """

    names: tuple[str, ...]

    def __init__(self, names: tuple[str, ...]) -> None:
        """Record the variables that never resolved."""
        self.names = names
        joined = ", ".join(sorted(names))
        super().__init__(f"variable(s) never resolved: {joined}")
