"""Fixer for R005 -- ServerCapabilities declared without `extensions`.

Adds `extensions={}` to a `ServerCapabilities(...)` constructor call that
doesn't already have one. This can never change existing behaviour --
`extensions` is new in 2026-07-28 and an absent value already meant "no
extensions" -- so declaring the empty map explicitly is a pure no-op at
runtime and confidence "safe".
"""
from __future__ import annotations

import re
from pathlib import Path

from ._textedit import find_matching_close, leading_ws
from .base import Fixer, FixResult

CTOR_RX = re.compile(r"\bServerCapabilities\s*(\()")
EXTENSIONS_WORD_RX = re.compile(r"\bextensions\b")


class ExtensionsFixer(Fixer):
    rule_id = "R005"
    title = "Add extensions={} to a ServerCapabilities(...) construction"
    confidence = "safe"

    def fix(self, source: str, path: Path) -> FixResult:
        lines = source.splitlines(keepends=True)
        changes: list[str] = []
        # Find call sites by searching each line individually, so the
        # column of the matched "(" is already line-relative -- exactly
        # what `find_matching_close` expects. Collect them all against the
        # unmutated lines first, then apply bottom-to-top: the multi-line
        # branch below can `lines.insert(...)` a brand new line, which
        # shifts every later line index, so an earlier call site's line
        # number must stay valid while later ones are rewritten first.
        targets = []
        for i, line in enumerate(lines):
            m = CTOR_RX.search(line)
            if not m:
                continue
            open_col = m.end(1) - 1
            closed = find_matching_close(lines, i, open_col)
            if closed is None:
                continue
            targets.append((i, open_col, *closed))

        for open_i, open_col, close_i, close_col in sorted(targets, key=lambda t: t[0], reverse=True):
            span_text = "".join(lines[open_i:close_i + 1]) if close_i > open_i \
                else lines[open_i][open_col:close_col + 1]
            if EXTENSIONS_WORD_RX.search(span_text):
                continue  # already declares extensions (possibly by a prior run)

            if close_i == open_i:
                line = lines[open_i]
                inner = line[open_col + 1:close_col]
                insertion = "extensions={}" if not inner.strip() else ", extensions={}"
                lines[open_i] = line[:close_col] + insertion + line[close_col:]
            else:
                # Multi-line call: insert a new `extensions={},` line right
                # before the closing paren, indented like its sibling
                # kwargs, and make sure the kwarg line above it ends with a
                # comma so the list stays valid Python.
                content_indent = None
                for k in range(open_i + 1, close_i):
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

                newline = "\n" if lines[close_i].endswith("\n") or close_i < len(lines) - 1 else ""
                lines.insert(close_i, f"{content_indent}extensions={{}},{newline}")

            changes.append(f"line {open_i + 1}: added extensions={{}} to ServerCapabilities(...)")

        if not changes:
            return self.unchanged(source)
        return self.result("".join(lines), changes)
