"""Fixer for R004 -- tools/list order is not deterministic.

Only handles the one shape that's genuinely unambiguous: a `list_tools`
handler whose body directly `return`s a list literal, where the list
elements are either all `Tool(...)` constructor calls (sort by `.name`) or
all plain string/number literals (sort with no key). Anything else --
building the list across several statements, conditionally appending,
returning a name bound elsewhere in a way we can't trace -- is left alone.
Confidence "safe": wrapping an already-known-shape list literal in
`sorted()` cannot change *what* is returned, only the order, and only when
we're already sure the client-visible order was unspecified.
"""
from __future__ import annotations

import re
from pathlib import Path

from ._textedit import find_matching_close, string_lines
from .base import Fixer, FixResult

HANDLER_RX = re.compile(r"def\s+list_tools\b|@[\w.]*\blist_tools\b")
RETURN_LIST_RX = re.compile(r"^(\s*)return\s*(\[)")
TOOL_CALL_RX = re.compile(r"\bTool\s*\(")
# A content span that -- ignoring whitespace/commas/trailing-comma noise --
# is made up entirely of plain literals: strings, numbers, True/False/None.
# Deliberately conservative; if it's anything more interesting than this we
# don't try to guess a sort key.
PLAIN_LITERAL_ITEM_RX = re.compile(
    r'^\s*(?:'
    r'"[^"]*"|\'[^\']*\'|-?\d+(?:\.\d+)?|True|False|None'
    r')\s*,?\s*$'
)


def _body_bounds(lines: list[str], line_no: int) -> tuple[int, int]:
    """Return 0-based (body_start, body_end) for the block starting at the
    1-based `line_no` -- same algorithm as the R004 *rule* uses to scope its
    look-ahead, reimplemented here rather than imported so the fixers
    package has no runtime dependency on `rules/`.
    """
    indent = len(lines[line_no - 1]) - len(lines[line_no - 1].lstrip())
    j = line_no
    while j < len(lines):
        text = lines[j]
        if not text.strip():
            j += 1
            continue
        if len(text) - len(text.lstrip()) > indent:
            break
        if len(text) - len(text.lstrip()) < indent:
            break
        j += 1
    body_start = j
    end = len(lines)
    for k in range(body_start, len(lines)):
        text = lines[k]
        if not text.strip():
            continue
        if len(text) - len(text.lstrip()) <= indent:
            end = k
            break
    return body_start, end


def _sort_key_for(content: str) -> str | None:
    """Decide the `sorted(..., key=...)` argument for the list contents, or
    None if the shape isn't one we're confident sorting is safe/meaningful
    for. Returns "" (empty string) to mean "sort with no key"."""
    if TOOL_CALL_RX.search(content):
        return "key=lambda t: t.name"
    # Split on top-level commas is unnecessary here: every individual line
    # of a literal list, once you strip comments, is either blank or one
    # item (+ optional trailing comma) when the source is at all readably
    # formatted -- which is the only case we try to handle.
    items = [ln for ln in content.splitlines() if ln.strip()]
    if items and all(PLAIN_LITERAL_ITEM_RX.match(ln) for ln in items):
        return ""
    # Single-line literal, e.g. `["a", "b"]` -- content has no newlines.
    if "\n" not in content:
        parts = [p.strip() for p in content.split(",")]
        parts = [p for p in parts if p]
        if parts and all(re.match(r'^(?:"[^"]*"|\'[^\']*\'|-?\d+(?:\.\d+)?|True|False|None)$', p) for p in parts):
            return ""
    return None


class SortToolsFixer(Fixer):
    rule_id = "R004"
    title = "Wrap an unambiguous tools/list literal in sorted(...)"
    confidence = "safe"

    def fix(self, source: str, path: Path) -> FixResult:
        lines = source.splitlines(keepends=True)
        changes: list[str] = []
        str_lines = string_lines(source, path)

        for m in HANDLER_RX.finditer(source):
            line_no = source.count("\n", 0, m.start()) + 1
            if line_no in str_lines:
                continue
            body_start, body_end = _body_bounds(lines, line_no)
            window_text = "".join(lines[body_start:body_end])
            if "sorted(" in window_text or ".sort(" in window_text:
                continue  # already deterministic (or already fixed)

            for i in range(body_start, body_end):
                rm = RETURN_LIST_RX.match(lines[i])
                if not rm:
                    continue
                open_col = rm.end(2) - 1
                closed = find_matching_close(lines, i, open_col)
                if closed is None:
                    continue
                close_i, close_col = closed
                content = "".join(lines[i + 1:close_i]) if close_i > i \
                    else lines[i][open_col + 1:close_col]
                key = _sort_key_for(content)
                if key is None:
                    continue  # ambiguous shape -- don't guess

                suffix = f", {key})" if key else ")"
                if close_i == i:
                    line = lines[i]
                    lines[i] = (
                        line[:open_col] + "sorted(" + line[open_col:close_col + 1]
                        + suffix + line[close_col + 1:]
                    )
                else:
                    open_line = lines[i]
                    lines[i] = open_line[:open_col] + "sorted(" + open_line[open_col:]
                    close_line = lines[close_i]
                    lines[close_i] = close_line[:close_col + 1] + suffix + close_line[close_col + 1:]
                changes.append(f"line {i + 1}: wrapped returned tool list in sorted({key or ''})")
                break  # one fix per handler window is enough for our target shapes

        if not changes:
            return self.unchanged(source)
        return self.result("".join(lines), changes)
