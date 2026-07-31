"""Fixer for R017 -- the old -32002 resource-not-found error code.

2026-07-28 reassigns the "resource not found" error code from -32002 to
-32602 (Invalid params). Mirrors the R017 *rule*'s own qualifying context
check on purpose (see `rules/r017_resource_not_found_code_changed.py`,
keyed off only by its rule id string, not imported): -32002 on its own is
just a negative integer, so it's only rewritten on a line that also reads
as being about a resource lookup failing (mentions "resource", or some
spelling of "not found"). An unrelated server-defined use of -32002 for a
different error condition is left untouched rather than guessed at.
Confidence "safe": once that context match is required, the remaining
transformation is an exact numeric literal rename.
"""
from __future__ import annotations

import re
from pathlib import Path

from .base import Fixer, FixResult

CODE_RX = re.compile(r"-32002\b")
# Same qualifying context as the R017 rule: -32002 plus a mention of
# "resource" or some spelling of "not found" anywhere on the same line.
CONTEXT_RX = re.compile(r"resource|not[_ ]?found|notfound", re.IGNORECASE)


class ResourceNotFoundErrorCodeFixer(Fixer):
    rule_id = "R017"
    title = "Resource-not-found JSON-RPC error code -32002 -> -32602"
    confidence = "safe"

    def fix(self, source: str, path: Path) -> FixResult:
        lines = source.splitlines(keepends=True)
        changes: list[str] = []

        for i, line in enumerate(lines):
            if not CODE_RX.search(line):
                continue
            if not CONTEXT_RX.search(line):
                continue  # -32002 here isn't clearly about resource-not-found; don't guess
            lines[i] = CODE_RX.sub("-32602", line)
            changes.append(f"line {i + 1}: resource-not-found error code -32002 -> -32602")

        if not changes:
            return self.unchanged(source)
        return self.result("".join(lines), changes)
