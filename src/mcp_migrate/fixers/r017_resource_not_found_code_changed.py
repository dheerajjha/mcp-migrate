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

from ._textedit import string_lines
from .base import Fixer, FixResult

CODE_RX = re.compile(r"-32002\b")
# Same qualifying context as the R017 rule: -32002 plus a mention of
# "resource" or some spelling of "not found" anywhere on the same line.
CONTEXT_RX = re.compile(r"resource|not[_ ]?found|notfound", re.IGNORECASE)

# A *name* that already says "this is the old code". Someone who writes
# `LEGACY_RESOURCE_NOT_FOUND = -32002` has demonstrated they know what
# -32002 is and is keeping it deliberately -- for clients that still send
# it, or to dispatch on both. Reporting that is noise; rewriting it is
# worse, and R017's fixer is `safe`, so it did. See #217.
#
# Scoped to the assigned identifier, NOT the whole line. That distinction is
# load-bearing: `RESOURCE_NOT_FOUND = -32002  # legacy code, now -32602` is
# a comment *describing the bug* and must still fire, while
# `LEGACY_RESOURCE_NOT_FOUND: -32002` is a deliberate keep. Our own test
# fixture is the first shape; dealfluence/adeu is the second.
#
# The marker has no trailing word boundary: `\b` would not match
# `LEGACY_RESOURCE...`, because `_` is a word character.
ASSIGNED_NAME_RX = re.compile(r"([A-Za-z_][A-Za-z0-9_]*)\s*[:=]\s*-32002\b")
LEGACY_MARKER_RX = re.compile(
    r"(?<![A-Za-z])(?:legacy|deprecated|obsolete|old|pre[_-]?2026|v1)(?![A-Za-z])",
    re.IGNORECASE,
)


def _is_deliberate_legacy_constant(text: str) -> bool:
    """True when the identifier being assigned -32002 names itself legacy."""
    m = ASSIGNED_NAME_RX.search(text)
    return bool(m and LEGACY_MARKER_RX.search(m.group(1)))



class ResourceNotFoundErrorCodeFixer(Fixer):
    rule_id = "R017"
    title = "Resource-not-found JSON-RPC error code -32002 -> -32602"
    confidence = "safe"

    def fix(self, source: str, path: Path) -> FixResult:
        lines = source.splitlines(keepends=True)
        changes: list[str] = []
        str_lines = string_lines(source, path)

        for i, line in enumerate(lines):
            if (i + 1) in str_lines:
                continue
            if not CODE_RX.search(line):
                continue
            if not CONTEXT_RX.search(line):
                continue  # -32002 here isn't clearly about resource-not-found; don't guess
            if _is_deliberate_legacy_constant(line):
                continue  # named legacy on purpose -- rewriting it defeats that
            lines[i] = CODE_RX.sub("-32602", line)
            changes.append(f"line {i + 1}: resource-not-found error code -32002 -> -32602")

        if not changes:
            return self.unchanged(source)
        return self.result("".join(lines), changes)
