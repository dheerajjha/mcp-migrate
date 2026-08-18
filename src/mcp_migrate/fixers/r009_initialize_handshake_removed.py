"""Fixer for R009 -- initialize / notifications/initialized handshake removed.

There is no mechanical replacement for the handshake itself: the server has
to advertise its protocol versions, capabilities and identity through
server/discover instead, and only a human can say what those actually are.
So this fixer does the one thing that is safe without understanding the
surrounding code -- neutralize the dead handshake code and the
`notifications/initialized` wire references with a loud TODO, the same
comment-out-don't-delete approach `r001_session_id.py` uses. Deleting the
handler outright risks leaving a dangling reference elsewhere in the file
(an import, a registration call) that a text-level fixer can't safely
trace; commenting out is reversible and loud. Confidence "review": every
flagged site still needs a human pass to wire up server/discover.
"""
from __future__ import annotations

import re
from pathlib import Path

from ._textedit import strip_import_members
from .base import Fixer, FixResult, comment_prefix, is_commented

SPEC_URL = "https://modelcontextprotocol.io/specification/2026-07-28/changelog"
COOKBOOK = "cookbook/02-initialize-to-server-discover.md"
TODO = (
    "TODO(mcp-migrate): the initialize/notifications/initialized handshake is "
    f"removed; advertise capabilities via server/discover instead, see {SPEC_URL} "
    f"and {COOKBOOK}"
)

# A bounded suffix, not `\w*`. The suffix has to be here at all because the
# TypeScript SDK exports Zod schema names (`InitializeRequestSchema`) and a
# bare `\b...\b` cannot match inside one -- but the enumerated set is what
# the SDK actually exports, and `\w*` would additionally swallow anything
# that merely starts the same way.
#
# The R009 rule's TS branch still uses `\w*` (that is #87, open). A fixer
# being narrower than its rule is the safe direction: `check` may report a
# line `fix` declines to touch. The reverse -- what `\w*` gives you here --
# means `fix --write` edits a line `check` graded clean, which for this
# fixer meant commenting out `helper = InitializeRequesterHelper()` and
# leaving the next line holding an undefined name.
HANDSHAKE_CODE_RX = re.compile(
    r"\bInitializeRequest(?:Params|Schema)?\b"
    r"|\bInitializeResult(?:Params|Schema)?\b"
    r"|\bInitializedNotification(?:Params|Schema)?\b"
)
# Only ever valid as a JSON-RPC method-name string, so it always starts
# inside a STRING token -- matched directly, same as the rule's search_wire.
WIRE_RX = re.compile(r"notifications/initialized")


def _safe_to_comment_out(line: str) -> bool:
    """Commenting out must not leave a dangling suite or multiline expression."""
    stripped = line.rstrip("\n").rstrip()
    if stripped.endswith(":"):
        return False
    if stripped.endswith(("(", "[", "{", "\\")):
        return False
    return True


def _handshake_hit(line: str) -> str | None:
    if HANDSHAKE_CODE_RX.search(line):
        return "initialize handshake reference"
    if WIRE_RX.search(line):
        return "notifications/initialized wire reference"
    return None


class InitializeHandshakeFixer(Fixer):
    rule_id = "R009"
    title = "Comment out the removed initialize handshake, leave a TODO"
    confidence = "review"

    def fix(self, source: str, path: Path) -> FixResult:
        lines = source.splitlines(keepends=True)
        out: list[str] = []
        prefix = comment_prefix(path)
        todo = f"{prefix}{TODO}"
        # Remove import members from a parenthesised list rather than
        # commenting them out, so `from x import ( )` is never produced (#245).
        lines, changes = strip_import_members(lines, _handshake_hit, todo, "initialize handshake")

        for i, raw_line in enumerate(lines, start=1):
            stripped = raw_line.lstrip(" \t")
            already_commented = is_commented(raw_line)
            ends_as_block_opener = raw_line.rstrip("\n").rstrip().endswith(":")
            hit = (
                None
                if already_commented or ends_as_block_opener
                else _handshake_hit(raw_line)
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
