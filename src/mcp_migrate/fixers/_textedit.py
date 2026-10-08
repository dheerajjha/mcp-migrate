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

# A `def`/`async def` header -- the one suite shape `sole_function_body_lines`
# recognises (see it for why the others are left to the #244 guard).
_DEF_HEADER_RX = re.compile(r"^\s*(?:async\s+)?def\b")
# The fixers that ask about function bodies also read TypeScript, where a
# line starting `def` is not a function at all, so the scan is gated to the
# files it is true for. Kept in sync with the "python" entries of
# `languages.EXTENSIONS`.
_PYTHON_SUFFIXES = frozenset({".py", ".pyi"})


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


def _live_line(line: str) -> bool:
    """True for a line that holds a suite open: not blank, not a comment."""
    stripped = line.strip()
    return bool(stripped) and not stripped.startswith("#")


def _opens_suite(line: str) -> bool:
    """True if `line` ends in the `:` that indents a block beneath it.

    A trailing comment is not part of the header, so `def f():  # noqa`
    counts. Splitting on the first `#` is the same shortcut
    `_strip_members_in_text` takes, and it errs the safe way: a `#` inside a
    string literal truncates the line, the colon goes missing, and the header
    is simply not recognised.
    """
    return line.split("#", 1)[0].rstrip().endswith(":")


def sole_function_body_lines(lines, path: Path) -> set[int]:
    """The 1-indexed lines that are the only live statement of a function body.

    Commenting one of those out leaves `def handlers():` with nothing under
    it, which does not parse -- so the #244 guard refuses the whole file and
    the user gets no fix at all. That is the sole-statement half of #245;
    callers keep an indented `pass` beside the TODO for these lines.

    The signal is indentation, not a parse: a body runs from its `def` header
    down to the next live line indented no deeper than the header, so the
    single live line under it is the whole body. That is Python's own rule
    for the shapes in question, and the only other read of the source is the
    `string_lines` call below -- which matters, because the file in hand is
    often mid-migration and may not parse at all. A header counts only when
    it plainly opens a block and is not string data, and the body only when
    one live line sits under it -- itself code rather than string data, since
    the repair edits that line -- so a docstring, a second statement or a
    nested block all decline the case on their own.

    Everything else keeps the pre-existing outcome, where the file is refused
    rather than edited (#244). That is the safe direction to be wrong in: a
    `pass` nobody needed is a stray no-op in someone's diff, while a missing
    one costs them the whole file.
    """
    if path.suffix.lower() not in _PYTHON_SUFFIXES:
        return set()
    # Prose is not structure: a `def` written inside a triple-quoted string is
    # a code example in a docstring, and a `pass` written under it would land
    # in the user's string data (the #105 family). `string_lines` is this
    # module's existing answer to "which lines are string data"; it fails safe
    # on source it cannot tokenize (every line comes back), which declines the
    # case rather than guessing at it.
    #
    # Headers only. A docstring is a statement like any other -- it is exactly
    # what keeps a body non-empty -- so body lines are counted as they are, and
    # filtering them out would invent a `pass` for a body that still holds one.
    string_data = string_lines("".join(lines), path)
    out: set[int] = set()
    for i, line in enumerate(lines):
        if i + 1 in string_data:
            continue
        if not _DEF_HEADER_RX.match(line) or not _opens_suite(line):
            continue
        header_indent = len(leading_ws(line))
        body = []
        for j in range(i + 1, len(lines)):
            if not _live_line(lines[j]):
                continue
            if len(leading_ws(lines[j])) <= header_indent:
                break  # dedented: the body ended, and it was not empty
            body.append(j)
        # The one line still has to be code. A docstring holding the flagged
        # name is the body's only statement *and* string data, and commenting
        # it out with a `pass` under it writes an edit inside the user's
        # string -- turning a #244 refusal into a parseable one (#105's
        # family). String data is counted as the statement it is, so that a
        # body keeping a docstring is never called empty; it just cannot be
        # the line the repair acts on.
        if len(body) == 1 and (body[0] + 1) not in string_data:
            out.add(body[0] + 1)
    return out


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


def comment_lines(source: str, path_or_lang: str | Path = "python") -> set[int]:
    """Return 1-indexed line numbers that are comment-only prose.

    Unlike `string_lines`, this answers the narrower question the fixers
    need when deciding whether an entire line is safe to ignore: a comment
    line should never be rewritten, but a real code line with a trailing
    explanatory comment still belongs to the fixer. Parsing failures return
    all lines as a fail-safe so line-based fixers decline to edit rather
    than guessing.
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
        return _ts_comment_lines(source, total_lines, all_lines)
    return _py_comment_lines(source, total_lines, all_lines, io, tokenize)


def cross_line_bracket_lines(source: str, path_or_lang: str | Path) -> set[int]:
    """Return 1-indexed lines at either end of a bracket pair that crosses lines.

    Commenting out either endpoint can remove a delimiter needed by the other
    line. Parsing failures return all lines as a fail-safe so fixers keep the
    original code and add only a TODO when the structure is ambiguous.
    """
    lines_list = source.splitlines()
    total_lines = len(lines_list)
    all_lines = set(range(1, total_lines + 1))
    if total_lines == 0:
        return set()

    if isinstance(path_or_lang, Path):
        lang = path_or_lang.suffix.lower()
    else:
        lang = str(path_or_lang).lower()

    if lang in (".py", ".pyi", "py", "python"):
        return _py_cross_line_bracket_lines(source, all_lines)
    if lang in (".ts", ".tsx", ".js", ".jsx", ".mts", ".cts", ".mjs", ".cjs",
                "ts", "typescript", "js", "javascript"):
        return _ts_cross_line_bracket_lines(source, all_lines)
    return set()


def _py_string_lines(
    source: str, total_lines: int, all_lines: set[int], io_mod: any, tok_mod: any
) -> set[int]:
    lines: set[int] = set()
    # PEP 701 (3.12+) stops emitting one STRING for an f-string: it splits the
    # literal into FSTRING_START / FSTRING_MIDDLE / FSTRING_END, so the STRING
    # branch below matches nothing and a multiline f-string used to come back
    # empty -- an empty set being indistinguishable from "no string data here"
    # for every caller, and unlike the fail-safe at the bottom it raises
    # nothing to trigger on. The two names do not exist before 3.12, where
    # `getattr` leaves them None and both branches below are unreachable, so
    # the <=3.11 single-STRING path is untouched: this is parity with it, not
    # a redesign of it.
    fstring_start = getattr(tok_mod, "FSTRING_START", None)
    fstring_end = getattr(tok_mod, "FSTRING_END", None)
    # A stack rather than one remembered span. An f-string nested inside a
    # replacement field pushes its own entry, so the END token that pops it is
    # the one that closes *it* -- pairing a START with the next END regardless
    # of nesting would end the outer span at the inner literal's closing
    # quotes and under-report the rest of it. Marking each popped entry on its
    # own also covers the mirror shape, where the inner literal is the
    # triple-quoted one and the outer is not: on <=3.11 that is exactly what
    # the tokenizer hands over as a STRING, because its own scanner finds the
    # inner `'''`, so marking it is parity too.
    open_fstrings: list[tuple[int, bool]] = []
    try:
        g = tok_mod.generate_tokens(io_mod.StringIO(source).readline)
        for tok in g:
            if tok.type == tok_mod.STRING:
                s = tok.string.lstrip("rRbBuUfF")
                if s.startswith('"""') or s.startswith("'''"):
                    s_line = tok.start[0]
                    e_line = tok.end[0]
                    lines.update(range(s_line, e_line + 1))
            elif fstring_start is not None and tok.type == fstring_start:
                head = tok.string.lstrip("rRbBuUfF")
                open_fstrings.append(
                    (tok.start[0], head.startswith('"""') or head.startswith("'''"))
                )
            elif fstring_end is not None and tok.type == fstring_end:
                if open_fstrings:
                    s_line, triple = open_fstrings.pop()
                    if triple:
                        # The whole literal, replacement fields included. On
                        # <=3.11 the single STRING token covers those lines
                        # too, so callers already treat them as string data;
                        # telling literal text from embedded code is a
                        # separate question this helper does not answer.
                        lines.update(range(s_line, tok.end[0] + 1))
    except (tok_mod.TokenError, SyntaxError, IndentationError, ValueError):
        return all_lines
    return lines


def _py_comment_lines(
    source: str, total_lines: int, all_lines: set[int], io_mod: any, tok_mod: any
) -> set[int]:
    lines: set[int] = set()
    try:
        g = tok_mod.generate_tokens(io_mod.StringIO(source).readline)
        for tok in g:
            if tok.type != tok_mod.COMMENT:
                continue
            # `tok.line` is the physical line the comment sits on. Splitting
            # the whole source again for every comment made this quadratic.
            if tok.line[: tok.start[1]].strip():
                continue
            lines.add(tok.start[0])
    except Exception:
        return all_lines
    return lines


def _py_cross_line_bracket_lines(source: str, all_lines: set[int]) -> set[int]:
    import io
    import tokenize

    stack: list[tuple[str, int]] = []
    crossed: set[int] = set()
    open_to_close = {"(": ")", "[": "]", "{": "}"}
    try:
        for tok in tokenize.generate_tokens(io.StringIO(source).readline):
            if tok.type != tokenize.OP:
                continue
            if tok.string in open_to_close:
                stack.append((tok.string, tok.start[0]))
                continue
            if tok.string not in open_to_close.values():
                continue
            if not stack or open_to_close[stack[-1][0]] != tok.string:
                return all_lines
            _, open_line = stack.pop()
            if open_line < tok.start[0]:
                crossed.add(open_line)
                crossed.add(tok.start[0])
    except (tokenize.TokenError, SyntaxError, IndentationError, ValueError):
        return all_lines
    return crossed


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


def _ts_cross_line_bracket_lines(source: str, all_lines: set[int]) -> set[int]:
    stack: list[tuple[str, int]] = []
    crossed: set[int] = set()
    open_to_close = {"(": ")", "[": "]", "{": "}"}
    close_to_open = {value: key for key, value in open_to_close.items()}
    i = 0
    line = 1
    col = 0
    n = len(source)
    while i < n:
        ch = source[i]
        nxt = source[i + 1] if i + 1 < n else ""

        if ch == "/" and nxt == "/":
            i += 2
            col += 2
            while i < n and source[i] != "\n":
                i += 1
                col += 1
            continue
        if ch == "/" and nxt == "*":
            i += 2
            col += 2
            closed = False
            while i < n:
                if source[i] == "\n":
                    i += 1
                    line += 1
                    col = 0
                    continue
                if source[i] == "*" and i + 1 < n and source[i + 1] == "/":
                    i += 2
                    col += 2
                    closed = True
                    break
                i += 1
                col += 1
            if not closed:
                return all_lines
            continue
        if ch in "\"'`":
            quote = ch
            i += 1
            col += 1
            while i < n:
                c = source[i]
                if c == "\n":
                    if quote != "`":
                        return all_lines
                    i += 1
                    line += 1
                    col = 0
                    continue
                if c == "\\":
                    if i + 1 >= n:
                        return all_lines
                    i += 2
                    col += 2
                    continue
                if c == quote:
                    i += 1
                    col += 1
                    break
                i += 1
                col += 1
            else:
                return all_lines
            continue

        if ch in open_to_close:
            stack.append((ch, line))
        elif ch in close_to_open:
            if not stack or stack[-1][0] != close_to_open[ch]:
                return all_lines
            _, open_line = stack.pop()
            if open_line < line:
                crossed.add(open_line)
                crossed.add(line)

        if ch == "\n":
            i += 1
            line += 1
            col = 0
            continue
        i += 1
        col += 1
    return crossed


def _ts_comment_lines(source: str, total_lines: int, all_lines: set[int]) -> set[int]:
    spans = _ts_comment_spans(source)
    if spans is None:
        return all_lines
    out: set[int] = set()
    source_lines = source.splitlines()
    for (start_line, start_col), (end_line, end_col) in spans:
        for line_no in range(start_line, end_line + 1):
            line_text = source_lines[line_no - 1]
            from_col = start_col if line_no == start_line else 0
            to_col = end_col if line_no == end_line else len(line_text)
            if line_text[:from_col].strip() or line_text[to_col:].strip():
                continue
            out.add(line_no)
    return out


def _ts_comment_spans(text: str) -> list[tuple[tuple[int, int], tuple[int, int]]] | None:
    spans: list[tuple[tuple[int, int], tuple[int, int]]] = []
    i = 0
    line = 1
    col = 0
    n = len(text)
    while i < n:
        ch = text[i]
        if ch == "/" and i + 1 < n and text[i + 1] == "/":
            start = (line, col)
            i += 2
            col += 2
            while i < n and text[i] != "\n":
                i += 1
                col += 1
            spans.append((start, (line, col)))
            continue
        if ch == "/" and i + 1 < n and text[i + 1] == "*":
            start = (line, col)
            i += 2
            col += 2
            closed = False
            while i < n:
                if text[i] == "\n":
                    i += 1
                    line += 1
                    col = 0
                    continue
                if text[i] == "*" and i + 1 < n and text[i + 1] == "/":
                    i += 2
                    col += 2
                    spans.append((start, (line, col)))
                    closed = True
                    break
                i += 1
                col += 1
            if not closed:
                return None
            continue
        if ch in "\"'`":
            quote = ch
            i += 1
            col += 1
            while i < n:
                c = text[i]
                if c == "\n":
                    if quote != "`":
                        return None
                    i += 1
                    line += 1
                    col = 0
                    continue
                if c == "\\":
                    if i + 1 >= n:
                        return None
                    i += 2
                    col += 2
                    continue
                if c == quote:
                    i += 1
                    col += 1
                    break
                i += 1
                col += 1
            else:
                return None
            continue
        if ch == "\n":
            i += 1
            line += 1
            col = 0
            continue
        i += 1
        col += 1
    return spans
