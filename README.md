<div align="center">

# xtr-dotenv

**Layered `.env` files loaded into the environment, and the same layers behind a typed settings model.**

<img alt="python 3.11+" src="https://img.shields.io/badge/python-%E2%89%A5%203.11-3776AB?logo=python&logoColor=white">
<img alt="typed" src="https://img.shields.io/badge/typed-ty%20%2B%20basedpyright-1f6feb">
<img alt="license MIT" src="https://img.shields.io/badge/license-MIT-blue">

</div>

---

## Why?

Real applications keep several `.env` files layered so a developer laptop, a CI runner and a
production host each end up with the settings that suit, without any one file knowing about
the other. This library is the loader every layer runs through, plus a pydantic-settings
source that feeds a typed model from the same cascade — without ever touching
`os.environ` behind your back.

- 📚 **The layered cascade** — `.env` → `.env.local` → `.env.{env}` → `.env.{env}.local`, with a
  `.env.dist` read instead of a missing `.env`, and real environment variables always winning.
- 🧪 **Testable end-to-end** — hand the loader a plain `dict` and no other test in the same
  process can see anything it did.
- 🧩 **Pydantic-settings integration** — `DotenvSettings` reads the same cascade from a
  sandboxed copy of `os.environ`, so a model gets the values without side effects.
- 🌐 **Variable expansion** — `$VAR`, `${VAR}`, `${VAR:-default}`, `${VAR:=default}`, `\$` as
  a literal. Single-quoted values are literal too. `$(command)` is kept as text, never run.
- ⚡ **A dumped fast path** — `dotenv:dump` writes the compiled cascade to `.env.local.json`,
  stamped with the description it was compiled from; `boot_env` reads that one file instead of
  the cascade, and refuses a dump whose stamp no longer matches.

## Install

```sh
uv add xtr-dotenv                           # the loader and the settings source
uv add xtr-dotenv xtr-dependency-injection  # + the container, for the DotenvBundle
uv add xtr-console                          # beside it: + the dotenv:dump and debug:dotenv commands
```

Requires Python 3.11+. Depends on `pydantic-settings`, `python-dotenv`, `typing-extensions` and
`anyio` — not on the container: the bundle is used when
[xtr-dependency-injection](../xtr-dependency-injection) is installed beside the package, never as
an extra, and the loader works without it. The two commands also need
[xtr-console](../xtr-console) installed beside it.

## Quick start

Call `Dotenv().boot_env(...)` at the very top of your entry point — **before** anything
reads a settings model, and before you build a kernel:

```python
from pathlib import Path

from xtr_dotenv import Dotenv

Dotenv().boot_env(str(Path(__file__).parent / ".env"))

# ... only now import the kernel, settings, etc.
from app.kernel import kernel

raise SystemExit(kernel.run(...))
```

`boot_env` also sets `APP_DEBUG` to `"1"` or `"0"`: its own value read as a flag when it is set,
otherwise on only in the environments `debug_envs` declares — `("dev", "local", "test")` by
default. That default fails closed: an environment declared nowhere (not the default, not in
`debug_envs`, `test_envs` or `prod_envs`) gets debug **off** plus a one-time `RuntimeWarning`
naming it and the remedies — set `APP_DEBUG` explicitly, or declare the environment.

The loader is stateless: hand it a `MutableMapping[str, str]` as `environ=` and no other
code sees a thing.

```python
sandbox: dict[str, str] = {}
Dotenv(environ=sandbox).load_env("/etc/app/.env")
```

## The file cascade

`load_env(path)` reads, in order:

| Order | File | When it applies |
| --- | --- | --- |
| 1 | `path` | Always, or `path.dist` when `path` is missing |
| 2 | *(reads env key from environ; an unset or empty one takes `default_env`)* | |
| 3 | `path.local` | Only outside `test_envs` — a developer's per-machine overrides |
| 4 | *(re-reads env key)* | The `.local` file may have set a different environment |
| 5 | `path.{env}` | When `env` is not `"local"` |
| 6 | `path.{env}.local` | Same — a per-machine override for that environment |

Files 5 and 6 were chosen by the environment, so one of them naming a different environment is
a `FormatError` pointing at the line. `cascade(path)` returns the environment and these files,
without loading anything — what `debug:dotenv` lists.

Later files override earlier ones. A **real** environment variable always wins over any file
unless `override_existing_vars=True` is passed — `overload()` passes it — and then the file's
value replaces it, the real one is gone, and the name counts as one a file set.
`XTR_DOTENV_VARS` tracks which names came from a file so a later file may replace them; `XTR_DOTENV_PATH` records the base path so
tooling can find it.

Its value being empty changes nothing: `FOO=` is how a process says "disabled", and no file
undoes it. The env key is the one exception — an empty one names no environment, so the
cascade defaults it and may write that default back.

## Variable expansion

| Written | Means |
| --- | --- |
| `$VAR`, `${VAR}` | the value of `VAR`, or empty when unset |
| `${VAR:-default}` | `default` when `VAR` is unset or empty |
| `${VAR:=default}` | the same, and record `VAR=default` for later lookups |
| `\$` | a literal dollar sign |

**Single-quoted values are never expanded** — that is the escape hatch for a literal `$`
inside a password. `$(command)` is kept as text and never run: a settings loader should do
no I/O beyond reading files. A default is plain text — a quote, a brace or a `$` in one
(`${A:-${B}}`), or a `${` never closed, is a `FormatError` naming the line. A value spanning
lines must be quoted.

Expansion runs once every file of the cascade is read, so a value in `.env` may reference
one only `.env.local` defines; a real environment variable wins inside an expansion as it
does everywhere else. A self-referencing `A=${A:-x}` reads the value `A` has now (or the
default) — it does not cycle. Expansion repeats as long as each pass resolves something, so a
chain of references resolves however long it is; values left waiting on each other are a real
cycle and raise `VariableCircularReferenceError`.

## Typed settings from the cascade

`DotenvSettings` is a `BaseSettings` base whose subclass reads the layered cascade from a
sandboxed copy of `os.environ`:

```python
from typing import ClassVar

from xtr_dotenv import DotenvSettings


class AppSettings(DotenvSettings):
    _dotenv_path: ClassVar[str] = "/etc/app/.env"
    _dotenv_env_key: ClassVar[str] = "APP_ENV"
    _dotenv_default_env: ClassVar[str] = "prod"

    database_url: str
    log_level: str = "INFO"
```

Source priority is: init keyword arguments > real environment variables > the dotenv
cascade > secret files > field defaults. **No file the source reads writes into
`os.environ`.** A relative `_dotenv_path` is taken from the process's working directory —
an application that means the project's `.env` sets `_dotenv_path = str(PROJECT_DIR / ".env")`.
A missing base file raises `PathError`: the cascade the model promises is the one it reads,
not an empty model.

## Errors

Everything the library raises derives from `DotenvError`, and carries the data as typed
attributes.

| Error | Raised when |
| --- | --- |
| `FormatError` | A line cannot be parsed (bad binding, key without `=`); carries `.path`, `.line`, `.reason` |
| `InvalidArgumentError` | A `DotenvConfig` field is empty; carries `.reason` |
| `PathError` | A file cannot be read — the cascade's base file included, raised by `DotenvSettings` — or the dump cannot be written; carries `.path` |
| `VariableCircularReferenceError` | Variables reference each other and never resolve; carries `.names` |

`FormatError`, `InvalidArgumentError` and `VariableCircularReferenceError` are also `ValueError`s; `PathError` is
also `OSError`. Existing `except` blocks keep working.

## Use in an application

Everything adding this package to an application on
[xtr-dependency-injection](../xtr-dependency-injection) takes — and, read backwards, what removing it undoes.

- **Install** — `uv add xtr-dotenv xtr-dependency-injection`: the bundle needs the container
  installed beside it, never as an extra. Install xtr-console beside it for the `dotenv:dump`
  and `debug:dotenv` commands.
- **Recipe** — `uv run xtr-recipes recipes:sync` does the *Activate*, *Configure*, *Environment*
  and *Ignore* steps below: it lists `DotenvBundle`, writes `config/packages/dotenv.py`, writes
  `APP_ENV=dev` in `.env`, and ignores the per-machine `.env.local`, `.env.*.local` and
  `.env.local.json`. It prints the *Load* step, which a recipe cannot make for you.
- **Load** — the bundle does not load `.env` files. `config/packages/dotenv.py` holds the one
  description of the cascade; call `DOTENV.boot(PROJECT_DIR)` at the top of every entry point,
  before the kernel is built:

  ```python
  # <app>/config/packages/dotenv.py — the recipe writes this
  from typing import Final

  from xtr_dependency_injection import configure
  from xtr_dotenv.bundle import DotenvConfig

  DOTENV: Final = DotenvConfig(
      path="%kernel.project_dir%/.env",
      env_key="APP_ENV",
      debug_key="APP_DEBUG",
      default_env="dev",
      test_envs=("test",),
      prod_envs=("prod",),
      debug_envs=("dev", "local", "test"),
  )


  @configure
  def dotenv() -> DotenvConfig:
      """Hand the container the one cascade description."""
      return DOTENV
  ```

  ```python
  # <app>/__main__.py — the first line of every entry point
  from app.config.packages.dotenv import DOTENV

  DOTENV.boot(PROJECT_DIR)  # only now import the kernel, settings, everything else
  ```

  `boot` resolves `%kernel.project_dir%` against the project directory itself — no container
  exists yet — and `dotenv:dump` and `debug:dotenv` read the same `DOTENV` from the container.
  Change the cascade in `config/packages/dotenv.py`, and nowhere else.
- **Activate** — `DotenvBundle: {"all": True}` in `BUNDLES` in `<app>/config/bundles.py`, imported
  from `xtr_dotenv.bundle`. It only adds `dotenv:dump` and `debug:dotenv`, and only when the
  console bundle is active.
- **Brings along** — nothing.
- **Configure** — `config/packages/dotenv.py`, written by the recipe (see *Load*).
  `debug_envs` are the environments where `boot` leaves `APP_DEBUG` on by default; everywhere
  else it stays off, and an explicit `APP_DEBUG` always wins. An environment declared nowhere
  (not `default_env`, not in `debug_envs`, `test_envs` or `prod_envs`) gets debug off plus a
  one-time `RuntimeWarning` naming it and the remedies. `dotenv:dump` stamps the description
  it was compiled from into the dump, and `boot` refuses — with a one-time warning — a dump
  whose stamp no longer matches, so a stale dump never silently loads.
- **Environment** — create `.env` with the defaults every machine shares, for example
  `APP_ENV=dev`, and commit it.
- **Ignore** — `.env.local`, `.env.*.local` and `.env.local.json`: per-machine overrides, and
  what `dotenv:dump` writes.
- **Remove** — drop the `BUNDLES` entry and every `DOTENV.boot(...)` call, delete
  `<app>/config/packages/dotenv.py`, then `uv remove xtr-dotenv`. The `.env` files stay yours.
- **Check** — `debug:dotenv` reports the environment, production and debug flags, and lists each
  file of the cascade as loaded or missing (values masked unless `--show-values`).

## Kernel / bundle

With [xtr-dependency-injection](../xtr-dependency-injection) installed beside the package — it is
not a dependency, and nothing outside `xtr_dotenv.bundle` and the commands it loads needs it — an
application lists `DotenvBundle` in its `app/config/bundles.py`. **The bundle does not load `.env`
files** — `DOTENV.boot(PROJECT_DIR)` runs before the kernel is built, on the one description
`config/packages/dotenv.py` holds (see [Use in an application](#use-in-an-application)). What the
bundle contributes is the two commands that need the kernel to know its project directory:

```sh
uv add xtr-dotenv xtr-dependency-injection xtr-console
```

```python
# app/config/bundles.py
from xtr_dotenv.bundle import DotenvBundle

BUNDLES = {DotenvBundle: {"all": True}}
```

| `DotenvConfig` field | Meaning |
| --- | --- |
| `path` | The base `.env` path; default `%kernel.project_dir%/.env` — the token is resolved against the project directory by `base_path()`, every other parameter reference by the kernel, and a relative path is taken from the project directory |
| `env_key` | The variable naming the active environment |
| `debug_key` | The variable naming debug mode |
| `default_env` | The environment the cascade settles on when the environment key names none |
| `test_envs` | Environments where the `.local` overlay is skipped |
| `prod_envs` | Environments declared production — read by `boot_env`'s undeclared-environment warning and the `debug:dotenv` report |
| `debug_envs` | Environments where `boot_env` leaves debug on by default; everywhere else it stays off |

### Commands

| Command | What it does |
| --- | --- |
| `dotenv:dump [env]` | Compile the cascade for `env` (default: the kernel's env) into `<path>.local.json`, stamped with the `default_env` and `test_envs` it was compiled from — `boot_env` refuses a dump whose stamp no longer matches. Runs on a fresh environ with only the env key, so real environment variables never land in the dump — but the `.local` files do, so gitignore it |
| `debug:dotenv [name] [--show-values]` | Report the environment, the default environment, whether it is production (`prod_envs`) and the debug flag (`debug_key`) — decided by the loader the config itself builds — then list the files the loader's own cascade considers (loaded / missing) and each variable's value per file, filtered by `name` when given. Values are masked unless `--show-values` is passed |

The commands are only registered when the console bundle is active — xtr-console installed
beside the package; on a headless application the bundle is still valid and boots at zero
config.

## Layout

```
xtr_dotenv/
├── dotenv.py                       the loader: parse, load, overload, populate, load_env, boot_env
├── dotenv_settings_source.py       a pydantic-settings source that runs the cascade in a sandbox
├── dotenv_settings.py              BaseSettings base declaring the cascade behind the real env
├── exception/                      DotenvError + FormatError, InvalidArgumentError, PathError, …
├── command/                        dotenv:dump and debug:dotenv (xtr-console commands)
└── bundle/                         DotenvBundle for xtr-dependency-injection
```

## Development

Developed in the [python-xtr](https://github.com/xterr/python-xtr) monorepo, under
`packages/xtr-dotenv`; run the commands below from there. The `python-xtr-dotenv`
repository is a read-only copy, so send issues and pull requests to the monorepo.

```sh
uv sync
uv run ruff check
uv run ruff format --check
uv run basedpyright
uv run ty check
uv run pytest
```

## License

MIT — see [LICENSE](LICENSE).
