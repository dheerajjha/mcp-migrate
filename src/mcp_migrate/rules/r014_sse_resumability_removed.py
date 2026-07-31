from .base import Finding, Project, Rule


class SSEResumabilityRemoved(Rule):
    id = "R014"
    title = "Implements SSE resumability (Last-Event-ID / event redelivery)"
    severity = "breaking"
    spec_ref = "SEP-2575 https://modelcontextprotocol.io/specification/2026-07-28/changelog"
    fix = (
        "Stream resumability via Last-Event-ID and replayed events is gone. Drop your "
        "event store / replay logic -- a dropped connection is just a dropped connection "
        "now, the client issues a fresh request."
    )

    def check(self, project: Project) -> list[Finding]:
        out: list[Finding] = []
        # search_code: a comment noting "we don't support Last-Event-ID"
        # (like the comment_only_mentions fixture pattern for R001) isn't a
        # real implementation of it. `Last-Event-ID` itself is a real HTTP
        # header name, not a generic English phrase, so this is precise the
        # same way R001 matching `Mcp-Session-Id` directly is precise.
        for f, line, text in project.search_code(
            r"Last-Event-ID|last_event_id|LAST_EVENT_ID"
        ):
            out.append(self.finding(
                "Implements SSE resumability (Last-Event-ID) -- removed from the transport.",
                f, line, text,
            ))
        return out
