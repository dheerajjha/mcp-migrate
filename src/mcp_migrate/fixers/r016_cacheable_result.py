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

`fix()` only ever sees one file's text, so it cannot reproduce `check()`'s
project-wide search for an existing `cache_hints`/`cacheHints` config. It
does apply that same presence check to the file in front of it, which
covers the common shape -- hints configured in the same module that
registers the handlers. Without it the fixer annotated handlers that
`check` had just declared clean in the same run, which is the one thing a
fixer must not do: `check` is the tool's opinion, and `fix` contradicting
it reads as a bug in whichever the user believes.

Across files it stays generous, because there it has no choice: a
redundant reminder costs a human a few seconds to dismiss, a missing one
costs a silent spec violation nobody sees.
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

# Taken from the rule (`rules/r016_cacheable_result.py`) so the two agree on
# what "already configured" looks like. The rule searches the whole project
# for these; the fixer can only see one file, so it applies them to that
# file and stays silent when they are present.
CACHE_HINT_CONFIG_RX = re.compile(
    r"\bcache_hints\s*=|\bCacheHint\s*\(|\bcacheHints\b|\bcacheHint\s*:"
)


class CacheableResultFixer(Fixer):
    rule_id = "R016"
    title = "Annotate list/read handlers missing ttlMs/cacheScope with a TODO"
    confidence = "review"

    def fix(self, source: str, path: Path) -> FixResult:
        # This file already configures cache hints, so the rule would not
        # have reported it. Annotating anyway would have `fix` contradict
        # `check` on the same file in the same run.
        if CACHE_HINT_CONFIG_RX.search(source):
            return self.unchanged(source)

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
