"""Static guards against traps found in the rules -- not behavioural tests.

#123 and #143 were the same shape twice: a rule compiled a pattern with a
flag (`re.compile(..., re.IGNORECASE)`), then passed only `RX.pattern` -- a
plain string -- into `search_code`/`search_wire`/`search`. Those methods
recompile the string with `flags=0`, so the flag silently never took effect.
Nothing caught it either time; the tests passed and the rule quietly
under-reported. See #173.
"""
from __future__ import annotations

import ast
from pathlib import Path

RULES_DIR = Path(__file__).parent.parent / "src" / "mcp_migrate" / "rules"
SEARCH_METHODS = {"search", "search_code", "search_wire"}


def _compiled_names_with_flags(tree: ast.Module) -> set[str]:
    """Module-level `NAME = re.compile(pattern, <flags>)` where a flag is
    actually passed (positionally or via `flags=`)."""
    names: set[str] = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Assign):
            continue
        call = node.value
        if not isinstance(call, ast.Call):
            continue
        func = call.func
        if not (isinstance(func, ast.Attribute) and func.attr == "compile"
                and isinstance(func.value, ast.Name) and func.value.id == "re"):
            continue
        has_flags = len(call.args) >= 2 or any(kw.arg == "flags" for kw in call.keywords)
        if not has_flags:
            continue
        for target in node.targets:
            if isinstance(target, ast.Name):
                names.add(target.id)
    return names


def _dropped_flag_call_lines(tree: ast.Module, flagged_names: set[str]) -> list[int]:
    """Calls of the shape `search_*(NAME.pattern, ...)` where NAME is a
    flag-carrying compiled pattern and the call doesn't forward `flags=`."""
    offenders: list[int] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if not (isinstance(func, ast.Attribute) and func.attr in SEARCH_METHODS):
            continue
        if not node.args:
            continue
        first = node.args[0]
        if not (isinstance(first, ast.Attribute) and first.attr == "pattern"
                and isinstance(first.value, ast.Name) and first.value.id in flagged_names):
            continue
        if not any(kw.arg == "flags" for kw in node.keywords):
            offenders.append(node.lineno)
    return offenders


def test_no_rule_drops_a_compiled_flag_by_passing_only_dot_pattern():
    violations: dict[str, list[int]] = {}
    for path in sorted(RULES_DIR.glob("*.py")):
        if path.name == "base.py":
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        flagged_names = _compiled_names_with_flags(tree)
        if not flagged_names:
            continue
        offenders = _dropped_flag_call_lines(tree, flagged_names)
        if offenders:
            violations[path.name] = offenders

    assert not violations, (
        "search_code()/search_wire()/search() recompile a pattern string with "
        "flags=0 -- passing only `RX.pattern` from a flag-carrying re.compile(...) "
        "silently drops the flag (this is what happened in #123 and #143). "
        "Pass `flags=...` alongside `.pattern`, or call `RX.search()` directly. "
        f"Offending files/lines: {violations}"
    )
