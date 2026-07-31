import re

from .base import Finding, Project, Rule

# Evidence a file implements a result-returning MCP handler at all -- if a
# file doesn't do this, it has nothing to add `resultType` to, and firing
# here would just be noise unrelated to what the rule checks.
RESULT_HANDLER_RX = re.compile(
    r"@[\w.]*\.(?:call_tool|list_tools|list_resources|read_resource|"
    r"list_prompts|get_prompt)\s*\("
)

# Presence check for the required field. Deliberately raw text, not
# search_code: this is the same permissive direction r005_extensions.py
# uses for its own "is `extensions` declared anywhere in this file" check
# -- a mention anywhere (even a comment noting the transport layer adds it)
# is enough to consider the field present, because the cost of a wrong
# "still missing" claim (breaking) is much higher than the cost of a
# generous read of "present".
RESULT_TYPE_MENTION_RX = re.compile(r"resultType")


# Downgraded from "breaking" after auditing real servers: resultType is a
# brand-new required field introduced by this same spec revision, so this
# is an absence check that every pre-2026-07-28 handler fails by
# construction -- of the 14 real servers scanned, all 5 whose handlers this
# rule could even detect (the low-level SDK decorator style) tripped it,
# 5 for 5. That's not this rule finding a bug some projects have and
# others don't; it's the rule detecting "was this file written before the
# field existed", which is true of virtually all real MCP code today.
# Stacked at `breaking` alongside R010/R016 (the same shape of absence
# check) this took every reference server straight to F on the day the
# spec shipped, which tells a reader nothing about which of those projects
# is actually further along. Keep surfacing it, just not at a severity
# that drowns out real signal.
class RequiredResultTypeMissing(Rule):
    id = "R015"
    title = "Results are returned without the required resultType field"
    severity = "advisory"
    spec_ref = "SEP-2322 https://modelcontextprotocol.io/specification/2026-07-28/changelog"
    fix = (
        "Every result now carries resultType: \"complete\" or \"input_required\". "
        "Add it to whatever you return from tools/call, tools/list, resources/read, "
        "list handlers, and everywhere else a Result crosses the wire."
    )

    def check(self, project: Project) -> list[Finding]:
        out: list[Finding] = []
        seen_files = set()
        for f, line, text in project.search_code(RESULT_HANDLER_RX.pattern):
            if f.path in seen_files:
                continue
            if RESULT_TYPE_MENTION_RX.search(f.text):
                continue
            seen_files.add(f.path)
            out.append(self.finding(
                "This file implements a result-returning MCP handler but `resultType` "
                "never appears in it.",
                f, line, text,
            ))
        return out
