import re

from .base import Finding, Project, Rule

# `PingRequest` is the MCP SDK's own model name -- distinctive, essentially
# never appears outside MCP code. In TypeScript the SDK exports
# `PingRequestSchema` (Zod) and `PingRequest` (inferred type), so we match
# any identifier starting with PingRequest.
PING_CODE_RX = re.compile(r"\bPingRequest\w*")

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

# --- TypeScript -----------------------------------------------------------
#
# Same two signals, adapted for TS syntax. `===` is the idiomatic equality
# operator in TypeScript, and template literals (backticks) are valid
# string delimiters. The dispatch-object alternative keeps the same
# `{`/`,` anchor trick so search_code doesn't drop the match.
TS_PING_CODE_RX = r"\bPingRequest\w*"
TS_PING_DISPATCH_RX = (
    r"method\s*===?\s*[\"'`]ping[\"'`]"
    r"|case\s+[\"'`]ping[\"'`]\s*:"
    r"|[{,]\s*[\"'`]ping[\"'`]\s*:"
)

# `ping` appears in health-check endpoints constantly. Gate signal 2 on
# the file having some MCP context: an SDK import or a reference to MCP's
# own JSON-RPC method names. A file that never touches MCP is not
# dispatching the MCP ping, no matter what string it compares against.
TS_MCP_SURFACE_RX = re.compile(
    r"@modelcontextprotocol|tools/call|tools/list|resources/read|prompts/get|jsonrpc",
    re.IGNORECASE,
)

MESSAGE_CODE = "References the removed PingRequest handler."
MESSAGE_DISPATCH = "Dispatches the removed `ping` JSON-RPC method."


class PingRemoved(Rule):
    id = "R011"
    title = "Implements the removed ping request/response"
    severity = "breaking"
    spec_ref = "SEP-2575 https://modelcontextprotocol.io/specification/2026-07-28/changelog"
    fix = (
        "ping is gone from the protocol -- liveness now rides on the transport itself. "
        "Remove the handler and rely on your HTTP stack's own keepalive/health checks."
    )
    languages = ("python", "typescript")

    def check(self, project: Project) -> list[Finding]:
        if project.language == "typescript":
            return self._check_ts(project)
        return self._check_python(project)

    def _check_python(self, project: Project) -> list[Finding]:
        out: list[Finding] = []
        for f, line, text in project.search_code(PING_CODE_RX.pattern):
            out.append(self.finding(MESSAGE_CODE, f, line, text))
        for f, line, text in project.search_code(PING_DISPATCH_RX.pattern):
            out.append(self.finding(MESSAGE_DISPATCH, f, line, text))
        return out

    def _check_ts(self, project: Project) -> list[Finding]:
        out: list[Finding] = []
        seen: set[tuple[str, int]] = set()

        # Signal 1: PingRequest identifier. Distinctive enough that no MCP
        # context gate is needed -- search_code skips comments and string
        # literals, so a JSDoc mention is not a reference.
        for f, line, text in project.search_code(TS_PING_CODE_RX):
            key = (str(f.path), line)
            if key in seen:
                continue
            seen.add(key)
            out.append(self.finding(MESSAGE_CODE, f, line, text))

        # Signal 2: "ping" as a JSON-RPC method dispatch. Gated on MCP
        # context because `ping` is one of the most common tokens in
        # non-MCP server code (health checks, keepalives). The dispatch
        # patterns start on code tokens (method, case, {, ,) so
        # search_code finds them despite the "ping" part being a string
        # literal.
        mcp_paths = {f.path for f in project.files if TS_MCP_SURFACE_RX.search(f.text)}
        for f, line, text in project.search_code(TS_PING_DISPATCH_RX):
            if f.path not in mcp_paths:
                continue
            key = (str(f.path), line)
            if key in seen:
                continue
            seen.add(key)
            out.append(self.finding(MESSAGE_DISPATCH, f, line, text))

        return sorted(out, key=lambda x: (str(x.path or ""), x.line or 0))
