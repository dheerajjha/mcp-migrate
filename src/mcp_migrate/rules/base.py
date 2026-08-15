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
    # `tree` is Python-only and stays None for every other language. Rules
    # that walk the AST must therefore declare `languages = ("python",)`,
    # which is the default -- see Rule below.
    language: str = "python"

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

    def search_wire(self, pattern: str, *, flags: int = 0):
        """Like `search`, but ignores matches inside comments and
        triple-quoted strings.

        The middle setting between `search` and `search_code`, and the
        right one for removed JSON-RPC method names.

        Those names (`notifications/initialized`, `resources/subscribe`,
        `tools/list`, ...) can only ever appear as string *literals* -- they
        are not valid identifiers -- so `search_code`, which skips every
        string token, would never find them at all. But plain `search`
        finds them in prose too, and prose is where people explain the
        protocol: a module docstring reading "Runs the MCP handshake
        (initialize -> notifications/initialized)" is documentation, not an
        implementation of it. That exact line produced a `breaking` finding
        on a real server, which is the `Mcp-Session-Id`-in-a-help-string
        mistake wearing a different hat.

        The split that works: real wire names live in short quoted strings
        (`{"method": "tools/list"}`), explanations live in comments and
        triple-quoted blocks. So skip those two and keep everything else.
        """
        rx = re.compile(pattern, flags)
        for f in self.files:
            spans = self._prose_spans_for(f)
            for i, line in enumerate(f.lines, start=1):
                m = rx.search(line)
                if not m:
                    continue
                if spans is not None and _in_content_span(i, m.start(), spans):
                    continue
                yield f, i, line.strip()

    @property
    def language(self) -> str | None:
        """The language of this view's files, or None if it's empty.

        Rules are always handed a single-language view (see
        `for_language`), so a multi-language rule can branch on this rather
        than inspecting individual files.
        """
        return self.files[0].language if self.files else None

    def for_language(self, language: str) -> Project:
        """A view of this project containing only files in `language`.

        The rule engine hands each rule one of these rather than the whole
        project, so a Python-only rule can never see a `.ts` file. That
        matters more than it looks: `search_code` skips comments and
        strings by *tokenizing* the file, and a TypeScript file fails to
        tokenize as Python, which makes it fall back to unfiltered raw
        matching -- so every Python rule would quietly start reporting
        matches from TypeScript comments the moment TS files were loaded.
        """
        return Project(root=self.root,
                       files=[f for f in self.files if f.language == language])

    def _spans_for(self, f: SourceFile) -> list[tuple[tuple[int, int], tuple[int, int]]] | None:
        key = id(f)
        if key not in self._span_cache:
            self._span_cache[key] = (
                _ts_spans(f.text, prose_only=False)
                if f.language in {"typescript", "javascript"}
                else _content_spans(f.text)
            )
        return self._span_cache[key]

    def _prose_spans_for(self, f: SourceFile) -> list[tuple[tuple[int, int], tuple[int, int]]] | None:
        key = ("prose", id(f))
        if key not in self._span_cache:
            self._span_cache[key] = (
                _ts_spans(f.text, prose_only=True)
                if f.language in {"typescript", "javascript"}
                else _prose_spans(f.text)
            )
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


def _ts_spans(text: str, *, prose_only: bool) -> list[tuple[tuple[int, int], tuple[int, int]]]:
    """Comment (and optionally string) spans for TypeScript/JavaScript.

    A hand-rolled scanner rather than a real parser, deliberately: pulling
    in a JS grammar to answer "is this match inside a comment" would be a
    heavy dependency for a tool whose rules are all textual anyway. It
    tracks line comments, block comments, and the three string forms
    (`'`, `"`, backtick), honouring backslash escapes.

    `prose_only=True` returns comments alone -- the TypeScript analogue of
    `_prose_spans`. Removed JSON-RPC method names live in ordinary quoted
    strings in TS exactly as they do in Python, while the prose explaining
    them lives in `//` and JSDoc `/** */` comments.

    Known gap, and a good first contribution: a regex literal containing a
    quote (`/["']/`) can start a phantom string. It is rare in MCP server
    code and it fails toward *fewer* findings, never toward a false one.
    """
    spans: list[tuple[tuple[int, int], tuple[int, int]]] = []
    row, col, i, n = 1, 0, 0, len(text)
    state: str | None = None
    start: tuple[int, int] | None = None

    while i < n:
        ch = text[i]
        nxt = text[i + 1] if i + 1 < n else ""

        if state is None:
            if ch == "/" and nxt == "/":
                state, start = "line", (row, col)
                i, col = i + 2, col + 2
                continue
            if ch == "/" and nxt == "*":
                state, start = "block", (row, col)
                i, col = i + 2, col + 2
                continue
            if ch in "\"'`" and not prose_only:
                state, start = ch, (row, col)
                i, col = i + 1, col + 1
                continue
            if ch in "\"'`":
                # prose_only: still consume the string so a quote inside it
                # can't be mistaken for the start of one.
                state, start = ch, None
                i, col = i + 1, col + 1
                continue
        elif state == "line":
            if ch == "\n":
                if start:
                    spans.append((start, (row, col)))
                state, start = None, None
        elif state == "block":
            if ch == "*" and nxt == "/":
                i, col = i + 2, col + 2
                if start:
                    spans.append((start, (row, col)))
                state, start = None, None
                continue
        else:  # inside a string literal
            if ch == "\\":
                i, col = i + 2, col + 2
                continue
            if ch == state:
                i, col = i + 1, col + 1
                if start:
                    spans.append((start, (row, col)))
                state, start = None, None
                continue
            if ch == "\n" and state != "`":
                # Unterminated ordinary string -- don't swallow the file.
                if start:
                    spans.append((start, (row, col)))
                state, start = None, None

        if ch == "\n":
            row, col = row + 1, 0
        else:
            col += 1
        i += 1

    if start is not None:
        spans.append((start, (row, col)))
    return spans


def _is_triple_quoted(tok_string: str) -> bool:
    """True for a STRING token written with triple quotes.

    Strips any prefix (r, b, f, rb, ...) before looking at the quotes, so
    an f-string docstring-shaped block is still recognised.
    """
    s = tok_string.lstrip("rRbBuUfF")
    return s.startswith('"""') or s.startswith("'''")


def _prose_spans(text: str) -> list[tuple[tuple[int, int], tuple[int, int]]] | None:
    """Spans of every COMMENT and every triple-quoted STRING token.

    Deliberately *not* every string: single-line quoted strings are where
    real JSON-RPC method names live, and excluding them would make the
    wire-name rules find nothing at all.
    """
    spans: list[tuple[tuple[int, int], tuple[int, int]]] = []
    try:
        for tok in tokenize.generate_tokens(io.StringIO(text).readline):
            if tok.type == tokenize.COMMENT or (
                tok.type == tokenize.STRING and _is_triple_quoted(tok.string)
            ):
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
    # The named feature this finding is about ("Sampling", "roots/list",
    # ...), set by rules that classify their matches. overlap.py groups known
    # rule pairs on this instead of on the line number, so two rules that
    # describe the same underlying fact merge even when they matched
    # different symbols on different lines. Optional: rules without a
    # feature classification leave it unset and dedupe falls back to the
    # line key.
    feature: str | None = None

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

    # Which languages this rule knows how to read. The engine calls check()
    # once per declared language, with a Project filtered to just those
    # files, so a rule never has to think about the others.
    #
    # Default is Python only, which is the safe default: a rule written
    # against Python idioms will produce nonsense on a .ts file, and the
    # spec change being detected is language-independent but the *detection*
    # never is. Add "typescript" only once you have checked the patterns
    # actually hold there -- see r001 and r006 for worked examples.
    languages: tuple[str, ...] = ("python",)

    def check(self, project: Project) -> list[Finding]:  # pragma: no cover
        raise NotImplementedError

    # convenience for subclasses
    def finding(self, message: str, f: SourceFile | None = None,
                line: int | None = None, snippet: str | None = None,
                feature: str | None = None) -> Finding:
        return Finding(
            rule_id=self.id,
            message=message,
            path=f.path if f else None,
            line=line,
            snippet=snippet,
            feature=feature,
        )


def wire_method(*names: str) -> str:
    r"""Build a regex pattern for JSON-RPC wire method names bounded by (?![\w/-]).

    Prevents false positives on longer, unrelated strings like 'roots/listeners'
    or 'tasks/listeners'.
    """
    if len(names) == 1:
        return rf"\b{re.escape(names[0])}(?![\w/-])"
    joined = "|".join(re.escape(n) for n in names)
    return rf"\b(?:{joined})(?![\w/-])"


# Evidence that a file speaks MCP at all, independent of the token a rule
# matched. Some SDK names are distinctive enough to stand alone
# (`RegisterClientRequest`, `ListToolsRequestSchema`); others are ordinary
# words the SDK happens to also use (`register_client`, `capabilities`,
# `ping`), and for those the token proves nothing on its own -- a
# connection pool registering clients is not implementing RFC 7591.
#
# Deliberately broad, because it is used to *keep* findings rather than to
# create them: an import of the SDK in either language, or a reference to
# any of MCP's own wire method names, or a JSON-RPC envelope. Narrowing it
# turns real findings into silence, which is the direction that costs a
# user a broken server rather than three points on a grade.
#
# Language-agnostic on purpose. A Python file importing the TypeScript
# package name is not a thing, so including both costs nothing, and it
# means a rule does not have to pick a gate per language and get them
# subtly out of step -- which is the failure #107 was about.
# The wire names below go through wire_method() rather than being spelled
# inline, and that is not tidiness. An unbounded `logging/setLevel` also
# matches `logging/setLevelLatency` -- a metric name, not MCP surface --
# which is #88's bug reappearing on the other side of the telescope: there
# it invented findings, here it would *keep* ones that should be gated
# away. The gate has to be at least as careful as the rules it gates.
MCP_SURFACE_RX = re.compile(
    r"@modelcontextprotocol"
    r"|\bmcp\.server\b|\bmcp\.types\b|\bmcp\.client\b|\bfrom\s+mcp\b|\bimport\s+mcp\b"
    r"|\bmodelcontextprotocol\b"
    r"|\bjsonrpc\b"
    "|" + wire_method(
        "tools/call", "tools/list", "resources/read", "resources/list",
        "prompts/get", "prompts/list", "sampling/createMessage", "roots/list",
        "logging/setLevel", "server/discover",
    ),
    re.IGNORECASE,
)


def mcp_surface_paths(project: "Project") -> set:
    """Paths of files in `project` that show any independent MCP surface.

    Use to gate a token that is only suspicious *because* the SDK also uses
    it. Do not use to gate a token that is already distinctive -- that adds
    a way to miss a real finding and buys nothing.
    """
    return {f.path for f in project.files if MCP_SURFACE_RX.search(f.text)}

