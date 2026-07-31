import re

from .base import Finding, Project, Rule

# `PingRequest` is the MCP SDK's own model name -- distinctive, essentially
# never appears outside MCP code.
PING_CODE_RX = re.compile(r"\bPingRequest\b")

# A bare `"ping"` string is one of the most overloaded tokens in server
# code (health checks, keepalives, load-balancer probes have nothing to do
# with MCP) -- matching it on its own would be exactly the kind of
# false-positive risk this project is trying to avoid. Only count it when
# it's shaped like an actual JSON-RPC method dispatch: compared against a
# `method` variable, or used as a `case`/dict-key clause the way a
# dispatcher for `tools/call`, `resources/subscribe`, etc. would use it.
#
# Note on the third alternative: a match's *start* position is what
# `search_code` checks against string/comment spans, so a pattern that
# starts right on the opening quote of "ping" would always look like it
# starts inside a string and get silently dropped. Anchoring on a
# preceding `{`/`,` keeps the match's start on the code side of that
# quote, the same trick r002_connection_state.py relies on via AST instead
# of regex.
PING_DISPATCH_RX = re.compile(
    r"method\s*==\s*[\"']ping[\"']|case\s*[\"']ping[\"']|[{,]\s*[\"']ping[\"']\s*:"
)


class PingRemoved(Rule):
    id = "R011"
    title = "Implements the removed ping request/response"
    severity = "breaking"
    spec_ref = "SEP-2575 https://modelcontextprotocol.io/specification/2026-07-28/changelog"
    fix = (
        "ping is gone from the protocol -- liveness now rides on the transport itself. "
        "Remove the handler and rely on your HTTP stack's own keepalive/health checks."
    )

    def check(self, project: Project) -> list[Finding]:
        out: list[Finding] = []
        for f, line, text in project.search_code(PING_CODE_RX.pattern):
            out.append(self.finding(
                "References the removed PingRequest handler.", f, line, text,
            ))
        for f, line, text in project.search_code(PING_DISPATCH_RX.pattern):
            out.append(self.finding(
                "Dispatches the removed `ping` JSON-RPC method.", f, line, text,
            ))
        return out
