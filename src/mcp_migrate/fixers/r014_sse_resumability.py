"""Fixer for R014 -- SSE resumability (Last-Event-ID) removed from the transport.

There is no mechanical replacement for stream resumability: a dropped
connection is just dropped now, and the client re-issues a fresh request.
So this fixer does the one thing that is safe without understanding the
surrounding code -- neutralize the Last-Event-ID header read and event-store
replay plumbing with a loud TODO, leaving the event store itself alone when
it may still serve other purposes (audit logging, debugging). Confidence
"review": every flagged site still needs a human pass.
"""
from __future__ import annotations

import re
from pathlib import Path

from .base import Fixer, FixResult

SPEC_URL = "https://modelcontextprotocol.io/specification/2026-07-28/changelog"
COOKBOOK = "cookbook/08-sse-resumability-removed.md"
TODO = (
    "# TODO(mcp-migrate): SSE resumability via Last-Event-ID is removed; "
    f"see {SPEC_URL} and {COOKBOOK}"
)

# The actual header read -- not every downstream use of a variable named
# `last_event_id` on a block-opener line.
HEADER_ACCESS_RX = re.compile(
    r'\.headers\s*(?:\.get\(\s*|\[\s*)["\']Last-Event-ID["\']'
    r'|os\.environ\s*(?:\.get\(\s*|\[\s*)["\']LAST_EVENT_ID["\']',
    re.IGNORECASE,
)
REPLAY_CALL_RX = re.compile(r"\.replay_after\s*\(")


def _safe_to_comment_out(line: str) -> bool:
    """Commenting out must not leave a dangling suite or multiline expression."""
    stripped = line.rstrip("\n").rstrip()
    if stripped.endswith(":"):
        return False
    if stripped.endswith(("(", "[", "{", "\\")):
        return False
    return True


def _resumability_hit(line: str) -> str | None:
    if HEADER_ACCESS_RX.search(line):
        return "Last-Event-ID header access"
    if REPLAY_CALL_RX.search(line):
        return "event-store replay call"
    return None


class SseResumabilityFixer(Fixer):
    rule_id = "R014"
    title = "Comment out Last-Event-ID resumability plumbing, leave a TODO"
    confidence = "review"

    def fix(self, source: str, path: Path) -> FixResult:
        lines = source.splitlines(keepends=True)
        out: list[str] = []
        changes: list[str] = []

        for i, raw_line in enumerate(lines, start=1):
            stripped = raw_line.lstrip(" \t")
            already_commented = stripped.startswith("#")
            ends_as_block_opener = raw_line.rstrip("\n").rstrip().endswith(":")
            hit = (
                None
                if already_commented or ends_as_block_opener
                else _resumability_hit(raw_line)
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
