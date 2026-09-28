"""Layered dotenv loading with variable expansion.

``.env`` files carry the "how do I run this" bits — database URL, feature
flags, log level — that must move with the code but should never live in
it. Real applications keep several files layered so a developer laptop, a
CI runner and a production host each end up with the settings that suit,
without any one file knowing about the other.

:class:`Dotenv` is the loader every layer runs through. It reads a base
file, decides the environment (from a chosen variable, or a default when
the variable is unset), applies the ``.env.local`` per-machine override
outside test runs, and finally the environment-specific ``.env.{env}`` and
``.env.{env}.local`` files, in that order. A real environment variable
always wins over anything a file says — when it is expanded into another
value too.

Expansion is resolved once every file of a call is read, so a value in
``.env`` may reference one only ``.env.local`` defines; only the environment
key is resolved early, since it decides which files come next.
"""

from __future__ import annotations

import json
import os
import re
from io import StringIO
from pathlib import Path
from typing import TYPE_CHECKING, Final, Self, cast, final

from dotenv.parser import parse_stream

from xtr_dotenv.exception import FormatError, PathError, VariableCircularReferenceError

if TYPE_CHECKING:
    from collections.abc import Callable, Collection, Iterable, Mapping, MutableMapping

    Lookup = Callable[[str], "str | None"]
    Assign = Callable[[str, str], None]

__all__ = ["PATH_VAR", "TRACKING_VAR", "Dotenv"]

TRACKING_VAR: Final = "XTR_DOTENV_VARS"
"""Lists, comma-separated, every variable a file set — a later file may replace those."""

PATH_VAR: Final = "XTR_DOTENV_PATH"
"""The base path the last cascade loaded, for tooling."""

_BRACED: Final = re.compile(r"\$\{([A-Za-z_][A-Za-z0-9_]*)(?:(:[-=])((?:[^}\\]|\\.)*))?\}")
_UNBRACED: Final = re.compile(r"\$([A-Za-z_][A-Za-z0-9_]*)")
_BRACE_CHECK: Final = re.compile(r"\$\{([A-Za-z_][A-Za-z0-9_]*)(?::[-=]((?:[^}\\]|\\.)*))?(\})?")
_UNSUPPORTED_IN_DEFAULT: Final = re.compile(r"['\"{$]")
_ESCAPED: Final = re.compile(r"\\.")
_TRUE: Final = frozenset({"1", "true", "yes", "on"})
_NUMBER: Final = re.compile(r"[+-]?(\d+(\.\d*)?|\.\d+)([eE][+-]?\d+)?")

Raw = tuple[str, bool]


@final
class _Blocked:
    """A reference to a value the current pass has not resolved yet."""


_BLOCKED: Final = _Blocked()
"""A value as a file wrote it, and whether it was single-quoted (never expanded)."""


@final
class Dotenv:
    """Load layered dotenv files into a target environment mapping.

    A ``Dotenv`` never touches :data:`os.environ` unless it is the target
    mapping. Hand it a plain :class:`dict` in a test and no other test
    running in the same process can see anything it did.
    """

    __slots__ = ("_debug_key", "_env_key", "_environ", "_prod_envs")

    def __init__(
        self,
        env_key: str = "APP_ENV",
        debug_key: str = "APP_DEBUG",
        *,
        environ: MutableMapping[str, str] | None = None,
        prod_envs: Iterable[str] = ("prod",),
    ) -> None:
        """Build a loader that reads and writes ``environ`` (default: ``os.environ``).

        ``prod_envs`` are the environments where :meth:`boot_env` leaves debug
        off unless the debug key turns it on; it is on by default elsewhere.
        """
        self._env_key = env_key
        self._debug_key = debug_key
        self._environ: MutableMapping[str, str] = environ if environ is not None else os.environ
        self._prod_envs: tuple[str, ...] = tuple(prod_envs)

    @property
    def env_key(self) -> str:
        """The variable naming the active environment."""
        return self._env_key

    @property
    def debug_key(self) -> str:
        """The variable naming debug mode."""
        return self._debug_key

    def set_prod_envs(self, envs: Iterable[str]) -> Self:
        """Replace the environments where :meth:`boot_env` leaves debug off by default.

        The same as passing ``prod_envs`` to the constructor.
        """
        self._prod_envs = tuple(envs)
        return self

    def parse(self, data: str, path: str = ".env") -> dict[str, str]:
        """Parse one file's contents and return its expanded name-to-value mapping.

        Expansion reads, in order: a real environment variable, a value
        parsed earlier in ``data``, a variable set by an earlier file.

        Raises:
            FormatError: On a line that cannot be parsed, or a key without ``=``.
            VariableCircularReferenceError: If values reference each other in
                a loop.
        """
        return self._resolve(dict(_bindings(data, path)), override=False)

    def load(self, path: str, *extra: str) -> Self:
        """Load files without overriding real environment variables.

        Raises:
            PathError: If a file cannot be read.
            FormatError: On a line that cannot be parsed.
            VariableCircularReferenceError: If values reference each other in
                a loop.
        """
        return self._load((path, *extra), override=False)

    def overload(self, path: str, *extra: str) -> Self:
        """Load files, overriding real environment variables too.

        Raises:
            PathError: If a file cannot be read.
            FormatError: On a line that cannot be parsed.
            VariableCircularReferenceError: If values reference each other in
                a loop.
        """
        return self._load((path, *extra), override=True)

    def populate(self, values: Mapping[str, str], override_existing_vars: bool = False) -> Self:
        """Write ``values`` into the target environ under the tracking rules.

        A real (untracked) variable is never replaced unless
        ``override_existing_vars``; a name :data:`TRACKING_VAR` lists came
        from a file, and a later file may replace it.
        """
        tracked = self._tracked()
        written = {
            name
            for name in values
            if override_existing_vars or name not in self._environ or name in tracked
        }
        for name in written:
            self._environ[name] = values[name]
        if written - tracked:
            self._environ[TRACKING_VAR] = ",".join(sorted(tracked | written))
        return self

    def load_env(
        self,
        path: str,
        env_key: str | None = None,
        default_env: str = "dev",
        test_envs: tuple[str, ...] = ("test",),
        override_existing_vars: bool = False,
    ) -> Self:
        """Load ``path`` and its per-environment overlays, in the standard order.

        The cascade is: ``path`` (or ``path.dist`` when ``path`` is missing);
        read the environment key, defaulting it to ``default_env``; outside
        ``test_envs``, ``path.local``, then read the key again; if the
        environment is ``"local"``, stop; else ``path.{env}``, then
        ``path.{env}.local``. Later files override earlier ones; real
        environment variables always win.

        Raises:
            PathError: If neither ``path`` nor ``path.dist`` can be read.
            FormatError: On a line that cannot be parsed, or when an
                environment's own file names another environment.
            VariableCircularReferenceError: If values reference each other in
                a loop.
        """
        key = env_key if env_key is not None else self._env_key
        override = override_existing_vars
        self._environ[PATH_VAR] = path
        _, _, merged = self._cascade(path, key, default_env, test_envs, override)
        return self.populate(self._resolve(merged, override=override), override)

    def cascade(
        self,
        path: str,
        env_key: str | None = None,
        default_env: str = "dev",
        test_envs: tuple[str, ...] = ("test",),
        override_existing_vars: bool = False,
    ) -> tuple[str, tuple[str, ...]]:
        """Return the environment :meth:`load_env` settles on, and the files it considers.

        The files come in the order they are layered, the optional ones
        whether they exist or not, so a tool can show what is missing too.
        Nothing is written to the environment.

        Raises:
            PathError: If neither ``path`` nor ``path.dist`` can be read.
            FormatError: On a line that cannot be parsed, or when an
                environment's own file names another environment.
        """
        key = env_key if env_key is not None else self._env_key
        env, considered, _ = self._cascade(
            path, key, default_env, test_envs, override_existing_vars
        )
        return env, considered

    def _cascade(
        self,
        path: str,
        key: str,
        default_env: str,
        test_envs: tuple[str, ...],
        override: bool,
    ) -> tuple[str, tuple[str, ...], dict[str, Raw]]:
        """Read the cascade: the environment, the files considered in order, what they bind."""
        merged: dict[str, Raw] = {}
        base = path if _is_file(path) or not _is_file(f"{path}.dist") else f"{path}.dist"
        considered = [base]
        merged.update(_bindings(_read(base), base))
        env = self._current(key, merged, override)
        if env is None:
            merged[key] = (default_env, True)
            env = default_env
        if env not in test_envs:
            considered.append(f"{path}.local")
            if _is_file(f"{path}.local"):
                merged.update(_bindings(_read(f"{path}.local"), f"{path}.local"))
                env = self._current(key, merged, override) or env
        if env != "local":
            for overlay in (f"{path}.{env}", f"{path}.{env}.local"):
                considered.append(overlay)
                if not _is_file(overlay):
                    continue
                data = _read(overlay)
                merged.update(_bindings(data, overlay))
                named = self._current(key, merged, override)
                if named != env:
                    # Its own overlays were chosen by the environment it now contradicts.
                    reason = f"sets {key} to {named!r} in the files of environment {env!r}"
                    raise FormatError(overlay, _line_of(data, key), reason)
        return env, tuple(considered), merged

    def boot_env(
        self,
        path: str,
        default_env: str = "dev",
        test_envs: tuple[str, ...] = ("test",),
        override_existing_vars: bool = False,
    ) -> Self:
        """Load the environment, from the ``dotenv:dump`` output when it applies, and set debug.

        ``path.local.json`` — a JSON object of strings the dump writes — is
        used when overriding, when it names no environment, or when the one
        it names is the current one; otherwise the cascade of
        :meth:`load_env` runs. The debug key then becomes ``"1"`` or ``"0"``:
        its value read as a flag (``1/true/yes/on`` or a non-zero number),
        or, unset, whether the environment is not a production one.

        Raises:
            PathError: If the cascade runs and its base file cannot be read.
            FormatError: On a line that cannot be parsed.
            VariableCircularReferenceError: If values reference each other in
                a loop.
        """
        dumped = _read_dump(f"{path}.local.json")
        if dumped is not None and self._dump_applies(dumped, override_existing_vars):
            self._environ[PATH_VAR] = path
            _ = self.populate(dumped, override_existing_vars)
        else:
            _ = self.load_env(
                path,
                default_env=default_env,
                test_envs=test_envs,
                override_existing_vars=override_existing_vars,
            )
        debug = self._environ.get(self._debug_key)
        if debug is None:
            enabled = self._environ.get(self._env_key) not in self._prod_envs
        else:
            enabled = _flag(debug)
        self._environ[self._debug_key] = "1" if enabled else "0"
        return self

    def _load(self, paths: tuple[str, ...], *, override: bool) -> Self:
        merged: dict[str, Raw] = {}
        for path in paths:
            merged.update(_bindings(_read(path), path))
        return self.populate(self._resolve(merged, override=override), override)

    def _dump_applies(self, dumped: Mapping[str, str], override: bool) -> bool:
        dumped_env = dumped.get(self._env_key)
        current = self._environ.get(self._env_key, dumped_env)
        return override or dumped_env is None or current == dumped_env

    def _tracked(self) -> set[str]:
        raw = self._environ.get(TRACKING_VAR, "")
        return {name.strip() for name in raw.split(",") if name.strip()}

    def _real(self, name: str, override: bool) -> str | None:
        """Return ``name`` from the environment when it wins over the files, else ``None``."""
        if override or name not in self._environ or name in self._tracked():
            return None
        return self._environ[name]

    def _current(self, name: str, merged: Mapping[str, Raw], override: bool) -> str | None:
        """Return the value ``name`` will have once ``merged`` is populated."""
        real = self._real(name, override)
        if real is not None:
            return real
        if name not in merged:
            return self._environ.get(name)
        raw, single = merged[name]
        if single:
            return raw

        raws = {other: value for other, (value, _) in merged.items()}

        def lookup(other: str) -> str | None:
            found = self._lookup(name, other, raws, (), override)
            return None if isinstance(found, _Blocked) else found

        return _expand(raw, lookup, lambda _name, _value: None)

    def _resolve(self, merged: Mapping[str, Raw], *, override: bool) -> dict[str, str]:
        """Expand every value of ``merged``, repeating while values wait on each other.

        A name resolves, in order, to: a real environment variable (unless
        overriding), a value resolved from the files, the environment. A
        reference to a value not resolved yet waits for the next pass;
        ``A=${A:-x}`` reads the value ``A`` has now, or the default. ``${B:=x}``
        also defines ``B`` when nothing else does.

        Raises:
            VariableCircularReferenceError: If a pass resolves nothing while
                values still wait — they wait on each other.
        """
        resolved = {name: raw for name, (raw, single) in merged.items() if single}
        pending = {name: raw for name, (raw, single) in merged.items() if not single}
        while pending:
            waiting: dict[str, str] = {}
            for name, raw in pending.items():
                expanded = self._expand_one(name, raw, merged, resolved, set(pending), override)
                if expanded is None:
                    waiting[name] = raw
                else:
                    resolved[name] = expanded
            if len(waiting) == len(pending):
                break
            pending = waiting
        if pending:
            raise VariableCircularReferenceError(tuple(pending))
        return resolved

    def _lookup(
        self,
        name: str,
        other: str,
        values: Mapping[str, str],
        pending: Collection[str],
        override: bool,
    ) -> str | _Blocked | None:
        """Return what ``other`` reads as inside ``name``'s value — the precedence of the files.

        A real environment variable (unless overriding), then a value from the
        files, then the environment. ``_BLOCKED`` when ``other`` is still
        ``pending``; ``A=${A:-x}`` reads the value ``A`` has now, or nothing.
        """
        if other == name:
            return self._environ.get(name)
        real = self._real(other, override)
        if real is not None:
            return real
        if other in values:
            return values[other]
        if other in pending:
            return _BLOCKED
        return self._environ.get(other)

    def _expand_one(  # noqa: PLR0913, PLR0917 — the state of one resolution pass.
        self,
        name: str,
        raw: str,
        merged: Mapping[str, Raw],
        resolved: dict[str, str],
        pending: set[str],
        override: bool,
    ) -> str | None:
        """Return ``raw`` expanded, or ``None`` when it references a value not resolved yet."""
        blocked = False

        def lookup(other: str) -> str | None:
            nonlocal blocked
            found = self._lookup(name, other, resolved, pending, override)
            if isinstance(found, _Blocked):
                blocked = True
                return None
            return found

        def assign(other: str, value: str) -> None:
            if other not in merged and other not in self._environ:
                _ = resolved.setdefault(other, value)

        expanded = _expand(raw, lookup, assign)
        return None if blocked else expanded


def _bindings(data: str, path: str) -> Iterable[tuple[str, Raw]]:
    """Yield ``(name, (raw value, single-quoted))`` for every binding of ``data``.

    Raises:
        FormatError: On a line python-dotenv cannot parse, or a key without ``=``.
    """
    for binding in parse_stream(StringIO(data)):
        line = binding.original.line
        if binding.error:
            raise FormatError(path, line, "cannot parse line")
        if binding.key is None:  # a blank line or a comment
            continue
        if binding.value is None:
            raise FormatError(path, line, f"missing '=' after {binding.key!r}")
        single = _single_quoted(binding.original.string)
        reason = None if single else _expansion_error(binding.value)
        if reason is not None:
            raise FormatError(path, line, reason)
        yield binding.key, (binding.value, single)


def _line_of(data: str, name: str) -> int:
    """Return the line of the last binding of ``name`` in ``data``, ``0`` when there is none."""
    lines = [
        binding.original.line for binding in parse_stream(StringIO(data)) if binding.key == name
    ]
    return lines[-1] if lines else 0


def _expansion_error(raw: str) -> str | None:
    """Return why a ``${...}`` in ``raw`` cannot be expanded, or ``None`` when all can.

    A default is plain text: a quote, a brace or a dollar in one would need a
    nested expansion, which is not supported — refusing it beats expanding
    ``${A:-${B}}`` into a stray ``}``.
    """
    for match in _BRACE_CHECK.finditer(raw):
        if match.start() > 0 and raw[match.start() - 1] == "\\":
            continue
        name, default, closing = match.group(1), match.group(2), match.group(3)
        if closing is None:
            return f"unclosed braces on variable expansion of {name!r}"
        unsupported = _UNSUPPORTED_IN_DEFAULT.search(_ESCAPED.sub("", default or ""))
        if unsupported is not None:
            return (
                f"unsupported character {unsupported.group(0)!r} "
                f"in the default value of variable {name!r}"
            )
    return None


def _single_quoted(original: str) -> bool:
    """Return whether the value in the line ``original`` starts with a single quote.

    python-dotenv hands back the value unquoted, so the verbatim line is the
    only place the quoting is still visible.
    """
    _, separator, tail = original.partition("=")
    return bool(separator) and tail.lstrip().startswith("'")


def _is_file(path: str) -> bool:
    try:
        return Path(path).is_file()
    except OSError:
        return False


def _read(path: str) -> str:
    """Return ``path``'s text.

    Raises:
        PathError: If it cannot be read.
        FormatError: If it is not UTF-8 text.
    """
    try:
        return Path(path).read_text(encoding="utf-8")
    except OSError as error:
        raise PathError(path) from error
    except UnicodeDecodeError as error:
        raise FormatError(path, 0, "not valid UTF-8 text") from error


def _read_dump(path: str) -> dict[str, str] | None:
    """Return the dumped values in ``path``, or ``None`` when absent or not strings only."""
    if not _is_file(path):
        return None
    try:
        payload = cast("object", json.loads(Path(path).read_text(encoding="utf-8")))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(payload, dict):
        return None
    items = cast("dict[object, object]", payload).items()
    if not all(isinstance(key, str) and isinstance(value, str) for key, value in items):
        return None
    return cast("dict[str, str]", payload)


def _flag(value: str) -> bool:
    text = value.strip().lower()
    return text in _TRUE or (bool(_NUMBER.fullmatch(text)) and float(text) != 0)


def _expand(raw: str, lookup: Lookup, assign: Assign) -> str:
    r"""Substitute every ``$VAR``, ``${VAR}``, ``${VAR:-default}`` and ``${VAR:=default}``.

    ``\$`` is a literal dollar. ``$(command)`` is deliberately not supported:
    loading settings runs nothing. A ``:=`` default is also handed to
    ``assign``.
    """
    output: list[str] = []
    index = 0
    while index < len(raw):
        char = raw[index]
        if char == "\\" and raw.startswith("$", index + 1):
            output.append("$")
            index += 2
            continue
        match = (_BRACED if raw.startswith("${", index) else _UNBRACED).match(raw, index)
        if char != "$" or match is None:
            output.append(char)
            index += 1
            continue
        name = match.group(1)
        value = lookup(name)
        operator = match.group(2) if match.re is _BRACED else None
        if operator is not None and not value:
            default = _expand(match.group(3).replace("\\}", "}"), lookup, assign)
            if operator == ":=":
                assign(name, default)
            value = default
        output.append(value or "")
        index = match.end()
    return "".join(output)
