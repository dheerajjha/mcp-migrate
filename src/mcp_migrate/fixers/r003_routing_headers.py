"""Fixer for R003 -- hand-rolled MCP transport calls that skip the
Mcp-Method / Mcp-Name routing headers.

R003 itself is deliberately conservative (see the rule source's comment on
the mcp-atlassian false-positive), and a fixer for it has to be even more
so: inserting a header into an arbitrary `.post(...)` call site correctly --
as a new kwarg? into an existing `headers=` dict? a new dict merged with
something else? -- needs real call-site parsing this project doesn't have,
and guessing wrong risks writing an unrelated header into an unrelated
call. See fixers/base.py: "when a fixer cannot be sure a transformation is
correct, it must return the source unchanged rather than guess."

What's safe to do mechanically: an inline `headers={...}` (Python) or
`headers: {...}` (TypeScript) dict literal, written on one line, is
already the exact spot a human would add the missing keys -- no shape
inference needed, just "does this literal already mention Mcp-Method".
So the fixer finds those lines and drops a TODO above them. It does not
touch the dict itself: this project's own before/after in
cookbook/14-routing-headers.md shows Mcp-Method's value coming from the
method being sent (`"tools/call"`, a variable holding the tool name, ...),
which the fixer has no reliable way to recover. Confidence "review": every
flagged site still needs a human to fill in the actual header value.
"""
from __future__ import annotations

import re
from pathlib import Path

from .base import Fixer, FixResult, comment_prefix, is_commented

SPEC_URL = "https://modelcontextprotocol.io/specification/2026-07-28/basic/transports/streamable-http"
COOKBOOK = "cookbook/14-routing-headers.md"
TODO = (
    "TODO(mcp-migrate): add Mcp-Method (and Mcp-Name if this call sends "
    f"tools/call, resources/read, or prompts/get) to this headers dict, see {SPEC_URL} and {COOKBOOK}"
)

# Weak, file-wide evidence that this file plausibly speaks MCP's own wire
# protocol at all -- the same signal the rule itself gates on
# (MCP_METHOD_RX / TS_MCP_SURFACE_RX in rules/r003_routing_headers.py).
# Without it, an inline `headers={...}` literal is just as likely to belong
# to some unrelated REST call (Jira, Confluence, S3, ...) that has nothing
# to do with MCP transport.
MCP_SURFACE_RX = re.compile(
    r"tools/call|tools/list|resources/read|prompts/get|jsonrpc|@modelcontextprotocol",
    re.IGNORECASE,
)

# The one shape narrow enough to be confident about: a headers dict literal
# written inline, on a single line, so the fixer can see its entire
# contents and doesn't have to guess whether some other line contributes to
# it (a `.update(...)` call, a spread, a second dict merged in later).
# Requiring the first token inside the braces to be a quoted key rules out
# `headers = {}` (an empty dict later populated elsewhere) matching here --
# that's the multi-line-construction shape this fixer explicitly declines.
INLINE_HEADERS_DICT_RX = re.compile(r"headers\s*[:=]\s*\{\s*([\"'][^{}]*)\}")


class RoutingHeadersFixer(Fixer):
    rule_id = "R003"
    title = "Annotate inline headers dict literals missing Mcp-Method with a TODO"
    confidence = "review"

    def fix(self, source: str, path: Path) -> FixResult:
        if not MCP_SURFACE_RX.search(source):
            return self.unchanged(source)

        lines = source.splitlines(keepends=True)
        out: list[str] = []
        changes: list[str] = []

        prefix = comment_prefix(path)
        todo = f"{prefix}{TODO}"

        for i, raw_line in enumerate(lines, start=1):
            stripped = raw_line.lstrip(" \t")
            already_commented = is_commented(raw_line)
            match = INLINE_HEADERS_DICT_RX.search(raw_line)

            if (
                not already_commented
                and match
                and "mcp-method" not in match.group(1).lower()
                and not (out and out[-1].strip(" \t\n") == todo)
            ):
                indent = raw_line[: len(raw_line) - len(stripped)]
                newline = "\n" if raw_line.endswith("\n") else ""
                out.append(f"{indent}{todo}{newline}")
                changes.append(f"line {i}: annotated inline headers dict missing Mcp-Method with TODO")

            out.append(raw_line)

        if not changes:
            return self.unchanged(source)
        return self.result("".join(out), changes)
