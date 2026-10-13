import re

from .base import Finding, Fires, Project, Rule, Silent, mcp_surface_paths

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
    boundaries = (
        Fires(
            snippet='last_event_id = request.headers.get("Last-Event-ID")',
            reason="A variable named for the resume cursor is active Python code.",
        ),
        Fires(
            snippet='LAST_EVENT_ID = "Last-Event-ID"',
            reason="A Python constant carries the removed header name.",
        ),
        Fires(
            snippet=(
                'from mcp.server import Server\n\n'
                'cursor = request.headers.get("Last-Event-ID")'
            ),
            reason="A header read into any name fires once the file shows MCP surface.",
        ),
        Fires(
            snippet="return replay_events(last_event_id)",
            reason="Python code still uses the removed resume cursor.",
        ),
        Silent(
            snippet="# Last-Event-ID resumability was removed",
            reason="A comment documenting the removal is not an implementation.",
        ),
        Silent(
            snippet=(
                'from mcp.server import Server\n\n'
                'NOTICE = "Last-Event-ID resumability was removed"'
            ),
            reason="A user-facing notice about the removal is prose, not active code.",
        ),
        Silent(
            snippet='cursor = request.headers.get("last-event-id") or ""',
            reason=(
                "The same read with no MCP surface in its file is an ordinary EventSource "
                "stream: without this gate, invisible-playwright-mcp's /chat/events route "
                "goes from A/97 to C/72."
            ),
        ),
        Fires(
            snippet='const lastEventId = req.headers.get("last-event-id");',
            reason="TypeScript code reads the removed SSE resume cursor.",
            language="typescript",
        ),
        Fires(
            snippet=(
                'import { Server } from "@modelcontextprotocol/sdk/server/index.js";\n'
                'const cursor = req.headers["last-event-id"];'
            ),
            reason="A header read into any name fires once the file shows MCP surface.",
            language="typescript",
        ),
        Fires(
            snippet="return replayEventsAfter(lastEventID);",
            reason="TypeScript code still uses the removed resume cursor.",
            language="typescript",
        ),
        Silent(
            snippet="// We dropped lastEventId / Last-Event-ID resumability support.",
            reason="A TypeScript comment documenting the removal is not code.",
            language="typescript",
        ),
        Silent(
            snippet="const lastEventIdentifier = new Map();",
            reason="A longer identifier is outside the bounded cursor name.",
            language="typescript",
        ),
        Silent(
            snippet=(
                'import { Server } from "@modelcontextprotocol/sdk/server/index.js";\n'
                'const notice = "Last-Event-ID resumability was removed";'
            ),
            reason="A sentence that mentions the header is not the quoted header name.",
            language="typescript",
        ),
        Silent(
            snippet='const cursor = req.headers["last-event-id"] ?? "";',
            reason="The same read with no MCP surface in its file is an ordinary EventSource stream.",
            language="typescript",
        ),
    )

    def check(self, project: Project) -> list[Finding]:
        if project.language == "typescript":
            return self._check_ts(project)
        return self._check_python(project)

    def _check_python(self, project: Project) -> list[Finding]:
        seen: set[tuple[str, int]] = set()
        out: list[Finding] = []
        surface = mcp_surface_paths(project)
        # search_code keeps comment-only mentions of last_event_id from
        # being mistaken for an implementation of resumability.
        # Header names live in strings, which search_code skips. Keep the
        # quotes so prose like "Last-Event-ID resumability was removed"
        # stays silent, and deduplicate lines that also name the identifier.
        for pattern, search, gated in (
            (PY_RX, project.search_code, False),
            (PY_HEADER_RX, project.search_wire, True),
        ):
            for f, line, text in search(pattern):
                # Ordinary browser EventSource streams use this header too.
                # Without this gate, invisible-playwright-mcp's /chat/events
                # route took its pinned board grade from A/97 to C/72.
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
        surface = mcp_surface_paths(project)
        # The header half stays case-sensitive on purpose: it matches a
        # quoted string, and both spellings servers actually send are
        # already listed in TS_HEADER_RX.
        for pattern, search, flags, gated in (
            (TS_CODE_RX, project.search_code, TS_CODE_FLAGS, False),
            (TS_HEADER_RX, project.search_wire, 0, True),
        ):
            for f, line, text in search(pattern, flags=flags):
                # As on Python, an ordinary /chat/events route can read this
                # header beside an MCP server in another file (PR #335).
                # Only header matches need same-file MCP context; preserve
                # existing identifier detection even without that context.
                if gated and f.path not in surface:
                    continue
                key = (str(f.path), line)
                if key in seen:
                    continue
                seen.add(key)
                out.append(self.finding(MESSAGE, f, line, text))
        return sorted(out, key=lambda x: (str(x.path or ""), x.line or 0))
