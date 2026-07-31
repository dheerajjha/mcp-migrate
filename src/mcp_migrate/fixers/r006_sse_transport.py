"""Fixer for R006 -- deprecated HTTP+SSE transport.

Renames the mechanical, unambiguous parts of an SSE -> Streamable HTTP
migration:

  - `from mcp.server.sse import SseServerTransport` -> the Streamable HTTP
    equivalent import
  - `SseServerTransport(...)` -> `StreamableHTTPServerTransport()`
  - `transport="sse"` -> `transport="streamable-http"`

`StreamableHTTPServerTransport` doesn't take the SSE endpoint-path argument
`SseServerTransport` did, so any constructor arguments are dropped -- but
never silently: a TODO is left right above the call so a human confirms
nothing load-bearing was lost. Swapping the transport class is otherwise a
real architectural change (route mounting, request handling and framing all
differ between SSE and Streamable HTTP), well beyond what a text-level
fixer should attempt on its own, so confidence stays "review" even though
each individual rename below is exact.
"""
from __future__ import annotations

import re
from pathlib import Path

from ._textedit import find_matching_close, leading_ws
from .base import Fixer, FixResult

SPEC_URL = "https://modelcontextprotocol.io/specification/draft/changelog"
TODO = "# TODO(mcp-migrate): verify no constructor args were lost moving off SSE, see " + SPEC_URL

IMPORT_RX = re.compile(r"from\s+mcp\.server\.sse\s+import\s+SseServerTransport\b")
CTOR_RX = re.compile(r"\bSseServerTransport\s*(\()")
TRANSPORT_KW_RX = re.compile(r'transport\s*=\s*(["\'])sse\1')


def _is_commented(line: str) -> bool:
    return line.lstrip().startswith("#")


class SseTransportFixer(Fixer):
    rule_id = "R006"
    title = 'Rewrite SseServerTransport / transport="sse" to Streamable HTTP'
    confidence = "review"

    def fix(self, source: str, path: Path) -> FixResult:
        lines = source.splitlines(keepends=True)
        changes: list[str] = []

        # 1. Import rename -- single-line, in place.
        for i, line in enumerate(lines):
            if _is_commented(line):
                continue
            new_line, n = IMPORT_RX.subn(
                "from mcp.server.streamable_http import StreamableHTTPServerTransport",
                line,
            )
            if n:
                lines[i] = new_line
                changes.append(f"line {i + 1}: import Streamable HTTP transport instead of SSE")

        # 2. Constructor call sites. Collect targets against the *current*
        # (already import-fixed, but not yet call-site-fixed) lines first,
        # then apply edits bottom-to-top: a multi-line call collapses to
        # one line, which shifts every later line index, so an earlier
        # target's line number must stay valid while later ones are
        # rewritten first.
        targets = []
        for i, line in enumerate(lines):
            if _is_commented(line):
                continue
            m = CTOR_RX.search(line)
            if not m:
                continue
            open_col = m.end(1) - 1
            closed = find_matching_close(lines, i, open_col)
            if closed is None:
                continue
            close_i, close_col = closed
            targets.append((i, m.start(), close_i, close_col))

        for open_i, name_start, close_i, close_col in sorted(targets, key=lambda t: t[0], reverse=True):
            indent = leading_ws(lines[open_i])
            before = lines[open_i][:name_start]
            after = lines[close_i][close_col + 1:]
            new_line = f"{before}StreamableHTTPServerTransport(){after}"
            if close_i > open_i:
                for k in range(open_i + 1, close_i + 1):
                    lines[k] = ""
            lines[open_i] = new_line
            lines.insert(open_i, f"{indent}{TODO}\n")
            changes.append(
                f"line {open_i + 1}: SseServerTransport(...) -> StreamableHTTPServerTransport(), flagged for review"
            )

        # 3. transport="sse" keyword rename -- single-line, in place.
        for i, line in enumerate(lines):
            if _is_commented(line):
                continue
            new_line, n = TRANSPORT_KW_RX.subn(
                lambda mm: f'transport={mm.group(1)}streamable-http{mm.group(1)}', line,
            )
            if n:
                lines[i] = new_line
                changes.append(f'line {i + 1}: transport="sse" -> transport="streamable-http"')

        if not changes:
            return self.unchanged(source)
        return self.result("".join(lines), changes)
