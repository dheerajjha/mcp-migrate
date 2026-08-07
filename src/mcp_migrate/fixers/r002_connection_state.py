"""Fixer for R002 -- per-connection state kept in a module-level dict.

There's no mechanical fix here: replacing the dict means picking a real
store (a DB table, redis, a keyed file) and deciding what the key even is
once there's no protocol session to derive it from, and a text editor
can't make either call. Same reasoning as R008 and R018's fixers -- what
*is* safe is finding the declaration and dropping a TODO right above it
pointing at the cookbook recipe. The dict itself is left untouched: it's
still valid code (just architecturally wrong), not something to comment
out. Confidence "review": every flagged declaration still needs a human
to design and thread through a real store.

Mirrors the R002 *rule*'s own module/class-level-assignment walk on
purpose (see `rules/r002_connection_state.py`, keyed off only by its rule
id string, not imported) so the fixer flags exactly what the rule flags,
no more and no less.
"""
from __future__ import annotations

import ast
from pathlib import Path

from .base import Fixer, FixResult, comment_prefix, is_commented

SPEC_URL = "https://github.com/modelcontextprotocol/modelcontextprotocol/pull/2567"
COOKBOOK = "cookbook/01-sessions-to-explicit-handles.md"
TODO = (
    "TODO(mcp-migrate): per-connection state in a module-level dict breaks "
    f"across replicas -- move it into a real store keyed by an explicit "
    f"handle, see {SPEC_URL} and {COOKBOOK}"
)

SUSPECT = ("sessions", "session_store", "_sessions", "connections", "session_state",
           "SESSIONS", "client_state", "per_session")

# Same scope boundary as the rule: don't descend into function/lambda
# bodies -- a dict built and thrown away inside a request handler isn't
# process-wide state, it just happens to share a suspect name.
SCOPE_BOUNDARY = (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda)


def _module_and_class_level_assigns(node: ast.AST):
    for child in ast.iter_child_nodes(node):
        if isinstance(child, (ast.Assign, ast.AnnAssign)):
            yield child
        if isinstance(child, SCOPE_BOUNDARY):
            continue
        yield from _module_and_class_level_assigns(child)


def _flagged_linenos(tree: ast.AST) -> set[int]:
    linenos: set[int] = set()
    for node in _module_and_class_level_assigns(tree):
        if isinstance(node, ast.AnnAssign):
            if node.value is None or not isinstance(node.value, (ast.Dict, ast.DictComp)):
                continue
            targets = [node.target]
        else:
            if not isinstance(node.value, (ast.Dict, ast.DictComp)):
                continue
            targets = node.targets
        for target in targets:
            if isinstance(target, ast.Name) and any(s in target.id for s in SUSPECT):
                linenos.add(node.lineno)
    return linenos


class PerConnectionStateFixer(Fixer):
    rule_id = "R002"
    title = "Annotate module-level per-connection state dicts with a TODO"
    confidence = "review"

    def fix(self, source: str, path: Path) -> FixResult:
        if path.suffix.lower() != ".py":
            return self.unchanged(source)  # R002 is a Python-only rule; nothing to AST-walk elsewhere

        try:
            tree = ast.parse(source)
        except SyntaxError:
            return self.unchanged(source)

        flagged = _flagged_linenos(tree)
        if not flagged:
            return self.unchanged(source)

        lines = source.splitlines(keepends=True)
        prefix = comment_prefix(path)
        todo = f"{prefix}{TODO}"
        out: list[str] = []
        changes: list[str] = []

        for i, raw_line in enumerate(lines, start=1):
            if (
                i in flagged
                and not is_commented(raw_line)
                and not (out and out[-1].strip(" \t\n") == todo)
            ):
                indent = raw_line[: len(raw_line) - len(raw_line.lstrip(" \t"))]
                newline = "\n" if raw_line.endswith("\n") else ""
                out.append(f"{indent}{todo}{newline}")
                changes.append(f"line {i}: annotated per-connection state dict with TODO")
            out.append(raw_line)

        if not changes:
            return self.unchanged(source)
        return self.result("".join(out), changes)
