import re

from .base import Finding, Project, Rule, wire_method

# `InitializeRequest`, `InitializeResult` and `InitializedNotification` are
# the MCP SDK's own pydantic model names for the initialize handshake --
# they don't occur in ordinary, non-MCP code, so matching them directly
# carries essentially no false-positive risk (unlike a bare `initialize`,
# which is one of the most overloaded words in software: class
# initializers, database `.initialize()` calls, config keys, ...).
HANDSHAKE_CODE_RX = re.compile(
    r"\bInitializeRequest(?:Params|Schema)?\b|\bInitializeResult(?:Schema)?\b"
    r"|\bInitializedNotification(?:Schema)?\b"
)

# --- TypeScript -----------------------------------------------------------
#
# The same three SDK names, with one difference that matters: the TS SDK
# exports a Zod schema alongside the inferred type, and the schema is the
# name a server actually writes --
# `server.setRequestHandler(InitializeRequestSchema, ...)`.
# `\bInitializeRequest\b` cannot match inside `InitializeRequestSchema`
# (there is no word boundary before `Schema`), so a trailing-suffix match
# is required or this port would find nothing on the one shape it most
# needs to catch. Same treatment `r011_ping_removed.py` gives
# `PingRequest\w*`, for the same reason.
TS_HANDSHAKE_CODE_RX = (
    r"\bInitializeRequest(?:Params|Schema)?\b|\bInitializeResult(?:Schema)?\b"
    r"|\bInitializedNotification(?:Schema)?\b"
)

# The wire name is spelled the same in both languages, and needs
# `search_wire` in both for the same reason -- see the note in
# `_check_python`.
WIRE_RX = wire_method("notifications/initialized")

MESSAGE_CODE = (
    "References the removed initialize handshake (InitializeRequest/"
    "InitializeResult/InitializedNotification)."
)
MESSAGE_WIRE = "References the removed notifications/initialized handshake message."


class InitializeHandshakeStillImplemented(Rule):
    id = "R009"
    title = "Still implements the initialize / notifications/initialized handshake"
    severity = "breaking"
    spec_ref = "SEP-2575 https://modelcontextprotocol.io/specification/2026-07-28/changelog"
    fix = (
        "The initialize handshake is gone -- there is no more negotiation round trip "
        "before a server is usable. Delete your initialize/notifications/initialized "
        "handling and advertise protocol versions, capabilities and identity through "
        "server/discover instead."
    )
    languages = ("python", "typescript")

    def check(self, project: Project) -> list[Finding]:
        if project.language == "typescript":
            return self._check_ts(project)
        return self._check_python(project)

    def _check_python(self, project: Project) -> list[Finding]:
        out: list[Finding] = []
        # search_code: a comment or docstring mentioning InitializeRequest
        # isn't a real handler for it.
        for f, line, text in project.search_code(HANDSHAKE_CODE_RX.pattern):
            out.append(self.finding(MESSAGE_CODE, f, line, text))
        # `notifications/initialized` is only ever valid as a JSON-RPC
        # method-name string -- it can't appear as a bare code identifier --
        # so it always starts inside a STRING token and search_code would
        # silently never find it. Match the literal directly instead, the
        # same way r004_tool_ordering.py matches the literal `tools/list`.
        for f, line, text in project.search_wire(WIRE_RX):
            out.append(self.finding(MESSAGE_WIRE, f, line, text))
        return out

    def _check_ts(self, project: Project) -> list[Finding]:
        # Same two signals and the same two search modes, for the same
        # reasons: the SDK schema names are code, so a JSDoc block
        # explaining that the handshake was removed must not read as an
        # implementation of it; the wire name only ever exists inside a
        # string literal, which `search_code` discards wholesale.
        seen: set[tuple[str, int]] = set()
        out: list[Finding] = []
        for pattern, message, search in (
            (TS_HANDSHAKE_CODE_RX, MESSAGE_CODE, project.search_code),
            (WIRE_RX, MESSAGE_WIRE, project.search_wire),
        ):
            for f, line, text in search(pattern):
                # One dispatcher line can carry both signals --
                # `case "notifications/initialized": return this.onInitializedNotification()`
                # is a single handshake implementation, not two. Each
                # finding is a separate grade penalty, so charging one line
                # twice for one problem overstates it.
                if (str(f.path), line) in seen:
                    continue
                seen.add((str(f.path), line))
                out.append(self.finding(message, f, line, text))
        return sorted(out, key=lambda x: (str(x.path or ""), x.line or 0))
