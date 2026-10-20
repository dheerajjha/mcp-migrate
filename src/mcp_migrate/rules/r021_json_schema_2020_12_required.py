import re

from .base import Finding, Fires, Project, Rule, Silent

# Deliberately positive-evidence, not absence-based: the overwhelming
# majority of MCP servers (FastMCP included) generate inputSchema/
# outputSchema automatically and never reference a $schema dialect at all,
# so "the string 2020-12 doesn't appear anywhere" would fire on almost
# every real project and say nothing useful -- exactly the kind of
# systemic false positive this project exists to avoid. An explicit
# reference to an *older* draft, on the other hand, is real, rare, and
# actionable evidence that this project pins a dialect the new spec no
# longer guarantees support for.
OLD_DIALECT_RX = re.compile(
    r"json-schema\.org/draft-(?:0[1-7])/schema|\bdraft-0[1-7]\b|\b2019-09\b(?!-\d)"
)


class OldJSONSchemaDialect(Rule):
    id = "R021"
    title = "Pins an older JSON Schema dialect than 2020-12"
    severity = "advisory"
    spec_ref = "SEP-2106 https://modelcontextprotocol.io/specification/2026-07-28/changelog"
    fix = (
        "Implementations MUST support at least JSON Schema 2020-12 for inputSchema/"
        "outputSchema. If you pin an older draft explicitly, move it to 2020-12 (or "
        "drop the pin and let a modern validator pick the default)."
    )
    languages = ("python", "typescript", "javascript")
    boundaries = (
        Fires(
            snippet=(
                'input_schema = {\n'
                '    "$schema": "http://json-schema.org/draft-07/schema#",\n'
                '}\n'
            ),
            reason="An explicit draft-07 pin is older than the required 2020-12 dialect.",
        ),
        Silent(
            snippet=(
                'input_schema = {\n'
                '    "$schema": "https://json-schema.org/draft/2020-12/schema",\n'
                '}\n'
            ),
            reason="The required JSON Schema 2020-12 dialect is current.",
        ),
        Silent(
            snippet=(
                'input_schema = {\n'
                '    "type": "object",\n'
                '    "properties": {"query": {"type": "string"}},\n'
                '}\n'
            ),
            reason="Most servers never pin a dialect, and leaving it out is not a finding.",
        ),
        Silent(
            snippet=(
                '# We pinned draft-07 here before moving to 2020-12.\n'
                'input_schema = {"type": "object"}\n'
            ),
            reason="A comment about an old draft is not a pin.",
        ),
        Silent(
            snippet='START_DATE = "2019-09-01"\n',
            reason="A September 2019 date is not the 2019-09 dialect (#343).",
        ),
        Fires(
            snippet=(
                "const schema = {\n"
                '  $schema: "https://json-schema.org/draft/2019-09/schema",\n'
                "};\n"
            ),
            reason="An explicit 2019-09 pin is older than the required 2020-12 dialect.",
            language="typescript",
        ),
        Silent(
            snippet=(
                "const schema = {\n"
                '  $schema: "https://json-schema.org/draft/2020-12/schema",\n'
                "};\n"
            ),
            reason="The required JSON Schema 2020-12 dialect is current.",
            language="typescript",
        ),
        Silent(
            snippet=(
                '// We pinned draft-07 here before moving to 2020-12.\n'
                'const schema = { type: "object" };\n'
            ),
            reason="A comment about an old draft is not a pin.",
            language="typescript",
        ),
        Fires(
            snippet=(
                "const schema = {\n"
                '  $schema: "http://json-schema.org/draft-07/schema#",\n'
                "};\n"
            ),
            reason="An explicit draft-07 pin is older than the required 2020-12 dialect.",
            language="javascript",
        ),
        Silent(
            snippet=(
                "const schema = {\n"
                '  $schema: "https://json-schema.org/draft/2020-12/schema",\n'
                "};\n"
            ),
            reason="The required JSON Schema 2020-12 dialect is current.",
            language="javascript",
        ),
    )

    def check(self, project: Project) -> list[Finding]:
        # No language branch needed: a `$schema` dialect pin is always a
        # URL/date string, not a language-specific identifier or wire
        # name, so the same search_wire pass is correct for Python,
        # TypeScript, and JavaScript alike -- same shape as R017's port.
        out: list[Finding] = []
        # Raw text, not search_code: a `$schema` dialect pin is always a
        # URL/date string (`"http://json-schema.org/draft-07/schema#"`,
        # `"2019-09"`), never a bare code identifier, so it only ever
        # starts inside a STRING token -- search_code would silently never
        # find it (see the notifications/initialized note in r009).
        for f, line, text in project.search_wire(OLD_DIALECT_RX.pattern):
            out.append(self.finding(
                "Pins an older JSON Schema dialect; 2026-07-28 requires 2020-12 support.",
                f, line, text,
            ))
        return out
