"""Fixer for R001 -- Mcp-Session-Id no longer exists on the transport.

There is no mechanical replacement for "read the session id and look up
per-connection state": the human has to decide what the new explicit handle
argument is called and thread it through their tool signatures. So this
fixer does the one thing that *is* safe to do without understanding the
surrounding code -- neutralize the actual header read/write so it can't
silently do the wrong thing (e.g. always look up a `None` key) -- and
leaves a TODO exactly where the human needs to look next. Confidence
"review": the file still needs a human pass to finish the migration.
"""
from __future__ import annotations

import re
from pathlib import Path

from ._textedit import string_lines
from .base import Fixer, FixResult

SPEC_URL = "https://github.com/modelcontextprotocol/modelcontextprotocol/pull/2567"
TODO = "# TODO(mcp-migrate): replaced by an explicit handle argument, see " + SPEC_URL

# Only the actual header read/write plumbing -- not every downstream use of
# a variable that happens to be named `mcp_session_id`/`session_id` (an
# `if mcp_session_id is None:` a few lines below the read is not itself a
# "header read/write", and commenting *that* out risks leaving an `if`/
# `raise` block without a body, which would break the file outright).
HEADER_ACCESS_RX = re.compile(
    r'\.headers\s*(?:\.get\(\s*|\[\s*)["\']Mcp-Session-Id["\']'
    r'|os\.environ\s*(?:\.get\(\s*|\[\s*)["\']MCP_SESSION_ID["\']',
    re.IGNORECASE,
)


class SessionIdHeaderFixer(Fixer):
    rule_id = "R001"
    title = "Comment out Mcp-Session-Id header reads/writes, leave a TODO"
    confidence = "review"

    def fix(self, source: str, path: Path) -> FixResult:
        lines = source.splitlines(keepends=True)
        out: list[str] = []
        changes: list[str] = []
        str_lines = string_lines(source, path)

        for i, raw_line in enumerate(lines, start=1):
            if i in str_lines:
                out.append(raw_line)
                continue
            stripped = raw_line.lstrip(" \t")
            already_commented = stripped.startswith("#")
            # Block-openers (if/while/for/def/...) are never touched: commenting
            # one out would leave its suite dangling with no body, which is a
            # syntax error, not just a semantic one. When in doubt, don't fix.
            ends_as_block_opener = raw_line.rstrip("\n").rstrip().endswith(":")

            if (not already_commented) and (not ends_as_block_opener) and HEADER_ACCESS_RX.search(raw_line):
                indent = raw_line[: len(raw_line) - len(stripped)]
                newline = "\n" if raw_line.endswith("\n") else ""
                body = stripped.rstrip("\n")
                # Idempotency: if the line right above is already our TODO
                # (e.g. a previous fixer run), don't insert a second one.
                if not (out and out[-1].strip(" \t\n") == TODO):
                    out.append(f"{indent}{TODO}{newline}")
                out.append(f"{indent}# {body}{newline}")
                changes.append(f"line {i}: commented out Mcp-Session-Id header access, added TODO")
            else:
                out.append(raw_line)

        new_text = "".join(out)
        if not changes:
            return self.unchanged(source)
        return self.result(new_text, changes)
