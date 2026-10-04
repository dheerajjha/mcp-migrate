import re

from .base import Finding, Project, Rule, mcp_surface_paths

PY_RX = r"sse_server|SseServerTransport|transport\s*=\s*[\"']sse[\"']"

# TypeScript and JavaScript share these patterns. SSEServerTransport and
# transport: "sse" are distinctive enough to stand alone. An Express /sse
# route is ambiguous, so it is gated on MCP surface in check().
TS_STRONG_RX = (
    r"\bSSEServerTransport\b"
    r"|transport\s*:\s*[\"'`]sse[\"'`]"
)

TS_ROUTE_RX = r"\.(?:get|post|all)\s*\(\s*[\"'`]/sse[\"'`]"


class DeprecatedSSETransport(Rule):
    id = "R006"
    title = "Uses the deprecated HTTP+SSE transport"
    severity = "deprecated"
    spec_ref = "HTTP+SSE deprecated in favour of Streamable HTTP"
    fix = "Move to Streamable HTTP. HTTP+SSE stays in the spec for 12+ months, then goes."
    languages = ("python", "typescript", "javascript")

    MESSAGE = "HTTP+SSE transport is deprecated."

    def check(self, project: Project) -> list[Finding]:
        if project.language in ("typescript", "javascript"):
            out: list[Finding] = []
            seen = set()

            # search_wire, not search_code: `app.get("/sse", ...)` is a route, and
            # routes are string literals that search_code would skip. A comment
            # saying "we dropped SSE" is not a route either way.
            # Distinctive SDK/configuration signals do not need an MCP-surface gate.
            for f, line, text in project.search_wire(TS_STRONG_RX):
                seen.add((f.path, line))
                out.append(self.finding(self.MESSAGE, f, line, text))

            # An ordinary application can expose its own /sse route, so only treat
            # the route as MCP transport evidence when the same file speaks MCP.
            surface = mcp_surface_paths(project)
            for f, line, text in project.search_wire(TS_ROUTE_RX):
                if f.path not in surface:
                    continue
                if (f.path, line) in seen:
                    continue
                seen.add((f.path, line))
                out.append(self.finding(self.MESSAGE, f, line, text))

            return out
        # search_code skips comments and string literals, so a bare "/sse"
        # path cannot be Python transport evidence here.
        return [
            self.finding(self.MESSAGE, f, line, text)
            for f, line, text in project.search_code(PY_RX)
        ]
