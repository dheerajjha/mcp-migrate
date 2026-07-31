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
