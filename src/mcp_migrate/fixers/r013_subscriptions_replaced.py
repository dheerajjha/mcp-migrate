"""Fixer for R013 -- resources/subscribe and resources/unsubscribe removed.

The old shape was two separate calls (subscribe once, unsubscribe once, get
a stream of notifications/resources/updated in between); the new
subscriptions/listen call collapses that into a single long-lived call.
Rewriting a subscribe/unsubscribe handler pair into a listen loop is a real
control-flow change, not a text substitution, so this fixer does the one
thing that's safe without understanding the surrounding code -- comment out
the dead SubscribeRequest/UnsubscribeRequest reference or
"resources/subscribe"/"resources/unsubscribe" dispatch line and leave a TODO
pointing at cookbook/04-subscribe-to-subscriptions-listen.md. Confidence
"review": every flagged site still needs a human pass.
"""
from __future__ import annotations

import re
from pathlib import Path

from .base import Fixer, FixResult, comment_prefix, is_commented

SPEC_URL = "https://modelcontextprotocol.io/specification/2026-07-28/changelog"
COOKBOOK = "cookbook/04-subscribe-to-subscriptions-listen.md"
TODO = (
    "TODO(mcp-migrate): resources/subscribe and resources/unsubscribe are "
    "removed, replaced by the single long-lived subscriptions/listen call "
    f"-- see {SPEC_URL} and {COOKBOOK}"
)

# Bounded to the exact SDK export names (optionally suffixed
# `Params`/`Schema`), same as the rule -- an unbounded `\w*` suffix would
# also match unrelated identifiers like `SubscribeRequester`.
SUBSCRIBE_CODE_RX = re.compile(r"\b(?:Subscribe|Unsubscribe)Request(?:Params|Schema)?\b")
SUBSCRIBE_DISPATCH_RX = re.compile(
    r"""method\s*===?\s*["'](?:resources/subscribe|resources/unsubscribe)["']"""
    r"""|case\s*["'](?:resources/subscribe|resources/unsubscribe)["']"""
    r"""|[{,]\s*["'](?:resources/subscribe|resources/unsubscribe)["']\s*:"""
)


def _safe_to_comment_out(line: str) -> bool:
    """Commenting out must not leave a dangling suite or multiline expression."""
    stripped = line.rstrip("\n").rstrip()
    if stripped.endswith(":"):
        return False
    if stripped.endswith(("(", "[", "{", "\\")):
        return False
    return True


def _subscribe_hit(line: str) -> str | None:
    if SUBSCRIBE_CODE_RX.search(line):
        return "removed SubscribeRequest/UnsubscribeRequest reference"
    if SUBSCRIBE_DISPATCH_RX.search(line):
        return "removed resources/subscribe or resources/unsubscribe JSON-RPC method dispatch"
    return None


class SubscriptionsReplacedFixer(Fixer):
    rule_id = "R013"
    title = "Comment out removed resources/subscribe or resources/unsubscribe usage, leave a TODO"
    confidence = "review"

    def fix(self, source: str, path: Path) -> FixResult:
        lines = source.splitlines(keepends=True)
        out: list[str] = []
        changes: list[str] = []

        prefix = comment_prefix(path)
        todo = f"{prefix}{TODO}"

        for i, raw_line in enumerate(lines, start=1):
            stripped = raw_line.lstrip(" \t")
            already_commented = is_commented(raw_line)
            ends_as_block_opener = raw_line.rstrip("\n").rstrip().endswith(":")
            hit = (
                None
                if already_commented or ends_as_block_opener
                else _subscribe_hit(raw_line)
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
