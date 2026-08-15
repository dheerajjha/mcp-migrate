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

from ._textedit import strip_import_members
from .base import Fixer, FixResult, comment_prefix, is_commented

SPEC_URL = "https://modelcontextprotocol.io/specification/2026-07-28/changelog"
COOKBOOK = "cookbook/07-logging-set-level-removed.md"
# No comment marker baked in -- R012 reads TypeScript, and a `#` written into
# a `.ts` file is a syntax error, not a comment. That was #117.
TODO_BODY = (
    "TODO(mcp-migrate): logging/setLevel is removed; read the log level off "
    f'_meta["io.modelcontextprotocol/logLevel"] on each request instead -- see '
    f"{SPEC_URL} and {COOKBOOK}"
)

# Bounded, not `\w*`. This one matters more than most: `SetLevelRequester...`
# is not a block opener, so nothing downstream stops the line from being
# commented out entirely -- a working call site disappears rather than merely
# picking up a wrong TODO. The R012 rule still has `\w*`; that is #87.
SET_LEVEL_CODE_RX = re.compile(r"\bSetLevelRequest(?:Params|Schema)?\b")
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
        prefix = comment_prefix(path)
        todo = f"{prefix}{TODO_BODY}"
        # Remove import members from a parenthesised list rather than
        # commenting them out, so `from x import ( )` is never produced (#245).
        lines, changes = strip_import_members(lines, _set_level_hit, todo, "SetLevelRequest/logging/setLevel")

        for i, raw_line in enumerate(lines, start=1):
            stripped = raw_line.lstrip(" \t")
            already_commented = is_commented(raw_line)
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
