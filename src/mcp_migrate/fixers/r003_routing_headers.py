"""Fixer for R003 -- Mcp-Method / Mcp-Name routing headers on hand-rolled HTTP.

Hand-rolled MCP wire traffic must carry routing headers so proxies can
dispatch without parsing the body. There is no single mechanical value for
every call site (method/name may be dynamic), so this fixer handles only
the narrowest safe shape -- an inline ``headers={...}`` dict on a
``.post()``/``.request()`` call -- and leaves a TODO everywhere else.
Confidence "review": header values still need a human pass.
"""
from __future__ import annotations

import ast
import re
from pathlib import Path

from mcp_migrate.rules.r003_routing_headers import (
    HAND_ROLLED_CALL,
    HTTP_LIBS,
    MCP_METHOD_RX,
    NAME_REQUIRED_RX,
    _imports_mcp,
)

from ._textedit import find_matching_close, leading_ws
from .base import Fixer, FixResult

COOKBOOK = "cookbook/14-routing-headers.md"
SPEC_URL = (
    "https://modelcontextprotocol.io/specification/2026-07-28/basic/transports/streamable-http"
)
TODO = (
    "# TODO(mcp-migrate): add Mcp-Method"
    " (and Mcp-Name for tools/call, resources/read, or prompts/get)"
    f" — see {SPEC_URL} and {COOKBOOK}"
)

POST_CALL_RX = re.compile(r"\.(?:post|request)\s*\(")
HEADERS_KW_RX = re.compile(r"\bheaders\s*=\s*\{")
METHOD_LITERAL_RX = re.compile(r"""["']method["']\s*:\s*["']([^"']+)["']""")
METHOD_IDENT_RX = re.compile(r"""["']method["']\s*:\s*([A-Za-z_][A-Za-z0-9_]*)""")
NAME_IDENT_RX = re.compile(r"""["']name["']\s*:\s*([A-Za-z_][A-Za-z0-9_]*)""")


def _file_context(source: str):
    """Return gating flags mirroring the R003 rule's per-file checks."""
    tree = None
    try:
        tree = ast.parse(source)
    except SyntaxError:
        pass

    class _F:
        def __init__(self, text: str, tree):
            self.text = text
            self.tree = tree
            self.lines = text.splitlines()

    f = _F(source, tree)
    has_http = any(lib in source for lib in HTTP_LIBS)
    mcp_surface = bool(MCP_METHOD_RX.search(source)) or _imports_mcp(f)
    requires_name = bool(NAME_REQUIRED_RX.search(source))
    missing_method = "Mcp-Method" not in source
    missing_name = requires_name and "Mcp-Name" not in source
    return has_http, mcp_surface, requires_name, missing_method, missing_name


def _method_value(call_span: str) -> str:
    m = METHOD_LITERAL_RX.search(call_span)
    if m:
        return f'"{m.group(1)}"'
    m = METHOD_IDENT_RX.search(call_span)
    if m:
        return m.group(1)
    return '"<set-mcp-method>"'


def _name_value(call_span: str) -> str:
    m = NAME_IDENT_RX.search(call_span)
    if m:
        return m.group(1)
    return '"<set-mcp-name>"'


def _insert_headers_entries(
    lines: list[str],
    open_i: int,
    open_col: int,
    close_i: int,
    close_col: int,
    *,
    add_method: bool,
    add_name: bool,
    method_val: str,
    name_val: str,
) -> None:
    """Insert Mcp-Method / Mcp-Name entries before the closing ``}``."""
    entries: list[str] = []
    if add_method:
        entries.append(f'"Mcp-Method": {method_val}')
    if add_name:
        entries.append(f'"Mcp-Name": {name_val}')
    if not entries:
        return

    if open_i == close_i:
        # Single-line headers={...} — splice comma-separated entries before ``}``.
        line = lines[close_i]
        inner = line[open_col + 1 : close_col].rstrip()
        suffix = line[close_col + 1 :]
        insertion = ", ".join(entries)
        if inner.strip():
            new_inner = f"{inner.rstrip()}, {insertion}"
        else:
            new_inner = insertion
        lines[close_i] = line[: open_col + 1] + new_inner + "}" + suffix
        return

    content_indent = None
    for k in range(open_i + 1, close_i + 1):
        if lines[k].strip():
            content_indent = leading_ws(lines[k])
            break
    if content_indent is None:
        content_indent = leading_ws(lines[open_i]) + "    "

    prev = close_i - 1
    while prev > open_i and not lines[prev].strip():
        prev -= 1
    if prev >= open_i:
        stripped = lines[prev].rstrip("\n")
        if stripped.strip() and not stripped.rstrip().endswith(","):
            nl = "\n" if lines[prev].endswith("\n") else ""
            lines[prev] = stripped.rstrip() + "," + nl

    insertion_lines = [f"{content_indent}{entry}," for entry in entries]
    newline = "\n" if lines[close_i].endswith("\n") else ""
    lines.insert(close_i, "".join(f"{line}{newline}" for line in insertion_lines))


def _headers_dict_in_call(lines: list[str], call_i: int, close_i: int):
    """Locate an inline headers={...} dict inside a .post/.request call."""
    for line_idx in range(call_i, close_i + 1):
        hm = HEADERS_KW_RX.search(lines[line_idx])
        if not hm:
            continue
        brace_col = hm.end() - 1
        h_closed = find_matching_close(lines, line_idx, brace_col)
        if h_closed is None:
            continue
        h_close_i, h_close_col = h_closed
        headers_span = (
            "".join(lines[line_idx : h_close_i + 1])
            if h_close_i > line_idx
            else lines[line_idx][brace_col : h_close_col + 1]
        )
        return line_idx, brace_col, h_close_i, h_close_col, headers_span
    return None


class RoutingHeadersFixer(Fixer):
    rule_id = "R003"
    title = "Add Mcp-Method/Mcp-Name to inline headers={} on hand-rolled POSTs, TODO elsewhere"
    confidence = "review"

    def fix(self, source: str, path: Path) -> FixResult:
        has_http, mcp_surface, requires_name, missing_method, missing_name = _file_context(source)
        if not has_http or not mcp_surface:
            return self.unchanged(source)
        if not missing_method and not missing_name:
            return self.unchanged(source)

        lines = source.splitlines(keepends=True)
        changes: list[str] = []
        fixed_call_lines: set[int] = set()

        # Pass 1: mechanical insert into inline headers={...} dicts.
        call_targets: list[tuple[int, int, int, int, str, bool, bool]] = []
        for i, line in enumerate(lines):
            m = POST_CALL_RX.search(line)
            if not m:
                continue
            open_col = m.end() - 1
            closed = find_matching_close(lines, i, open_col)
            if closed is None:
                continue
            close_i, close_col = closed
            located = _headers_dict_in_call(lines, i, close_i)
            if located is None:
                continue
            h_open_i, h_open_col, h_close_i, h_close_col, headers_span = located
            if "Mcp-Method" in headers_span and (not requires_name or "Mcp-Name" in headers_span):
                continue

            add_method = missing_method and "Mcp-Method" not in headers_span
            add_name = missing_name and requires_name and "Mcp-Name" not in headers_span
            if not add_method and not add_name:
                continue

            call_span = "".join(lines[i : close_i + 1])
            call_targets.append(
                (h_close_i, h_open_i, h_open_col, h_close_i, h_close_col, call_span, add_method, add_name)
            )
            fixed_call_lines.add(i)

        for (
            _sort_key,
            h_open_i,
            h_open_col,
            h_close_i,
            h_close_col,
            call_span,
            add_method,
            add_name,
        ) in sorted(call_targets, key=lambda t: t[0], reverse=True):
            method_val = _method_value(call_span)
            name_val = _name_value(call_span)
            _insert_headers_entries(
                lines,
                h_open_i,
                h_open_col,
                h_close_i,
                h_close_col,
                add_method=add_method,
                add_name=add_name,
                method_val=method_val,
                name_val=name_val,
            )
            changes.append(
                f"line {h_open_i + 1}: added routing headers to inline headers={{...}}"
            )

        # Pass 2: TODO above hand-rolled calls we could not fix mechanically.
        out: list[str] = []
        for i, raw_line in enumerate(lines):
            if i in fixed_call_lines:
                out.append(raw_line)
                continue
            if not HAND_ROLLED_CALL.search(raw_line):
                out.append(raw_line)
                continue
            stripped = raw_line.lstrip(" \t")
            if stripped.startswith("#"):
                out.append(raw_line)
                continue
            if raw_line.rstrip("\n").rstrip().endswith(":"):
                out.append(raw_line)
                continue

            indent = raw_line[: len(raw_line) - len(stripped)]
            newline = "\n" if raw_line.endswith("\n") else ""
            if not (out and out[-1].strip(" \t\n") == TODO):
                out.append(f"{indent}{TODO}{newline}")
                changes.append(f"line {i + 1}: added TODO for missing routing headers")
            out.append(raw_line)

        new_text = "".join(out)
        if not changes:
            return self.unchanged(source)
        return self.result(new_text, changes)
