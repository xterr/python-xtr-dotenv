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
- ⚡ **A dumped fast path** — `dotenv:dump` writes the compiled cascade to `.env.local.json`;
  `boot_env` reads that one file instead of the cascade.

## Install

```sh
uv add xtr-dotenv                 # the loader and the settings source
uv add "xtr-dotenv[di]"           # + a DotenvBundle for xtr-dependency-injection
uv add "xtr-dotenv[console]"      # + the dotenv:dump and debug:dotenv commands
```

Requires Python 3.11+.

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
| 2 | *(reads env key from environ; defaults to `default_env`)* | |
| 3 | `path.local` | Only outside `test_envs` — a developer's per-machine overrides |
| 4 | *(re-reads env key)* | The `.local` file may have set a different environment |
| 5 | `path.{env}` | When `env` is not `"local"` |
| 6 | `path.{env}.local` | Same — a per-machine override for that environment |

Later files override earlier ones. A **real** environment variable always wins over any file
unless `override_existing_vars=True` is passed. `XTR_DOTENV_VARS` tracks which names came
from a file so a later file may replace them; `XTR_DOTENV_PATH` records the base path so
tooling can find it.

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
default) — it does not cycle. Anything still unresolved after five passes is a real cycle and
raises `VariableCircularReferenceError`.

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
`os.environ`.**

## Errors

Everything the library raises derives from `DotenvError`, and carries the data as typed
attributes.

| Error | Raised when |
| --- | --- |
| `FormatError` | A line cannot be parsed (bad binding, key without `=`); carries `.path`, `.line`, `.reason` |
| `PathError` | A file cannot be read; carries `.path` |
| `VariableCircularReferenceError` | Variables reference each other and never resolve; carries `.names` |

`FormatError` and `VariableCircularReferenceError` are also `ValueError`s; `PathError` is
also `OSError`. Existing `except` blocks keep working.

## Kernel / bundle

An application using [xtr-dependency-injection](../xtr-dependency-injection) lists
`DotenvBundle` in its `app/bundles.py`. **The bundle does not load `.env` files** —
`Dotenv().boot_env(...)` runs before the kernel is built. What the bundle contributes is
the two commands that need the kernel to know its project directory:

```sh
uv add "xtr-dotenv[di,console]"
```

```python
# app/bundles.py
from xtr_dotenv.bundle import DotenvBundle

BUNDLES = {DotenvBundle: {"all": True}}
```

```python
# app/config/dotenv.py
from xtr_dependency_injection import configure
from xtr_dotenv.bundle import DotenvConfig


@configure
def dotenv() -> DotenvConfig:
    return DotenvConfig(path="%kernel.project_dir%/.env", env_key="APP_ENV")
```

| `DotenvConfig` field | Meaning |
| --- | --- |
| `path` | The base `.env` path; default `%kernel.project_dir%/.env` — parameter references are resolved by the kernel, and a relative path is taken from the project directory |
| `env_key` | The variable naming the active environment |
| `debug_key` | The variable naming debug mode |
| `test_envs` | Environments where the `.local` overlay is skipped |
| `prod_envs` | Environments considered production, used for debug defaulting |

### Commands

| Command | What it does |
| --- | --- |
| `dotenv:dump [env]` | Compile the cascade for `env` (default: the kernel's env) into `<path>.local.json`. Runs on a fresh environ with only the env key, so real secrets never land in the dump |
| `debug:dotenv [name]` | List the files that apply in cascade order (loaded / missing) and each variable's value per file, filtered by `name` when given |

The commands are only registered when the console bundle is active; on a headless
application the bundle is still valid and boots at zero config.

## Layout

```
xtr_dotenv/
├── dotenv.py                       the loader: parse, load, overload, populate, load_env, boot_env
├── dotenv_settings_source.py       a pydantic-settings source that runs the cascade in a sandbox
├── dotenv_settings.py              BaseSettings base declaring the cascade behind the real env
├── exception/                      DotenvError + FormatError, PathError, VariableCircularReferenceError
├── command/                        dotenv:dump and debug:dotenv (xtr-console commands)
└── bundle/                         DotenvBundle for xtr-dependency-injection
```

## Development

Developed in the [python-xtr](https://github.com/xterr/python-xtr) monorepo, under
`packages/xtr-dotenv`; run the commands below from there. The `python-xtr-dotenv`
repository is a read-only copy, so send issues and pull requests to the monorepo.

```sh
uv sync --all-extras
uv run ruff check
uv run ruff format --check
uv run basedpyright
uv run ty check
uv run pytest
```

## License

MIT — see [LICENSE](LICENSE).
