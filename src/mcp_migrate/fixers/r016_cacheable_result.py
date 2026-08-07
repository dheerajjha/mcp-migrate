"""Fixer for R016 -- list/read results missing `ttlMs`/`cacheScope`.

Unlike most fixers here, there's no default value to insert: how long a
particular list response stays valid, and whether that varies per caller,
is a judgment call only the person who owns the data can make. A wrong
guess is worse than the missing field -- a `cacheScope` too wide can serve
one client's data to another out of cache (see cookbook/05). So this fixer
never writes `ttlMs`/`cacheScope` itself.

What it can do, the same as R008/R018 for the same reason, is find the
handler that needs them and drop a TODO right above it pointing at the
cookbook recipe. The handler itself is untouched. Confidence "review":
every flagged site still needs a human pass to pick the actual values.

Unlike the rule this mirrors, `fix()` only ever sees one file's text, so it
can't check whether `cache_hints`/`cacheHints` is already configured
elsewhere in the project the way `check()` does. It flags the handler
shape on sight, generous in the same direction as the rule's own presence
check: a redundant reminder costs a human a few seconds to dismiss, a
missing one costs a silent spec violation nobody sees.
"""
from __future__ import annotations

import re
from pathlib import Path

from .base import Fixer, FixResult, comment_prefix, is_commented

SPEC_URL = "https://modelcontextprotocol.io/specification/2026-07-28/changelog"
COOKBOOK = "cookbook/05-result-type-and-cache-metadata.md"
TODO = (
    "TODO(mcp-migrate): this result needs ttlMs/cacheScope (CacheableResult) -- "
    f"pick values for how long and how broadly it may be cached, see {SPEC_URL} "
    f"and {COOKBOOK}"
)

# Same handler shapes the rule itself looks for -- Python decorators and the
# two TypeScript idioms (low-level schema, low-level wire method literal).
CALL_SITE_RX = re.compile(
    r"@[\w.]*\.(?:list_tools|list_prompts|list_resources|read_resource|"
    r"list_resource_templates)\s*\("
    r"|setRequestHandler\s*\(\s*(?:ListTools|ListPrompts|ListResources|"
    r"ReadResource|ListResourceTemplates)RequestSchema\b"
    r"|setRequestHandler\s*\(\s*[\"'](?:tools/list|prompts/list|resources/list|"
    r"resources/read|resources/templates/list)[\"']"
)


class CacheableResultFixer(Fixer):
    rule_id = "R016"
    title = "Annotate list/read handlers missing ttlMs/cacheScope with a TODO"
    confidence = "review"

    def fix(self, source: str, path: Path) -> FixResult:
        lines = source.splitlines(keepends=True)
        out: list[str] = []
        changes: list[str] = []

        prefix = comment_prefix(path)
        todo = f"{prefix}{TODO}"

        for i, raw_line in enumerate(lines, start=1):
            stripped = raw_line.lstrip(" \t")
            already_commented = is_commented(raw_line)

            if (
                not already_commented
                and CALL_SITE_RX.search(raw_line)
                and not (out and out[-1].strip(" \t\n") == todo)
            ):
                indent = raw_line[: len(raw_line) - len(stripped)]
                newline = "\n" if raw_line.endswith("\n") else ""
                out.append(f"{indent}{todo}{newline}")
                changes.append(f"line {i}: annotated cacheable handler with TODO")

            out.append(raw_line)

        if not changes:
            return self.unchanged(source)
        return self.result("".join(out), changes)
