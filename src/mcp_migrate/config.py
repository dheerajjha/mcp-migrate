"""Project-level configuration.

Every preference below started life as a flag, and a flag has to be
retyped on every invocation and can't be shared with a team or with CI.
This reads `[tool.mcp-migrate]` from `pyproject.toml`, falling back to a
standalone `.mcp-migrate.toml` for projects with none -- which, since this
tool targets MCP servers, is most JavaScript/TypeScript projects.

Precedence is a flag beats config, config beats the built-in default.
Nothing here ever overrides a value the caller already has from a flag --
see how `run_check_detailed` in `cli.py` merges `include_tests`.

```toml
[tool.mcp-migrate]
skip = ["vendor/", "generated/"]
include-tests = false

[tool.mcp-migrate.rules]
R008 = "off"                                          # no reason recorded
R016 = "off -- ttl is enforced by the gateway in front of this"  # recorded
```

A disabled rule never runs, rather than running and having its findings
discarded after the fact -- the same distinction `SKIP_DIRS` draws between
"never opened" and "opened, ignored". It costs nothing against the grade
and is never mistaken for a pass, because it never produces one.
"""
from __future__ import annotations

import difflib
import re
from dataclasses import dataclass, field
from pathlib import Path

try:
    import tomllib
except ImportError:
    try:
        import tomli as tomllib  # type: ignore
    except ImportError:
        tomllib = None

from .suppress import RULE_ID_RX

STANDALONE_FILENAME = ".mcp-migrate.toml"

# Mirrors suppress.py's `ignore[R001] -- reason` shape on purpose: this is
# the second place in the tool where a rule id gets an optional trailing
# reason, and reusing the separator means someone who has already learned
# one learns both.
_OFF_RX = re.compile(r"^(?:off|disabled|false)\s*(?:(?:--|:)\s*(?P<reason>.+))?$", re.IGNORECASE)
_ON_RX = re.compile(r"^(?:on|enabled|true)$", re.IGNORECASE)

# Every key `_parse_table` actually consumes. Both spellings of the tests
# toggle are accepted (the reader takes either); the dash form is the one
# the docstring and README use, so it is the only one a "did you mean"
# hint ever suggests back.
_KNOWN_KEYS = frozenset({"skip", "include-tests", "include_tests", "rules"})
_HINT_KEYS = ("skip", "include-tests", "rules")


@dataclass
class Config:
    skip: frozenset[str] = frozenset()
    include_tests: bool = False
    disabled_rules: dict[str, str] = field(default_factory=dict)  # rule id -> reason ("" if none given)
    source: Path | None = None
    warnings: list[str] = field(default_factory=list)


def _empty(*, source: Path | None = None, warnings: list[str] | None = None) -> Config:
    return Config(source=source, warnings=warnings or [])


def _parse_table(table: dict, *, source: Path) -> Config:
    warnings: list[str] = []

    skip: set[str] = set()
    skip_raw = table.get("skip", [])
    if isinstance(skip_raw, list):
        for entry in skip_raw:
            if isinstance(entry, str) and entry.strip():
                skip.add(entry.strip().strip("/"))
            else:
                warnings.append(f"{source}: `skip` entries must be strings, ignoring {entry!r}")
    elif skip_raw:
        warnings.append(f"{source}: `skip` must be a list of strings, ignoring")

    include_tests = table.get("include-tests", table.get("include_tests", False))
    if not isinstance(include_tests, bool):
        warnings.append(f"{source}: `include-tests` must be true or false, ignoring {include_tests!r}")
        include_tests = False

    disabled: dict[str, str] = {}
    rules_table = table.get("rules", {})
    if isinstance(rules_table, dict):
        for rule_id, value in rules_table.items():
            if not RULE_ID_RX.match(rule_id):
                warnings.append(f"{source}: not a rule id, ignoring [rules] entry {rule_id!r}")
                continue
            if isinstance(value, bool):
                value = "on" if value else "off"
            if not isinstance(value, str):
                warnings.append(
                    f"{source}: rules.{rule_id} = {value!r} is not understood -- "
                    f'use "off" to disable a rule'
                )
                continue
            m_off = _OFF_RX.match(value.strip())
            if m_off:
                disabled[rule_id.upper()] = (m_off.group("reason") or "").strip()
            elif not _ON_RX.match(value.strip()):
                warnings.append(
                    f'{source}: rules.{rule_id} = {value!r} is not understood -- '
                    f'use "off" to disable a rule (anything else is a no-op)'
                )
    elif rules_table:
        warnings.append(f"{source}: `[rules]` must be a table, ignoring")

    # A key this parser doesn't consume used to fall off the end in silence
    # -- the one misconfiguration the module let pass without the scrutiny it
    # already applies one level down in `[rules]`. That silence is worse here
    # than for an ordinary typo'd setting: a `skip` that never took effect or
    # a rule toggle that never applied leaves the published grade different
    # from the configured one, with no output that differs to reveal it, in a
    # tool whose entire proposition is that the grade is trustworthy. So warn
    # for every unrecognised key, and where the key is a recognisable mistake
    # rather than noise, say what the right shape is.
    is_standalone = source.name == STANDALONE_FILENAME
    rules_label = "[rules]" if is_standalone else "[tool.mcp-migrate.rules]"
    for key in table:
        if key in _KNOWN_KEYS:
            continue
        if RULE_ID_RX.match(key):
            warnings.append(
                f"{source}: {key!r} is a rule id at the top level, ignoring "
                f"-- rule toggles go in the {rules_label} table"
            )
        elif key == "tool" and is_standalone:
            warnings.append(
                f"{source}: unknown setting 'tool', ignoring -- "
                f"`[tool.mcp-migrate]` is the pyproject.toml spelling; in "
                f"{STANDALONE_FILENAME} the settings are top level "
                f"(`skip`, `include-tests`, and a `[rules]` table)"
            )
        else:
            near = difflib.get_close_matches(key, _HINT_KEYS, n=1)
            hint = f" -- did you mean {near[0]!r}?" if near else ""
            warnings.append(f"{source}: unknown setting {key!r}, ignoring{hint}")

    return Config(
        skip=frozenset(skip), include_tests=include_tests,
        disabled_rules=disabled, source=source, warnings=warnings,
    )


def _load_toml(path: Path) -> dict | None | list[str]:
    """The parsed table, or a one-element list of warnings if it couldn't be read."""
    try:
        content = path.read_text(encoding="utf-8", errors="replace")
    except OSError as e:
        return [f"{path}: could not read config ({e})"]
    if tomllib is None:
        return [f"{path}: no TOML parser available (tomllib/tomli) -- config not read"]
    try:
        return tomllib.loads(content)
    except Exception as e:  # tomllib raises tomllib.TOMLDecodeError, tomli similar
        return [f"{path}: invalid TOML, ignoring config ({e})"]


def _load_config_at(level: Path) -> Config | None:
    """Load config from one directory, or None if nothing there decides.

    `pyproject.toml` wins at a level if it exists at all, whether or not it
    actually configures anything -- a project that has one and simply
    doesn't use `[tool.mcp-migrate]` has given a complete answer
    ("nothing") for that level, and going on to also read a standalone file
    next to it would make the two files silently fight over precedence.
    A section-less `pyproject.toml` returns None rather than an empty
    config: in a monorepo the inner `pyproject.toml` is a packaging file
    that says nothing about this tool, and treating its silence as an
    answer would make `check src/` silently ignore the repo's real config.
    """
    pyproject_path = level / "pyproject.toml"
    if pyproject_path.is_file():
        data = _load_toml(pyproject_path)
        if isinstance(data, list):
            return _empty(warnings=data)
        tool_table = data.get("tool") if isinstance(data, dict) else None
        section = None
        if isinstance(tool_table, dict):
            section = tool_table.get("mcp-migrate") or tool_table.get("mcp_migrate")
        if isinstance(section, dict):
            return _parse_table(section, source=pyproject_path)
        return None

    standalone_path = level / STANDALONE_FILENAME
    if standalone_path.is_file():
        data = _load_toml(standalone_path)
        if isinstance(data, list):
            return _empty(warnings=data)
        if isinstance(data, dict):
            return _parse_table(data, source=standalone_path)
        return _empty()

    return None


def load_config(root: Path) -> Config:
    """Load project config, or an empty one carrying only its warnings.

    The config is searched for by walking up from `root`, so `check src/`
    finds the repo's config at the repo root the way ruff, mypy, eslint, and
    black all do. The walk stops at the first directory containing a `.git`
    (the repo root), with the filesystem root as the backstop -- a stray
    file in a parent directory outside the repo must never quietly change
    someone's grade.
    """
    current = root.resolve()
    while True:
        found = _load_config_at(current)
        if found is not None:
            return found
        if (current / ".git").exists() or current.parent == current:
            return _empty()
        current = current.parent
