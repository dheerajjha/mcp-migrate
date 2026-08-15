"""Small text-editing helpers shared by fixers.

Not a fixer itself (no `Fixer` subclass lives here), so `all_fixers()`'s
module scan finds nothing to register from this file -- it's just plumbing.

These operate on plain text/line lists on purpose, not the AST: fixers must
preserve comments and formatting, so every edit here is a line/column
splice, never an `ast.unparse` round-trip.
"""
from __future__ import annotations

import re
from pathlib import Path

OPEN = "([{"
CLOSE = ")]}"

# A parenthesised `from x import (` opener: the only import shape where a
# fixer commenting out a member line leaves `from x import ( )`, which does
# not parse (see `strip_parenthesised_import_members`).
_FROM_IMPORT_PAREN_RX = re.compile(r"^\s*from\s+\S+\s+import\s*\(")


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


def strip_import_members(lines, hit_fn, todo, label):
    """Remove members of parenthesised `from x import (...)` statements whose
    names ``hit_fn`` flags, instead of commenting the member lines out.

    Commenting every member leaves ``from mcp.types import ( )``, which does
    not parse, so the fix guard would refuse the whole file and nothing would
    be fixed (#245). Removing the name keeps the import valid at every
    intermediate state; if the list empties, the statement is removed
    entirely. The TODO is placed above the ``from`` statement once.

    ``hit_fn`` receives a single member name and returns a truthy description
    when the fixer should drop it. Returns ``(new_lines, changes)`` where
    ``changes`` describes each edited statement.
    """
    new_lines = list(lines)
    changes: list[str] = []
    i = 0
    while i < len(new_lines):
        if not _FROM_IMPORT_PAREN_RX.match(new_lines[i]):
            i += 1
            continue
        open_idx = i
        open_col = new_lines[i].index("(")
        close = find_matching_close(new_lines, open_idx, open_col)
        if close is None:
            i += 1
            continue
        close_idx, close_col = close

        edited_any = False
        remaining_any = False

        if close_idx == open_idx:
            # Single-line import: edit the member text between the parens once.
            head, tail = new_lines[open_idx][: open_col + 1], new_lines[open_idx][close_col:]
            middle = new_lines[open_idx][open_col + 1 : close_col]
            edited, remaining, changed = _strip_members_in_text(middle, hit_fn)
            if changed:
                new_lines[open_idx] = head + edited + tail
                edited_any = True
                remaining_any = remaining
        else:
            # Open line: member text after '(' (exclude the close paren).
            head, tail = new_lines[open_idx][: open_col + 1], ""
            middle = new_lines[open_idx][open_col + 1 :]
            edited, remaining, changed = _strip_members_in_text(middle, hit_fn)
            if changed:
                new_lines[open_idx] = head + edited + tail
                edited_any = True
                remaining_any = remaining or remaining_any
            elif middle.strip():
                remaining_any = True  # untouched member text on the open line
            # Middle member lines.
            for j in range(open_idx + 1, close_idx):
                line = new_lines[j]
                stripped = line.strip()
                if not stripped or stripped.startswith(("#", "//")):
                    continue
                edited, remaining, changed = _strip_members_in_text(line, hit_fn)
                if not changed:
                    remaining_any = True  # untouched member line: list non-empty
                    continue
                # A member-only line whose name was removed leaves just
                # indentation -- blank it instead of leaving trailing
                # whitespace (the import itself stays valid).
                new_lines[j] = "" if not edited.strip(" \t\n") else edited
                edited_any = True
                remaining_any = remaining or remaining_any
            # Close line: member text before ')'.
            if new_lines[close_idx][:close_col].strip():
                head, tail = "", new_lines[close_idx][close_col:]
                middle = new_lines[close_idx][:close_col]
                edited, remaining, changed = _strip_members_in_text(middle, hit_fn)
                if changed:
                    new_lines[close_idx] = head + edited + tail
                    edited_any = True
                    remaining_any = remaining or remaining_any
                else:
                    remaining_any = True  # untouched member text on the close line

        if not edited_any:
            i = close_idx + 1
            continue
        indent = leading_ws(new_lines[open_idx])
        if remaining_any:
            new_lines.insert(open_idx, f"{indent}{todo}\n")
            changes.append(f"line {open_idx + 1}: removed {label} member(s) from the import")
            i = close_idx + 2
        else:
            # The list emptied: drop the whole statement, keep the TODO.
            new_lines[open_idx : close_idx + 1] = [f"{indent}{todo}\n"]
            changes.append(f"line {open_idx + 1}: removed {label}; empty import dropped")
            i = open_idx + 1
    return new_lines, changes


def _strip_members_in_text(text, hit_fn):
    """Remove comma-separated members that ``hit_fn`` flags from ``text``.

    Returns ``(new_text, remaining_any, changed)``. Leading indentation and a
    trailing comment/newline are preserved; a line whose members are all
    removed becomes indentation-only (the caller keeps or drops the line).
    """
    newline = "\n" if text.endswith("\n") else ""
    body = text[: len(text) - len(newline)]
    indent = leading_ws(body)
    stripped = body.strip()
    comment = ""
    core = stripped
    if "#" in core:
        comment = core[core.index("#") :]
        core = core[: core.index("#")]
    trailing_comma = core.rstrip().endswith(",")
    core = core.rstrip().rstrip(",").strip()
    if not core:
        return text, False, False
    parts = [p.strip() for p in core.split(",") if p.strip()]
    kept = [p for p in parts if not hit_fn(p)]
    if len(kept) == len(parts):
        return text, True, False
    if not kept:
        return indent + newline, False, True
    joined = ", ".join(kept)
    if trailing_comma:
        joined += ","
    if comment:
        joined += "  " + comment
    return indent + joined + newline, True, True


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
