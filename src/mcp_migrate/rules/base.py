"""Rule API.

A rule is a small class that inspects a Project and yields Findings.
Adding one is the main way to contribute -- see CONTRIBUTING.md.
"""
from __future__ import annotations

import ast
import io
import re
import tokenize
from dataclasses import dataclass, field
from pathlib import Path

SEVERITIES = ("breaking", "deprecated", "advisory")

# Token types that mark "content", not "code": comments and string/docstring
# bodies (including f-string pieces on interpreters new enough to tokenize
# them separately). A match that *starts* inside one of these spans is text
# a human wrote to *describe* something (a docstring, a --help string, a
# log message) rather than an actual reference the runtime will execute.
_STRING_TOKEN_TYPES = tuple(
    t for t in (
        tokenize.STRING,
        getattr(tokenize, "FSTRING_START", None),
        getattr(tokenize, "FSTRING_MIDDLE", None),
        getattr(tokenize, "FSTRING_END", None),
    ) if t is not None
)
_CONTENT_TOKEN_TYPES = (tokenize.COMMENT, *_STRING_TOKEN_TYPES)


@dataclass
class SourceFile:
    path: Path
    text: str
    tree: ast.AST | None = None

    @property
    def lines(self) -> list[str]:
        return self.text.splitlines()


@dataclass
class Project:
    """Everything a rule is allowed to look at."""

    root: Path
    files: list[SourceFile] = field(default_factory=list)
    _span_cache: dict = field(default_factory=dict, repr=False, compare=False)

    def search(self, pattern: str, *, flags: int = 0):
        """Yield (file, lineno, line) for every regex match across the project.

        This looks at the raw text of every line, comments and string
        literals included. Use it when a rule genuinely needs to read
        *content* -- e.g. R003 checking whether a header name appears
        anywhere in a docstring/log message, or R004 matching the literal
        JSON-RPC method name `tools/list`. For rules that mean to match
        *code* (an imported class, a real assignment, a real API call),
        use `search_code` instead so a docstring or `--help` string
        explaining the thing doesn't get mistaken for the thing.
        """
        rx = re.compile(pattern, flags)
        for f in self.files:
            for i, line in enumerate(f.lines, start=1):
                if rx.search(line):
                    yield f, i, line.strip()

    def search_code(self, pattern: str, *, flags: int = 0):
        """Like `search`, but ignores matches that start inside a comment
        or a string/docstring literal.

        For each file we tokenize the source with the stdlib `tokenize`
        module and record the (line, col) span of every COMMENT and
        STRING token (docstrings are just STRING tokens at module/class/
        function scope). A regex match is only yielded if the position
        where it *begins* does not fall inside one of those spans -- so
        `Mcp-Session-Id` inside a `logger.debug(...)` message or a
        `click.option(help=...)` string is skipped, but `Mcp-Session-Id`
        used as an actual header name/constant in code is still found.

        If a file fails to tokenize (e.g. it's not valid Python, or uses
        syntax the running interpreter's tokenizer chokes on), we fall
        back to plain, unfiltered `search` behaviour for that one file
        rather than silently dropping it.
        """
        rx = re.compile(pattern, flags)
        for f in self.files:
            spans = self._spans_for(f)
            for i, line in enumerate(f.lines, start=1):
                m = rx.search(line)
                if not m:
                    continue
                if spans is not None and _in_content_span(i, m.start(), spans):
                    continue
                yield f, i, line.strip()

    def _spans_for(self, f: SourceFile) -> list[tuple[tuple[int, int], tuple[int, int]]] | None:
        key = id(f)
        if key not in self._span_cache:
            self._span_cache[key] = _content_spans(f.text)
        return self._span_cache[key]

    def imports(self) -> set[str]:
        names: set[str] = set()
        for f in self.files:
            if f.tree is None:
                continue
            for node in ast.walk(f.tree):
                if isinstance(node, ast.Import):
                    names.update(a.name for a in node.names)
                elif isinstance(node, ast.ImportFrom) and node.module:
                    names.add(node.module)
        return names


def _content_spans(text: str) -> list[tuple[tuple[int, int], tuple[int, int]]] | None:
    """Return [(start, end), ...] token spans for every COMMENT/STRING
    token in `text`, or None if the file could not be tokenized (caller
    should fall back to unfiltered matching in that case)."""
    spans: list[tuple[tuple[int, int], tuple[int, int]]] = []
    try:
        for tok in tokenize.generate_tokens(io.StringIO(text).readline):
            if tok.type in _CONTENT_TOKEN_TYPES:
                spans.append((tok.start, tok.end))
    except (tokenize.TokenError, SyntaxError, IndentationError, ValueError):
        return None
    return spans


def _in_content_span(line: int, col: int, spans: list[tuple[tuple[int, int], tuple[int, int]]]) -> bool:
    for (srow, scol), (erow, ecol) in spans:
        if srow <= line <= erow:
            if srow == erow:
                if scol <= col < ecol:
                    return True
            elif line == srow:
                if col >= scol:
                    return True
            elif line == erow:
                if col < ecol:
                    return True
            else:
                return True
    return False


@dataclass
class Finding:
    rule_id: str
    message: str
    path: Path | None = None
    line: int | None = None
    snippet: str | None = None

    def location(self) -> str:
        if self.path is None:
            return "(project)"
        loc = str(self.path)
        if self.line:
            loc += f":{self.line}"
        return loc


class Rule:
    """Subclass this. Set the class attributes, implement check()."""

    id: str = ""
    title: str = ""
    severity: str = "advisory"  # breaking | deprecated | advisory
    spec_ref: str = ""
    fix: str = ""

    def check(self, project: Project) -> list[Finding]:  # pragma: no cover
        raise NotImplementedError

    # convenience for subclasses
    def finding(self, message: str, f: SourceFile | None = None,
                line: int | None = None, snippet: str | None = None) -> Finding:
        return Finding(
            rule_id=self.id,
            message=message,
            path=f.path if f else None,
            line=line,
            snippet=snippet,
        )
