"""Small text-editing helpers shared by fixers.

Not a fixer itself (no `Fixer` subclass lives here), so `all_fixers()`'s
module scan finds nothing to register from this file -- it's just plumbing.

These operate on plain text/line lists on purpose, not the AST: fixers must
preserve comments and formatting, so every edit here is a line/column
splice, never an `ast.unparse` round-trip.
"""
from __future__ import annotations

OPEN = "([{"
CLOSE = ")]}"


def find_matching_close(lines: list[str], open_idx: int, open_col: int) -> tuple[int, int] | None:
    """Given the position of an opening bracket (any of `([{`), return the
    (line_idx, col) of the bracket that closes it, tracking nested
    brackets of any kind along the way.

    Returns None if the source runs out before the bracket closes (e.g. the
    file is truncated, or our column pointed at something that wasn't
    actually an opening bracket) -- callers should treat that as "don't
    know how to fix this" rather than guessing.

    This deliberately does not try to skip over string literals, so a
    bracket character inside a string can throw the count off. That's an
    accepted, documented limitation: real-world Tool()/ServerCapabilities()
    call sites we target don't embed unbalanced bracket characters in their
    string arguments, and if one ever does, the worst outcome is that this
    returns a bad span and the caller's own sanity checks refuse to apply a
    fix -- never a silent, wrong edit written back to disk.
    """
    depth = 0
    started = False
    for i in range(open_idx, len(lines)):
        line = lines[i]
        start = open_col if i == open_idx else 0
        for j in range(start, len(line)):
            ch = line[j]
            if ch in OPEN:
                depth += 1
                started = True
            elif ch in CLOSE:
                depth -= 1
                if started and depth == 0:
                    return i, j
    return None


def leading_ws(line: str) -> str:
    return line[: len(line) - len(line.lstrip(" \t"))]
