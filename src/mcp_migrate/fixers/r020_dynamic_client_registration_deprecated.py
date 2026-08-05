"""Fixer for R020 -- Dynamic Client Registration deprecated.

RFC 7591 Dynamic Client Registration (`register_client`, `RegisterClientRequest`,
`DynamicClientRegistration`) is deprecated in the 2026-07-28 MCP specification in
favour of Client ID Metadata Documents (CIMD).

Because migrating off DCR requires standing up a real Client ID Metadata Document
endpoint and updating authentication flows, a mechanical fixer cannot do the
migration itself -- but it can annotate the flagged code with a
`# TODO(mcp-migrate): ...` pointing at `cookbook/12-dynamic-client-registration-deprecated.md`.

Confidence "review": requires human review and architectural updates to complete
the migration to CIMD.
"""
from __future__ import annotations

import re
from pathlib import Path

from .base import Fixer, FixResult

TODO = (
    "TODO(mcp-migrate): RFC 7591 Dynamic Client Registration is deprecated in "
    "2026-07-28; migrate to Client ID Metadata Document (CIMD). "
    "See cookbook/12-dynamic-client-registration-deprecated.md"
)

# Pattern matching DCR symbols in Python & TypeScript
DCR_RX = re.compile(
    r"\bRegisterClientRequest\b|\bDynamicClientRegistration\b|\bregister_client\b|\bregisterClient\b"
)


class DynamicClientRegistrationDeprecatedFixer(Fixer):
    rule_id = "R020"
    title = "Annotate deprecated Dynamic Client Registration (RFC 7591) usage with a TODO"
    confidence = "review"

    def fix(self, source: str, path: Path) -> FixResult:
        lines = source.splitlines(keepends=True)
        out: list[str] = []
        changes: list[str] = []

        for i, raw_line in enumerate(lines, start=1):
            stripped = raw_line.lstrip(" \t")
            already_commented = stripped.startswith(("#", "//"))

            if (
                not already_commented
                and DCR_RX.search(raw_line)
                and TODO not in raw_line
                and not (out and TODO in out[-1])
            ):
                indent = raw_line[: len(raw_line) - len(stripped)]
                newline = "\n" if raw_line.endswith("\n") else ""
                comment_prefix = "// " if path.suffix in (".ts", ".js", ".tsx", ".jsx") else "# "
                out.append(f"{indent}{comment_prefix}{TODO}{newline}")
                changes.append(f"line {i}: annotated deprecated DCR usage with TODO")

            out.append(raw_line)

        if not changes:
            return self.unchanged(source)
        return self.result("".join(out), changes)
