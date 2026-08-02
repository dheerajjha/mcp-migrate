import re

from .base import Finding, Project, Rule

# --- TypeScript -----------------------------------------------------------

# TypeScript servers commonly keep the header value in a camel-cased local
# before passing it to their replay store. The identifiers are specific enough
# to be code-only matches, while the wire name itself must be kept in a string
# literal and is therefore matched only in a header access.
TS_IDENT_RX = r"\blastEventId\b|\blast_event_id\b|\bLAST_EVENT_ID\b"
TS_HEADER_RX = (
    r"headers?\s*(?:\[|\.get\s*\(|\.set\s*\(|\.delete\s*\()\s*"
    r"[\"'`]last-event-id[\"'`]"
    r"|[\"'`]last-event-id[\"'`]\s*\]"
    r"|setHeader\s*\(\s*[\"'`]last-event-id[\"'`]"
)


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
    languages = ("python", "typescript")

    def check(self, project: Project) -> list[Finding]:
        if project.language == "typescript":
            return self._check_ts(project)
        return self._check_python(project)

    def _check_python(self, project: Project) -> list[Finding]:
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

    def _check_ts(self, project: Project) -> list[Finding]:
        # search_code catches executable identifier use while ignoring prose;
        # search_wire retains the quoted HTTP header while still ignoring
        # comments. Deduplicate the common `const lastEventId =
        # req.headers.get("Last-Event-ID")` form into one finding.
        seen: set[tuple[str, int]] = set()
        out: list[Finding] = []
        for pattern, search in (
            (TS_IDENT_RX, project.search_code),
            (TS_HEADER_RX, project.search_wire),
        ):
            for f, line, text in search(pattern, flags=re.IGNORECASE):
                if (str(f.path), line) in seen:
                    continue
                seen.add((str(f.path), line))
                out.append(self.finding(
                    "Implements SSE resumability (Last-Event-ID) -- removed from the transport.",
                    f, line, text,
                ))
        return sorted(out, key=lambda x: (str(x.path or ""), x.line or 0))
