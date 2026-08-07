"""Fixer for R019 -- removed tasks/list and blocking tasks/result.

There is no mechanical replacement for a blocking wait: the 2026-07-28
spec replaces it with a tasks/get + tasks/update polling loop, and tasks
moved into the io.modelcontextprotocol/tasks extension. So this fixer does
the one thing that is safe without understanding the surrounding control
flow -- flag each flagged call site with a loud TODO and comment out the
line when that cannot break a multiline expression. Confidence "review":
every flagged site still needs a human pass.
"""
from __future__ import annotations

import re
from pathlib import Path

from ._textedit import string_lines
from .base import Fixer, FixResult, comment_prefix, is_commented

SPEC_URL = "https://modelcontextprotocol.io/specification/2026-07-28/changelog"
COOKBOOK = "cookbook/11-tasks-polling.md"
TODO = (
    "TODO(mcp-migrate): tasks/list and blocking tasks/result are removed; "
    f"poll with tasks/get + tasks/update and declare io.modelcontextprotocol/tasks "
    f"under extensions — see {SPEC_URL} and {COOKBOOK}"
)

TASKS_CODE_RX = re.compile(r"\bListTasksRequest\b|\bGetTaskPayloadRequest\b")
TASKS_WIRE_RX = re.compile(r"""["']tasks/(?:list|result)["']""")


def _safe_to_comment_out(line: str) -> bool:
    """Commenting out must not leave a dangling suite or multiline expression."""
    stripped = line.rstrip("\n").rstrip()
    if stripped.endswith(":"):
        return False
    if stripped.endswith(("(", "[", "{", "\\")):
        return False
    return True


def _tasks_hit(line: str) -> str | None:
    if TASKS_CODE_RX.search(line):
        return "removed tasks SDK request type"
    if TASKS_WIRE_RX.search(line):
        return "removed tasks/list or blocking tasks/result method"
    return None


class TasksPollingFixer(Fixer):
    rule_id = "R019"
    title = "Comment out removed tasks/list or blocking tasks/result usage, leave a TODO"
    confidence = "review"

    def fix(self, source: str, path: Path) -> FixResult:
        lines = source.splitlines(keepends=True)
        out: list[str] = []
        changes: list[str] = []

        prefix = comment_prefix(path)
        todo = f"{prefix}{TODO}"
        # #105: a `#` inside a string literal opens no comment, so a TODO
        # written there silently edits the user's prose instead of
        # annotating their code.
        str_lines = string_lines(source, path)

        for i, raw_line in enumerate(lines, start=1):
            stripped = raw_line.lstrip(" \t")
            already_commented = i in str_lines or is_commented(raw_line)
            ends_as_block_opener = raw_line.rstrip("\n").rstrip().endswith(":")
            hit = (
                None
                if already_commented or ends_as_block_opener
                else _tasks_hit(raw_line)
            )

            if hit:
                indent = raw_line[: len(raw_line) - len(stripped)]
                newline = "\n" if raw_line.endswith("\n") else ""
                body = stripped.rstrip("\n")
                todo_added = False

                if not (out and out[-1].strip(" \t\n") == todo):
                    out.append(f"{indent}{todo}{newline}")
                    todo_added = True
                if _safe_to_comment_out(raw_line):
                    out.append(f"{indent}{prefix}{body}{newline}")
                    changes.append(f"line {i}: commented out {hit}, added TODO")
                elif todo_added:
                    out.append(raw_line)
                    changes.append(f"line {i}: added TODO for {hit}")
                else:
                    out.append(raw_line)
            else:
                out.append(raw_line)

        new_text = "".join(out)
        if not changes:
            return self.unchanged(source)
        return self.result(new_text, changes)
