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


def load_config(root: Path) -> Config:
    """Load project config, or an empty one carrying only its warnings.

    `pyproject.toml` wins if it exists at all, whether or not it actually
    configures anything -- a project that has one and simply doesn't use
    `[tool.mcp-migrate]` has given a complete answer ("nothing"), and going
    on to also read a standalone file next to it would make the two files
    silently fight over precedence. The standalone file is for projects
    that have no `pyproject.toml` in the first place, which given what this
    tool targets is most JavaScript and TypeScript ones.
    """
    pyproject_path = root / "pyproject.toml"
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
        return _empty()

    standalone_path = root / STANDALONE_FILENAME
    if standalone_path.is_file():
        data = _load_toml(standalone_path)
        if isinstance(data, list):
            return _empty(warnings=data)
        if isinstance(data, dict):
            return _parse_table(data, source=standalone_path)
        return _empty()

    return _empty()
