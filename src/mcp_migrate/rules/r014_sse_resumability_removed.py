import re

from .base import Finding, Project, Rule

PY_RX = r"Last-Event-ID|last_event_id|LAST_EVENT_ID"

# TypeScript identifier convention is camelCase, unlike Python's snake_case/
# SCREAMING_SNAKE_CASE. `Last-Event-ID` itself (the header name) is not a
# valid identifier in either language -- it can only appear as a string
# literal -- so that half needs search_wire, kept separate from the
# identifier half the same way R001 splits header-string vs. identifier.
#
# Matched case-insensitively (see TS_CODE_FLAGS): real servers write every
# casing of the same identifier -- `lastEventId`, `lastEventID`,
# `LastEventId` -- and a const carrying the header name is usually
# `LAST_EVENT_ID`, so the optional underscores cover the SCREAMING_SNAKE
# form too. The `\b` anchors keep it bounded: `lastEventIdentifier` and
# `lastEventIds` are left alone, which is the conservative direction.
TS_CODE_RX = r"\blast_?event_?id\b"
TS_CODE_FLAGS = re.IGNORECASE
TS_HEADER_RX = r"""["'`]last-event-id["'`]|["'`]Last-Event-ID["'`]"""

MESSAGE = "Implements SSE resumability (Last-Event-ID) -- removed from the transport."


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
        # search_code: a comment noting "we don't support Last-Event-ID"
        # (like the comment_only_mentions fixture pattern for R001) isn't a
        # real implementation of it. `Last-Event-ID` itself is a real HTTP
        # header name, not a generic English phrase, so this is precise the
        # same way R001 matching `Mcp-Session-Id` directly is precise.
        return [
            self.finding(MESSAGE, f, line, text)
            for f, line, text in project.search_code(PY_RX)
        ]

    def _check_ts(self, project: Project) -> list[Finding]:
        seen: set[tuple[str, int]] = set()
        out: list[Finding] = []
        # The header half stays case-sensitive on purpose: it matches a
        # quoted string, and both spellings servers actually send are
        # already listed in TS_HEADER_RX.
        for pattern, search, flags in (
            (TS_CODE_RX, project.search_code, TS_CODE_FLAGS),
            (TS_HEADER_RX, project.search_wire, 0),
        ):
            for f, line, text in search(pattern, flags=flags):
                key = (str(f.path), line)
                if key in seen:
                    continue
                seen.add(key)
                out.append(self.finding(MESSAGE, f, line, text))
        return sorted(out, key=lambda x: (str(x.path or ""), x.line or 0))
