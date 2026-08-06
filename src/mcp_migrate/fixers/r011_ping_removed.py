"""Fixer for R011 -- the removed ping request/response.

There is no mechanical replacement for a ping handler: the transport now
owns liveness, so the right fix is deletion, and deciding whether anything
else needs to fill that gap is a judgment call. So this fixer does the one
thing that's safe without understanding the surrounding code -- comment out
the dead PingRequest reference or "ping" dispatch branch and leave a TODO
pointing at cookbook/06-ping-removed.md. Confidence "review": every flagged
site still needs a human pass.
"""
from __future__ import annotations

import re
from pathlib import Path

from .base import Fixer, FixResult, comment_prefix, is_commented

SPEC_URL = "https://modelcontextprotocol.io/specification/2026-07-28/changelog"
COOKBOOK = "cookbook/06-ping-removed.md"
# No comment marker baked in -- R011 reads TypeScript, and a `#` written into
# a `.ts` file is a syntax error, not a comment. That was #117.
TODO_BODY = (
    "TODO(mcp-migrate): ping is removed from the protocol; liveness now rides "
    f"on the transport itself -- see {SPEC_URL} and {COOKBOOK}"
)

# Bounded, not `\w*`: the suffix exists for the TS SDK's Zod schema names
# (`PingRequestSchema`), but `\w*` also swallows `PingRequester`. The R011
# rule still has `\w*` -- that is #87. A fixer narrower than its rule is the
# safe direction; the reverse means `--write` edits what `check` calls clean.
PING_CODE_RX = re.compile(r"\bPingRequest(?:Params|Schema)?\b")
PING_DISPATCH_RX = re.compile(
    r"""method\s*===?\s*["']ping["']|case\s*["']ping["']|[{,]\s*["']ping["']\s*:"""
)


def _safe_to_comment_out(line: str) -> bool:
    """Commenting out must not leave a dangling suite or multiline expression."""
    stripped = line.rstrip("\n").rstrip()
    if stripped.endswith(":"):
        return False
    if stripped.endswith(("(", "[", "{", "\\")):
        return False
    return True


def _ping_hit(line: str) -> str | None:
    if PING_CODE_RX.search(line):
        return "removed PingRequest reference"
    if PING_DISPATCH_RX.search(line):
        return "removed ping JSON-RPC method dispatch"
    return None


class PingRemovedFixer(Fixer):
    rule_id = "R011"
    title = "Comment out removed PingRequest/ping usage, leave a TODO"
    confidence = "review"

    def fix(self, source: str, path: Path) -> FixResult:
        lines = source.splitlines(keepends=True)
        out: list[str] = []
        changes: list[str] = []
        prefix = comment_prefix(path)
        todo = f"{prefix}{TODO_BODY}"

        for i, raw_line in enumerate(lines, start=1):
            stripped = raw_line.lstrip(" \t")
            already_commented = is_commented(raw_line)
            ends_as_block_opener = raw_line.rstrip("\n").rstrip().endswith(":")
            hit = (
                None
                if already_commented or ends_as_block_opener
                else _ping_hit(raw_line)
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
