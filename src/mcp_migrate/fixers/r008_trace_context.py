"""Fixer for R008 -- OpenTelemetry in use but `traceparent` never read from `_meta`.

Unlike most rules here, R008's finding isn't tied to one call site: "OpenTelemetry
is used somewhere, traceparent is read nowhere" is a project-wide fact, not a
single line to repair. There's no single edit that turns a server into one that
correctly extracts trace context -- that requires wiring a propagator into
whichever framework the server uses, which is a design decision, not a text
substitution.

What a fixer *can* do mechanically: find where a span actually starts (the
`start_as_current_span`/`start_span` or TS `startActiveSpan`/`startSpan` call is
the site with the underlying bug -- a span opened here without extracted context
starts a new, disconnected trace) and drop a TODO right above it pointing at
`cookbook/17-trace-context-propagation.md`. The span-creation line itself is
untouched: it's correct code, just incomplete, so there's nothing to comment out.
Confidence "review": every flagged site still needs a human pass to wire up the
propagator.
"""
from __future__ import annotations

import re
from pathlib import Path

from .base import Fixer, FixResult, comment_prefix, is_commented

SPEC_URL = "https://github.com/modelcontextprotocol/modelcontextprotocol/pull/414"
COOKBOOK = "cookbook/17-trace-context-propagation.md"
TODO = (
    "TODO(mcp-migrate): extract traceparent/tracestate/baggage from _meta before "
    f"starting this span, or the trace disconnects here -- see {SPEC_URL} and {COOKBOOK}"
)

# The entry point this fixer can actually identify: where a span begins.
# `start_span`/`start_as_current_span` (Python) and `startSpan`/`startActiveSpan`
# (TypeScript) are the OpenTelemetry API's own names for that, so matching them
# needs no framework-specific knowledge.
SPAN_START_RX = re.compile(
    r"\.\s*start_as_current_span\s*\(|\.\s*start_span\s*\("
    r"|\.\s*startActiveSpan\s*\(|\.\s*startSpan\s*\("
)


class TraceContextFixer(Fixer):
    rule_id = "R008"
    title = "Annotate OpenTelemetry span creation with a traceparent-extraction TODO"
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
                and SPAN_START_RX.search(raw_line)
                and not (out and out[-1].strip(" \t\n") == todo)
            ):
                indent = raw_line[: len(raw_line) - len(stripped)]
                newline = "\n" if raw_line.endswith("\n") else ""
                out.append(f"{indent}{todo}{newline}")
                changes.append(f"line {i}: annotated OpenTelemetry span start with TODO")

            out.append(raw_line)

        if not changes:
            return self.unchanged(source)
        return self.result("".join(out), changes)
