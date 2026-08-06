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
            out.append(self.finding(
                "-32002 for resource-not-found is the old code; 2026-07-28 uses -32602.",
                f, line, text,
            ))
        return out
