import re

from .base import Finding, Project, Rule

# `-32002` on its own is just a negative five-digit integer -- it could be
# a port, a hash fragment, an unrelated sentinel, anything. What makes it a
# real hit for *this* rule is the same line also talking about a resource
# lookup failing, which is the one thing the old -32002 convention meant.
# Requiring both on one line trades a few missed multi-line cases for a
# large cut in accidental matches on an otherwise-generic number.
RESOURCE_NOT_FOUND_RX = re.compile(
    r"(?=.*-32002\b)(?=.*(?:resource|not[_ ]?found|notfound))", re.IGNORECASE
)

# A *name* that already says "this is the old code". Someone who writes
# `LEGACY_RESOURCE_NOT_FOUND = -32002` has demonstrated they know what
# -32002 is and is keeping it deliberately -- for clients that still send
# it, or to dispatch on both. Reporting that is noise; rewriting it is
# worse, and R017's fixer is `safe`, so it did. See #217.
#
# Scoped to the assigned identifier, NOT the whole line. That distinction is
# load-bearing: `RESOURCE_NOT_FOUND = -32002  # legacy code, now -32602` is
# a comment *describing the bug* and must still fire, while
# `LEGACY_RESOURCE_NOT_FOUND: -32002` is a deliberate keep. Our own test
# fixture is the first shape; dealfluence/adeu is the second.
#
# The marker has no trailing word boundary: `\b` would not match
# `LEGACY_RESOURCE...`, because `_` is a word character.
ASSIGNED_NAME_RX = re.compile(r"([A-Za-z_][A-Za-z0-9_]*)\s*[:=]\s*-32002\b")
LEGACY_MARKER_RX = re.compile(
    r"(?<![A-Za-z])(?:legacy|deprecated|obsolete|old|pre[_-]?2026|v1)(?![A-Za-z])",
    re.IGNORECASE,
)


def _is_deliberate_legacy_constant(text: str) -> bool:
    """True when the identifier being assigned -32002 names itself legacy."""
    m = ASSIGNED_NAME_RX.search(text)
    return bool(m and LEGACY_MARKER_RX.search(m.group(1)))



class ResourceNotFoundCodeChanged(Rule):
    id = "R017"
    title = "Uses the old -32002 resource-not-found error code"
    severity = "breaking"
    spec_ref = "https://modelcontextprotocol.io/specification/2026-07-28/changelog"
    fix = (
        "The resource-not-found error code changed from -32002 to -32602 (Invalid "
        "params). Update whatever raises or checks for -32002 in this context."
    )
    languages = ("python", "typescript")

    def check(self, project: Project) -> list[Finding]:
        # No language branch needed: the qualifying context is plain text
        # (a numeric literal plus nearby English words), not a
        # language-specific identifier or wire name, so the same
        # search_wire pass is correct for both Python and TypeScript --
        # see r001/r006 for rules where the two languages genuinely need
        # different patterns, which this one doesn't.
        out: list[Finding] = []
        # Raw text, not search_code: the qualifying context is as likely
        # to be a trailing comment ("# resource not found") as it is to be
        # a string/identifier, and being lenient about *where* the context
        # comes from doesn't create a false positive on its own -- the
        # numeric literal still has to be there too.
        for f, line, text in project.search_wire(
            RESOURCE_NOT_FOUND_RX.pattern, flags=re.IGNORECASE
        ):
            if _is_deliberate_legacy_constant(text):
                continue
            out.append(self.finding(
                "-32002 for resource-not-found is the old code; 2026-07-28 uses -32602.",
                f, line, text,
            ))
        return out
