"""Fixer API.

A fixer is a small class that turns the source text of a single file into
repaired source text for one specific rule. It mirrors the shape of
`rules/base.py`'s `Rule` on purpose -- same discovery mechanism, same "one
file, one class, drop it in the package" workflow -- so anyone who has
already read CONTRIBUTING.md's rule-writing section can write a fixer.

Fixers are deliberately *not* built on `ast.unparse`. Round-tripping through
the AST throws away comments, string-quote style, blank lines and exact
formatting, which would turn every fix into an unreviewable, unrelated diff.
Instead a fixer does line/regex-level surgery on the original text, so the
diff a human reviews is exactly the change being made and nothing else.

When a fixer cannot be sure a transformation is correct, it must return the
source unchanged rather than guess. A wrong fix that silently corrupts
someone's server is worse than reporting the finding and doing nothing.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

CONFIDENCES = ("safe", "review")

# Suffixes whose line comment is `//` rather than `#`.
#
# Kept in sync with the C-family entries of `languages.EXTENSIONS` -- and
# deliberately including the `.mts`/`.cts`/`.mjs`/`.cjs` module variants,
# which the scanner already reads and which an earlier hardcoded list here
# missed. A suffix absent from this set falls back to `#`, so the failure
# mode of forgetting one is a `#` in a C-family file: exactly the bug this
# module exists to prevent. Add the suffix rather than assuming nobody
# writes it.
SLASH_COMMENT_SUFFIXES = frozenset({
    ".ts", ".tsx", ".mts", ".cts",
    ".js", ".jsx", ".mjs", ".cjs",
})

# Every prefix a line could already be commented with, in any language a
# fixer might touch. Used to decide "have we (or a human) already commented
# this out?" -- and it has to accept *both* families regardless of the file
# in hand, because a `#` in a TypeScript file is precisely the corruption
# being repaired here, and re-commenting it would just deepen the damage.
COMMENT_PREFIXES = ("#", "//")


def comment_prefix(path: Path) -> str:
    """The line-comment prefix to write into `path`, including its space.

    A fixer that hardcodes `# ` writes a Python comment into TypeScript,
    where `#` starts nothing at all -- the "fixed" file stops parsing, and
    the tool reports success on its way out. That is strictly worse than
    the finding it was repairing: every other failure mode in this project
    produces a wrong *report*, which a human reads and discards. This one
    edits their source and leaves it broken.

    So the prefix is derived from the file, once, here -- rather than
    remembered correctly by each of six fixers independently.
    """
    return "// " if path.suffix.lower() in SLASH_COMMENT_SUFFIXES else "# "


def is_commented(line: str) -> bool:
    """True if `line`'s first non-whitespace token opens a line comment."""
    return line.lstrip(" \t").startswith(COMMENT_PREFIXES)


@dataclass
class FixResult:
    """The result of running one `Fixer` over one file's source text."""

    text: str
    changes: list[str] = field(default_factory=list)
    changed: bool = False

    @classmethod
    def unchanged(cls, source: str) -> "FixResult":
        """Convenience for the common "nothing to do here" return."""
        return cls(text=source, changes=[], changed=False)


class Fixer:
    """Subclass this. Set the class attributes, implement fix()."""

    rule_id: str = ""          # which rule this repairs, e.g. "R001"
    title: str = ""            # one line, shows in `mcp-migrate fixers`
    confidence: str = "review"  # "safe" (apply with confidence) | "review" (flag for a human)

    def fix(self, source: str, path: Path) -> FixResult:  # pragma: no cover
        raise NotImplementedError

    # convenience for subclasses
    def unchanged(self, source: str) -> FixResult:
        return FixResult.unchanged(source)

    def result(self, text: str, changes: list[str]) -> FixResult:
        return FixResult(text=text, changes=changes, changed=bool(changes))
