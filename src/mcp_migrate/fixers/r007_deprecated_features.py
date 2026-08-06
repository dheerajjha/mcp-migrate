"""Fixer for R007 -- Roots, Sampling and Logging deprecated as core capabilities.

There is no mechanical replacement for any of these: Roots wants resource
URIs, Sampling wants a multi-round-trip design, Logging wants an extension.
So this fixer does the one thing that is safe without understanding the
surrounding code -- leave a loud TODO exactly where the human needs to look,
and comment out only lines where doing so cannot break syntax (single-line
statements, not block openers, not the opening line of a multiline call).
Confidence "review": every flagged site still needs a human pass.
"""
from __future__ import annotations

import re
from pathlib import Path

from .base import Fixer, FixResult, comment_prefix, is_commented

SPEC_URL = "https://modelcontextprotocol.io/specification/draft/changelog"
COOKBOOK = "cookbook/18-roots-sampling-logging-deprecated.md"

# Mirrors r007_deprecated_features.FEATURES -- same patterns, same precision.
FEATURES: dict[str, str] = {
    r"\broots/list\b|list_roots|RootsCapability": "Roots",
    r"sampling/createMessage|SamplingCapability|\bsession\.create_message\b"
    r"|\bCreateMessageRequest\b|\bCreateMessageResult\b": "Sampling",
    r"notifications/message|LoggingCapability|set_logging_level": "Logging",
}
FEATURE_RX = tuple((re.compile(p), name) for p, name in FEATURES.items())


def _todo(feature: str, prefix: str) -> str:
    return (
        f"{prefix}TODO(mcp-migrate): {feature} is deprecated as a core capability; "
        f"see {SPEC_URL} and {COOKBOOK}"
    )


def _feature_on_line(line: str) -> str | None:
    for rx, name in FEATURE_RX:
        if rx.search(line):
            return name
    return None


def _safe_to_comment_out(line: str) -> bool:
    """Commenting out must not leave a dangling suite or multiline expression."""
    stripped = line.rstrip("\n").rstrip()
    if stripped.endswith(":"):
        return False
    if stripped.endswith(("(", "[", "{", "\\")):
        return False
    return True


class DeprecatedCoreFeaturesFixer(Fixer):
    rule_id = "R007"
    title = "Annotate deprecated Roots/Sampling/Logging usage with a TODO"
    confidence = "review"

    def fix(self, source: str, path: Path) -> FixResult:
        lines = source.splitlines(keepends=True)
        out: list[str] = []
        changes: list[str] = []

        prefix = comment_prefix(path)

        for i, raw_line in enumerate(lines, start=1):
            stripped = raw_line.lstrip(" \t")
            already_commented = is_commented(raw_line)
            feature = None if already_commented else _feature_on_line(raw_line)

            if feature:
                indent = raw_line[: len(raw_line) - len(stripped)]
                newline = "\n" if raw_line.endswith("\n") else ""
                todo = _todo(feature, prefix)
                body = stripped.rstrip("\n")

                if not (out and out[-1].strip(" \t\n") == todo):
                    out.append(f"{indent}{todo}{newline}")
                if _safe_to_comment_out(raw_line):
                    out.append(f"{indent}{prefix}{body}{newline}")
                    changes.append(
                        f"line {i}: commented out deprecated {feature} usage, added TODO"
                    )
                else:
                    out.append(raw_line)
                    changes.append(
                        f"line {i}: added TODO for deprecated {feature} usage"
                    )
            else:
                out.append(raw_line)

        new_text = "".join(out)
        if not changes:
            return self.unchanged(source)
        return self.result(new_text, changes)
