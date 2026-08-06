"""Fixer for R018 -- server-initiated roots/list, sampling/createMessage and
elicitation/create, replaced by Multi Round-Trip Requests.

Unlike most fixers here, there's no mechanical rewrite available: turning a
blocking server-initiated call into an `InputRequiredResult` + client retry
means designing an id to correlate the retry to the pending state, and
threading that id (and whatever local state used to live on the stack)
through the handler -- see cookbook/10-multi-round-trip-requests.md. A fixer
can't invent that id or that storage for you.

What it can do, the same as R008's fixer for the same reason, is find the
call site and drop a TODO right above it pointing at the cookbook recipe.
The call itself is untouched: it's the exact thing that needs to become an
InputRequiredResult, not code to comment out. Confidence "review": every
flagged site still needs a human pass to do the actual rewrite.
"""
from __future__ import annotations

import re
from pathlib import Path

from .base import Fixer, FixResult, comment_prefix, is_commented

SPEC_URL = "https://modelcontextprotocol.io/specification/2026-07-28/changelog"
COOKBOOK = "cookbook/10-multi-round-trip-requests.md"
TODO = (
    "TODO(mcp-migrate): server-initiated request replaced by Multi Round-Trip "
    f"Requests -- return InputRequiredResult and let the client retry with "
    f"inputResponses instead, see {SPEC_URL} and {COOKBOOK}"
)

# Same code-shaped identifiers the rule itself uses (search_code side only --
# see r018_multi_round_trip_replaces_server_initiated.py). The wire-literal
# half (`roots/list`, `sampling/createMessage`, ...) is deliberately left out
# here: those strings show up as dict/dispatch keys and similar shapes with
# no single call site to annotate, so a line-level fixer would be guessing
# at which occurrence is "the" call.
CALL_SITE_RX = re.compile(
    r"\blist_roots\s*\(|\bcreate_message\s*\(|\bElicitRequest\s*\("
    r"|\bListRootsRequestSchema\b|\bCreateMessageRequestSchema\b|\bElicitRequestSchema\b"
)


class MultiRoundTripFixer(Fixer):
    rule_id = "R018"
    title = "Annotate server-initiated roots/sampling/elicitation calls with a TODO"
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

            if (
                not already_commented
                and CALL_SITE_RX.search(raw_line)
                and not (out and out[-1].strip(" \t\n") == todo)
            ):
                indent = raw_line[: len(raw_line) - len(stripped)]
                newline = "\n" if raw_line.endswith("\n") else ""
                out.append(f"{indent}{todo}{newline}")
                changes.append(f"line {i}: annotated server-initiated call with TODO")

            out.append(raw_line)

        if not changes:
            return self.unchanged(source)
        return self.result("".join(out), changes)
