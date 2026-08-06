"""Fixer for R012 -- the removed logging/setLevel request.

Log level is now per-request (read off `_meta["io.modelcontextprotocol/logLevel"]`
on each incoming request) rather than one process-wide level set via
logging/setLevel. There's no mechanical way to thread that through an
arbitrary handler's control flow, so this fixer does the one safe thing:
comment out the actual SetLevelRequest reference or "logging/setLevel"
dispatch line and leave a TODO pointing at cookbook/07-logging-set-level-removed.md.
Confidence "review": every flagged site still needs a human pass.
"""
from __future__ import annotations

import re
from pathlib import Path

from .base import Fixer, FixResult

SPEC_URL = "https://modelcontextprotocol.io/specification/2026-07-28/changelog"
COOKBOOK = "cookbook/07-logging-set-level-removed.md"
TODO = (
    "# TODO(mcp-migrate): logging/setLevel is removed; read the log level off "
    f'_meta["io.modelcontextprotocol/logLevel"] on each request instead -- see '
    f"{SPEC_URL} and {COOKBOOK}"
)

SET_LEVEL_CODE_RX = re.compile(r"\bSetLevelRequest\w*")
SET_LEVEL_DISPATCH_RX = re.compile(
    r"""method\s*===?\s*["']logging/setLevel["']"""
    r"""|case\s*["']logging/setLevel["']"""
    r"""|[{,]\s*["']logging/setLevel["']\s*:"""
)


def _safe_to_comment_out(line: str) -> bool:
    """Commenting out must not leave a dangling suite or multiline expression."""
    stripped = line.rstrip("\n").rstrip()
    if stripped.endswith(":"):
        return False
    if stripped.endswith(("(", "[", "{", "\\")):
        return False
    return True


def _set_level_hit(line: str) -> str | None:
    if SET_LEVEL_CODE_RX.search(line):
        return "removed SetLevelRequest reference"
    if SET_LEVEL_DISPATCH_RX.search(line):
        return "removed logging/setLevel JSON-RPC method dispatch"
    return None


class LoggingSetLevelRemovedFixer(Fixer):
    rule_id = "R012"
    title = "Comment out removed SetLevelRequest/logging/setLevel usage, leave a TODO"
    confidence = "review"

    def fix(self, source: str, path: Path) -> FixResult:
        lines = source.splitlines(keepends=True)
        out: list[str] = []
        changes: list[str] = []

        for i, raw_line in enumerate(lines, start=1):
            stripped = raw_line.lstrip(" \t")
            already_commented = stripped.startswith(("#", "//"))
            ends_as_block_opener = raw_line.rstrip("\n").rstrip().endswith(":")
            hit = (
                None
                if already_commented or ends_as_block_opener
                else _set_level_hit(raw_line)
            )

            if hit:
                indent = raw_line[: len(raw_line) - len(stripped)]
                newline = "\n" if raw_line.endswith("\n") else ""
                body = stripped.rstrip("\n")
                todo_added = False

                if not (out and out[-1].strip(" \t\n") == TODO):
                    out.append(f"{indent}{TODO}{newline}")
                    todo_added = True
                if _safe_to_comment_out(raw_line):
                    out.append(f"{indent}# {body}{newline}")
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
