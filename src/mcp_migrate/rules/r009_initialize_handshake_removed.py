import re

from .base import Finding, Project, Rule, wire_method

# `InitializeRequest`, `InitializeResult` and `InitializedNotification` are
# the MCP SDK's own pydantic model names for the initialize handshake --
# they don't occur in ordinary, non-MCP code, so matching them directly
# carries essentially no false-positive risk (unlike a bare `initialize`,
# which is one of the most overloaded words in software: class
# initializers, database `.initialize()` calls, config keys, ...).
HANDSHAKE_CODE_RX = re.compile(
    r"\bInitializeRequest(?:Params|Schema)?\b|\bInitializeResult(?:Schema)?\b|\bInitializedNotification(?:Schema)?\b"
)


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

    def check(self, project: Project) -> list[Finding]:
        out: list[Finding] = []
        # search_code: a comment or docstring mentioning InitializeRequest
        # isn't a real handler for it.
        for f, line, text in project.search_code(HANDSHAKE_CODE_RX.pattern):
            out.append(self.finding(
                "References the removed initialize handshake (InitializeRequest/"
                "InitializeResult/InitializedNotification).",
                f, line, text,
            ))
        # `notifications/initialized` is only ever valid as a JSON-RPC
        # method-name string -- it can't appear as a bare code identifier --
        # so it always starts inside a STRING token and search_code would
        # silently never find it. Match the literal directly instead, the
        # same way r004_tool_ordering.py matches the literal `tools/list`.
        for f, line, text in project.search_wire(wire_method("notifications/initialized")):
            out.append(self.finding(
                "References the removed notifications/initialized handshake message.",
                f, line, text,
            ))
        return out
