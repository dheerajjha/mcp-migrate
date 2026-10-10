import re

from .base import Finding, Project, Rule, mcp_surface_paths

PY_RX = r"last_event_id|LAST_EVENT_ID"
PY_HEADER_RX = r"""["']last-event-id["']|["']Last-Event-ID["']"""

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
        seen: set[tuple[str, int]] = set()
        out: list[Finding] = []
        surface = mcp_surface_paths(project)
        # Header names live in strings, which search_code skips. Keep the
        # quotes so prose like "Last-Event-ID resumability was removed"
        # stays silent, and deduplicate lines that also name the identifier.
        for pattern, search, gated in (
            (PY_RX, project.search_code, False),
            (PY_HEADER_RX, project.search_wire, True),
        ):
            for f, line, text in search(pattern):
                # Ordinary browser EventSource streams use this header too.
                # Require independent MCP surface in the same file for the
                # header alone; existing identifier findings stay unchanged.
                if gated and f.path not in surface:
                    continue
                key = (str(f.path), line)
                if key in seen:
                    continue
                seen.add(key)
                out.append(self.finding(MESSAGE, f, line, text))
        return sorted(out, key=lambda x: (str(x.path or ""), x.line or 0))

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
