import re

from .base import Finding, Project, Rule

PY_RX = r"sse_server|SseServerTransport|transport\s*=\s*[\"']sse[\"']|/sse\b"

# TypeScript. The SDK class is `SSEServerTransport` (all-caps SSE, unlike
# the Python `SseServerTransport`), and the other giveaway is an Express
# route mounted at /sse -- which only ever appears as a string literal, so
# this needs search_wire rather than search_code.
TS_RX = (
    r"\bSSEServerTransport\b"
    r"|transport\s*:\s*[\"'`]sse[\"'`]"
    r"|\.(?:get|post|all)\s*\(\s*[\"'`]/sse[\"'`]"
    r"|[\"'`]/sse(?:/[^\"'`]*)?[\"'`]"
)


class DeprecatedSSETransport(Rule):
    id = "R006"
    title = "Uses the deprecated HTTP+SSE transport"
    severity = "deprecated"
    spec_ref = "HTTP+SSE deprecated in favour of Streamable HTTP"
    fix = "Move to Streamable HTTP. HTTP+SSE stays in the spec for 12+ months, then goes."
    languages = ("python", "typescript")

    MESSAGE = "HTTP+SSE transport is deprecated."

    def check(self, project: Project) -> list[Finding]:
        if project.language == "typescript":
            # search_wire: `app.get("/sse", ...)` is a route, and routes are
            # string literals. A comment saying "we dropped SSE" is not.
            return [
                self.finding(self.MESSAGE, f, line, text)
                for f, line, text in project.search_wire(TS_RX)
            ]
        # search_code: a comment explaining that SSE is deprecated, or a
        # log/URL string that happens to contain "/sse", isn't a real use
        # of the transport.
        return [
            self.finding(self.MESSAGE, f, line, text)
            for f, line, text in project.search_code(PY_RX)
        ]
