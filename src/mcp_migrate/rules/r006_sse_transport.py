from .base import Finding, Project, Rule


class DeprecatedSSETransport(Rule):
    id = "R006"
    title = "Uses the deprecated HTTP+SSE transport"
    severity = "deprecated"
    spec_ref = "HTTP+SSE deprecated in favour of Streamable HTTP"
    fix = "Move to Streamable HTTP. HTTP+SSE stays in the spec for 12+ months, then goes."

    def check(self, project: Project) -> list[Finding]:
        out: list[Finding] = []
        # search_code: a comment explaining that SSE is deprecated, or a
        # log/URL string that happens to contain "/sse", isn't a real use
        # of the transport.
        for f, line, text in project.search_code(r"sse_server|SseServerTransport|transport\s*=\s*[\"']sse[\"']|/sse\b"):
            out.append(self.finding("HTTP+SSE transport is deprecated.", f, line, text))
        return out
