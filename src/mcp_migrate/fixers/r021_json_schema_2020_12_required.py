"""Fixer for R021 -- older JSON Schema dialect pin.

SEP-2106 (2026-07-28) requires MCP implementations to support at least
JSON Schema 2020-12 for inputSchema/outputSchema. Explicitly pinning an
older draft (draft-07, 2019-09, etc.) via a ``$schema`` URL key is a
mechanical, unambiguous rewrite: the old dialect URL string becomes the
canonical 2020-12 URL.

Confidence ``safe`` because:
- The match is anchored to a ``"$schema"`` key on the same line, so the
  regex cannot hit a comment, a log message, or an unrelated dialect
  mention that just happens to contain the old URL string.
- The transformation is an exact string substitution of the dialect
  segment of the URL; no structural changes to the surrounding code.
- When the pattern is ambiguous (e.g. the old dialect string appears on a
  line that does *not* look like a ``"$schema"`` assignment), the fixer
  backs off and leaves the line untouched rather than guess.
"""
from __future__ import annotations

import re
from pathlib import Path

from .base import Fixer, FixResult

# The authoritative 2020-12 $schema URL (no trailing #)
_TARGET_DIALECT = "https://json-schema.org/draft/2020-12/schema"

# Matches the old-dialect string only when it appears on the same line as
# a "$schema": assignment (JSON, Python dict literal, YAML mapping, etc.).
# The look-behind ensures there is a "$schema" key somewhere to the left;
# the pattern then captures the old URL so we can replace just the URL
# portion and leave surrounding quotes/whitespace intact.
#
# Matches:
#   "$schema": "http://json-schema.org/draft-07/schema#"
#   "$schema": "http://json-schema.org/draft-04/schema"
#   "$schema": "https://json-schema.org/draft/2019-09/schema"
#   "$schema" = "http://json-schema.org/draft-07/schema#"   (Python)
#
# Does NOT match:
#   # old schema was draft-07         (no $schema key on the same line)
#   some_other_key = "draft-07"       (no $schema key on the same line)
_SCHEMA_KEY_RX = re.compile(
    r"""
    \"\$schema\"          # the "$schema" key (JSON / Python dict key)
    \s*[:=]\s*            # colon (JSON/YAML) or equals (Python)
    \"                    # opening quote of the value
    (                     # capture group 1: the entire URL value we will replace
        https?://
        (?:json-schema\.org/draft-(?:0[1-7])/schema  # draft-01 through draft-07
        |json-schema\.org/draft/2019-09/schema        # 2019-09 by path
        )
        [^"]*             # trailing fragment (#) or nothing
    )
    \"                    # closing quote
    """,
    re.VERBOSE,
)

# Also match bare 2019-09 mentions as a $schema value (some tools write
# the short form: "$schema": "2019-09")
_SCHEMA_KEY_SHORT_RX = re.compile(
    r"""
    \"\$schema\"
    \s*[:=]\s*
    \"
    (2019-09|draft-0[1-7])   # short form dialect pins
    \"
    """,
    re.VERBOSE,
)

# Guard: already the 2020-12 dialect -- do not touch these lines
_ALREADY_2020_RX = re.compile(r"2020-12")


class OldJSONSchemaDialectFixer(Fixer):
    rule_id = "R021"
    title = "Rewrite older JSON Schema dialect pin to 2020-12"
    confidence = "safe"

    def fix(self, source: str, path: Path) -> FixResult:
        lines = source.splitlines(keepends=True)
        changes: list[str] = []

        for i, line in enumerate(lines):
            # Already on 2020-12 -- skip (idempotency guard)
            if _ALREADY_2020_RX.search(line):
                continue

            new_line = line

            # Full URL form: replace captured URL with the target
            m = _SCHEMA_KEY_RX.search(new_line)
            if m:
                new_line = new_line[: m.start(1)] + _TARGET_DIALECT + new_line[m.end(1) :]
                changes.append(
                    f"line {i + 1}: $schema dialect {m.group(1)!r} -> {_TARGET_DIALECT!r}"
                )
            else:
                # Short form: replace the short dialect token with full URL
                m2 = _SCHEMA_KEY_SHORT_RX.search(new_line)
                if m2:
                    new_line = (
                        new_line[: m2.start(1)] + _TARGET_DIALECT + new_line[m2.end(1) :]
                    )
                    changes.append(
                        f"line {i + 1}: $schema dialect {m2.group(1)!r} -> {_TARGET_DIALECT!r}"
                    )

            lines[i] = new_line

        if not changes:
            return self.unchanged(source)
        return self.result("".join(lines), changes)
