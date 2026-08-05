"""Small text-editing helpers shared by fixers.

Not a fixer itself (no `Fixer` subclass lives here), so `all_fixers()`'s
module scan finds nothing to register from this file -- it's just plumbing.

These operate on plain text/line lists on purpose, not the AST: fixers must
preserve comments and formatting, so every edit here is a line/column
splice, never an `ast.unparse` round-trip.
"""
from __future__ import annotations

from pathlib import Path

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


def string_lines(source: str, path_or_lang: str | Path = "python") -> set[int]:
    """Return 1-indexed line numbers in ``source`` that are part of a string literal.

    - Python: tracks triple-quoted (''' and ''") and single/double quoted strings via tokenize.
    - TypeScript / JavaScript: tracks backtick template literals (`...`), single/double quotes.

    If parsing fails or encounters unterminated multi-line string state at EOF,
    returns all line numbers (1..N) as a fail-safe so line-based fixers decline to edit.
    """
    import io
    import tokenize

    lines_list = source.splitlines()
    total_lines = len(lines_list)
    all_lines = set(range(1, total_lines + 1))
    if total_lines == 0:
        return set()

    if isinstance(path_or_lang, Path):
        lang = path_or_lang.suffix.lower()
    else:
        lang = str(path_or_lang).lower()

    if lang in (".ts", ".tsx", ".js", ".jsx", "ts", "typescript", "js", "javascript"):
        return _ts_string_lines(source, total_lines, all_lines)
    return _py_string_lines(source, total_lines, all_lines, io, tokenize)


def _py_string_lines(
    source: str, total_lines: int, all_lines: set[int], io_mod: any, tok_mod: any
) -> set[int]:
    lines: set[int] = set()
    try:
        g = tok_mod.generate_tokens(io_mod.StringIO(source).readline)
        for tok in g:
            if tok.type == tok_mod.STRING:
                s = tok.string.lstrip("rRbBuUfF")
                if s.startswith('"""') or s.startswith("'''"):
                    s_line = tok.start[0]
                    e_line = tok.end[0]
                    lines.update(range(s_line, e_line + 1))
    except (tok_mod.TokenError, SyntaxError, IndentationError, ValueError):
        return all_lines
    return lines


def _ts_string_lines(source: str, total_lines: int, all_lines: set[int]) -> set[int]:
    lines: set[int] = set()
    row = 1
    i = 0
    n = len(source)
    in_template: bool = False

    while i < n:
        ch = source[i]
        if not in_template:
            if ch == "`":
                in_template = True
                lines.add(row)
            elif ch == "\n":
                row += 1
        else:
            lines.add(row)
            if ch == "\\":
                i += 1
                if i < n and source[i] == "\n":
                    row += 1
            elif ch == "`":
                in_template = False
            elif ch == "\n":
                row += 1
        i += 1

    if in_template:
        return all_lines
    return lines
