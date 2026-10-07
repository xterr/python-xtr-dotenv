---
name: xtr-dotenv
description: How to layer .env files into the environment and read them as a typed settings model with xtr-dotenv. Use when an application needs .env, .env.local, .env.dev or .env.prod files, an APP_ENV / APP_DEBUG environment flag, per-machine or per-environment overrides, variable expansion such as ${VAR:-default}, a pydantic-settings model fed from those files, secrets kept out of code, a dotenv:dump fast path, or when adding DotenvBundle to an application on xtr-dependency-injection.
---

# xtr-dotenv

Settings live in files, layered so a laptop, a CI runner and a production host each end up with
what suits them. `Dotenv` is the loader every layer runs through; `DotenvSettings` feeds a typed
model from the same layers without ever writing into `os.environ`.

## Quick reference

- Entry point, first line: `Dotenv().boot_env(str(PROJECT_DIR / ".env"))`. Before the kernel,
  before any settings model, before anything reads a variable.
- Layers, later wins: `.env` → `.env.local` → `.env.{env}` → `.env.{env}.local`. A real
  environment variable beats all of them.
- A typed model: subclass `DotenvSettings`, set the `_dotenv_*` class variables.
- A test: hand the loader its own mapping — `Dotenv(environ={})` touches nothing else.
- Commands (with the `console` extra and `DotenvBundle`): `dotenv:dump`, `debug:dotenv`.

## The cascade

`load_env(path)` and `boot_env(path)` read, in order:

| # | File | Applies |
| --- | --- | --- |
| 1 | `path` | Always — `path.dist` instead when `path` is missing |
| 2 | `path.local` | Outside `test_envs`; per-machine overrides |
| 3 | `path.{env}` | When the environment is not `local` |
| 4 | `path.{env}.local` | Same; per-machine, per-environment |

The environment comes from `env_key` (`APP_ENV` by default), read after file 1 and again after
file 2 — `.env.local` may change it. An unset **or empty** `env_key` names no environment, so
`default_env` takes over; every other real variable wins over the files whatever its value,
empty included. Files 3 and 4 were chosen by that environment, so one of them setting
`env_key` to something else is a `FormatError`. Which files to commit:

| File | Commit | Holds |
| --- | --- | --- |
| `.env` | yes | Defaults every machine shares, e.g. `APP_ENV=dev` |
| `.env.dev`, `.env.test`, `.env.prod` | yes | Per-environment defaults, no secrets |
| `.env.local`, `.env.*.local` | no | One machine's overrides |
| `.env.local.json` | no | What `dotenv:dump` writes |

Put the three ignored patterns in `.gitignore`. Real secrets belong in the process environment
or a mounted file, never in a committed layer.

## Load at the entry point

```python
# <app>/__main__.py
from xtr_dotenv import Dotenv


def main() -> None:
    Dotenv(env_key="APP_ENV", debug_key="APP_DEBUG").set_prod_envs(("prod",)).boot_env(
        str(PROJECT_DIR / ".env"), default_env="dev", test_envs=("test",)
    )

    from app.kernel import kernel  # only now — imports read the environment

    raise SystemExit(kernel.run(...))
```

`boot_env` also writes the debug key as `"1"` or `"0"`: its own value read as a flag
(`1/true/yes/on`, or a non-zero number) when set, otherwise on in every environment outside
`prod_envs`. If `<path>.local.json` exists and names the current environment, it is read instead
of the cascade.

Other calls on the loader:

| Call | Does |
| --- | --- |
| `load(path, *extra)` | Load named files; real variables win |
| `overload(path, *extra)` | Same, but the files win |
| `load_env(path, ...)` | The cascade, no debug key, no dump fast path |
| `cascade(path, ...)` | Return `(env, files)` without loading anything |
| `parse(data, path)` | Expand one file's text into a `dict[str, str]` |
| `populate(values, override_existing_vars=False)` | Write a mapping under the same rules |

The loader writes two bookkeeping names: `XTR_DOTENV_VARS` (which names came from a file, so a
later file may replace them) and `XTR_DOTENV_PATH` (the base path, for tooling).

## Expansion

| Written | Means |
| --- | --- |
| `$VAR`, `${VAR}` | `VAR`'s value, empty when unset |
| `${VAR:-default}` | `default` when `VAR` is unset or empty |
| `${VAR:=default}` | The same, and `VAR` is recorded as `default` for later lookups |
| `\$` | A literal dollar |

```sh
SHOP_HOST=localhost
SHOP_EMAIL=support@${SHOP_HOST}
DATABASE_URL=postgres://u:${DB_PASSWORD:-change-me}@${SHOP_HOST}/db
SHOP_PASSWORD='p@$$w0rd'          # single quotes: never expanded
SHOP_BUILD_USER=$(whoami)         # kept as text, never run
```

- Expansion runs after every file is read, so `.env` may reference a name only `.env.local` sets.
- A default is plain text: a quote, a brace or a `$` inside one, or a `${` never closed, is a
  `FormatError` naming the line.
- `A=${A:-x}` reads what `A` is now; it does not cycle. Names genuinely waiting on each other
  raise `VariableCircularReferenceError`.
- A value spanning lines must be quoted.

## A typed settings model

```python
from typing import ClassVar

from pydantic_settings import SettingsConfigDict
from xtr_dotenv import DotenvSettings


class AppSettings(DotenvSettings):
    _dotenv_path: ClassVar[str] = "/srv/app/.env"
    _dotenv_env_key: ClassVar[str] = "APP_ENV"
    _dotenv_default_env: ClassVar[str] = "dev"
    _dotenv_test_envs: ClassVar[tuple[str, ...]] = ("test",)

    model_config: ClassVar[SettingsConfigDict] = SettingsConfigDict(
        env_prefix="SHOP_", extra="ignore", frozen=True
    )

    database_url: str
    log_level: str = "INFO"
```

Priority: init keyword arguments > real environment variables > the cascade > secret files >
field defaults. Nothing the source reads lands in `os.environ`. Register the model as a
singleton (`@as_service def app_settings() -> AppSettings: return AppSettings()`) so the cascade
is read once. To place the source yourself in `settings_customise_sources`, use
`DotenvSettingsSource(settings_cls, path=..., env_key=...)`; it forwards `case_sensitive`,
`env_prefix`, `env_nested_delimiter` and friends.

## Commands

| Command | Does |
| --- | --- |
| `dotenv:dump [env]` | Compile the cascade for `env` (default: the kernel's) into `<path>.local.json`, which `boot_env` then reads instead of the files. Computed on a fresh environ holding only the env key, so no real variable lands in it — the `.local` layers do, so keep it out of git |
| `debug:dotenv [name] [--show-values]` | Report the environment, whether it is production (`prod_envs`) and the debug flag (`debug_key`), then list every cascade file as loaded or missing and each variable's value per file, filtered to `name` when given. Values are masked unless `--show-values` |

Both need `DotenvBundle` and an active console bundle.

## Testing

Give the loader its own mapping and nothing in the process can see it:

```python
def test_the_cascade_fills_in_a_default(tmp_path) -> None:
    (tmp_path / ".env").write_text("APP_ENV=dev\nDSN=postgres://u:${PW:-change-me}@db/x\n")
    sandbox: dict[str, str] = {}

    Dotenv(environ=sandbox).load_env(str(tmp_path / ".env"))

    assert sandbox["DSN"] == "postgres://u:change-me@db/x"
```

- `parse("A=1\nB=${A}!\n")` expands without reading or writing a file, for a test about the
  grammar alone.
- `cascade(path)` asserts which files would be read, in order, without loading them.
- Put test values in `.env.test`: the `.local` overlay is skipped in `test_envs`, so every
  machine runs the suite on the same values.

## Use in an application

`uv run xtr-recipes recipes:sync` applies the recipe shipped with this package: it lists
`DotenvBundle`, writes `APP_ENV` in `.env`, and ignores the per-machine `.env.local` files. That is
the steps below a recipe can do; the load step it prints for you to make.

1. **Install** — `uv add "xtr-dotenv[di,console]"`. Plain `xtr-dotenv` gives the loader and the
   settings source; `di` adds the bundle, `console` the two commands.
2. **Load** — the bundle loads nothing. Call `Dotenv().boot_env(...)` at the top of *every*
   entry point, before the kernel is built.
3. **Activate** — `DotenvBundle: {"all": True}` in `BUNDLES` in `<app>/bundles.py`
   (`from xtr_dotenv.bundle import DotenvBundle`). It only contributes the commands.
4. **Brings along** — nothing.
5. **Configure** — optional; by default the base file is `%kernel.project_dir%/.env` and the
   environment comes from `APP_ENV`:

   ```python
   # <app>/config/dotenv.py
   from xtr_dependency_injection import configure
   from xtr_dotenv.bundle import DotenvConfig


   @configure
   def dotenv() -> DotenvConfig:
       return DotenvConfig(
           path="%kernel.project_dir%/.env",
           env_key="APP_ENV",
           debug_key="APP_DEBUG",
           test_envs=("test",),
           prod_envs=("prod",),
       )
   ```

   Keep these fields and the `boot_env(...)` arguments in step — share constants between the two.
6. **Environment** — commit a `.env` with the defaults every machine shares, e.g. `APP_ENV=dev`.
   The commands describe that cascade; they do not replace step 2.
7. **Ignore** — add `.env.local`, `.env.*.local` and `.env.local.json` to `.gitignore`.
8. **Check** — `debug:dotenv` reports the environment, production and debug flags, and lists each
   cascade file as loaded or missing (values masked unless `--show-values`); `debug:bundles` shows
   `dotenv` as `active`.
9. **Remove** — drop the `BUNDLES` entry and every `boot_env(...)` call, delete
   `<app>/config/dotenv.py`, then `uv remove xtr-dotenv`. The `.env` files stay yours.

## Errors

All derive from `DotenvError` and carry typed attributes:

| Error | Raised when |
| --- | --- |
| `FormatError` | A line cannot be parsed, a key has no `=`, an overlay names another environment (`.path`, `.line`, `.reason`) |
| `InvalidArgumentError` | A `DotenvConfig` field is empty (`.reason`) |
| `PathError` | A file cannot be read, or the dump written (`.path`) |
| `VariableCircularReferenceError` | Values wait on each other forever (`.names`) |

`FormatError`, `InvalidArgumentError` and `VariableCircularReferenceError` are also `ValueError`s;
`PathError` is also an `OSError`.

## Do not

- Do not call `boot_env` after importing the kernel or a settings model — they read the
  environment as they import.
- Do not commit `.env.local`, `.env.*.local` or `.env.local.json`, and do not put a real secret
  in a committed layer.
- Do not expect the bundle to load files; it only adds the commands.
- Do not reach for `overload()` to fix a value a real environment variable is winning — fix the
  variable. `overload` discards it.
- Do not write `$(command)` expecting it to run, and do not single-quote a value you want
  expanded.
