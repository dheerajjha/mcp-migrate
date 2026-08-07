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


# --- one module per rule id ------------------------------------------------
#
# #219: two modules declared R001 and two declared R006 -- the 0.1.0
# originals, superseded but never deleted. `all_rules()` ends with
# `{r.id: r for r in rules}`, which keeps the *last* write, and
# `pkgutil.iter_modules` yields modules in sorted name order. So
# `r001_session_id_removed` was imported after `r001_session_id` and won.
#
# The count was right and the maintained implementations were the live
# ones -- by filename sort order. Rename the surviving module to something
# that sorts earlier and the tool silently reverts to a superseded rule,
# with the rule count unchanged and every test still green. That is the
# failure this guard exists to make impossible.

def _declared_rule_ids() -> dict[str, list[str]]:
    """Map rule id -> the modules that declare it, read from source.

    Deliberately static rather than importing `all_rules()`: the dedup this
    guards against happens *during* that import, so asking the imported
    result would only ever see the winner.
    """
    by_id: dict[str, list[str]] = {}
    for path in sorted(RULES_DIR.glob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not isinstance(node, ast.ClassDef):
                continue
            for stmt in node.body:
                if not isinstance(stmt, ast.Assign) or len(stmt.targets) != 1:
                    continue
                target = stmt.targets[0]
                if not (isinstance(target, ast.Name) and target.id == "id"):
                    continue
                if isinstance(stmt.value, ast.Constant) and isinstance(
                    stmt.value.value, str
                ):
                    by_id.setdefault(stmt.value.value, []).append(path.name)
    return by_id


def test_no_rule_id_is_declared_by_two_modules():
    duplicates = {
        rule_id: modules
        for rule_id, modules in _declared_rule_ids().items()
        if len(modules) > 1
    }
    assert not duplicates, (
        "two modules declare the same rule id; which one is live is decided "
        "by filename sort order inside all_rules(), not by intent: "
        f"{duplicates}"
    )


def test_every_declared_rule_id_survives_into_all_rules():
    """No rule is declared on disk and then silently dropped at import."""
    from mcp_migrate.rules import all_rules

    declared = set(_declared_rule_ids())
    live = {r.id for r in all_rules()}
    assert declared == live, (
        f"declared but not live: {sorted(declared - live)}; "
        f"live but not declared: {sorted(live - declared)}"
    )
