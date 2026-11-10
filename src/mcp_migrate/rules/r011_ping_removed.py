import re

from .base import Finding, Fires, Project, Rule, Silent, mcp_surface_paths, server_call_keywords

# `PingRequest` is the MCP SDK's own model name -- distinctive, essentially
# never appears outside MCP code. In TypeScript the SDK exports
# `PingRequestSchema` (Zod) and `PingRequest` (inferred type), so we match
# specific TypeScript/Python SDK type & schema names.
PING_CODE_RX = re.compile(r"\bPingRequest(?:Params|Schema|Result|ResultSchema)?\b")

# A bare `"ping"` string is one of the most overloaded tokens in server
# code (health checks, keepalives, load-balancer probes have nothing to do
# with MCP) -- matching it on its own would be exactly the kind of
# false-positive risk this project is trying to avoid. Only count it when
# it's shaped like an actual JSON-RPC method dispatch: compared against a
# `method` variable, or used as a `case`/dict-key clause the way a
# dispatcher for `tools/call`, `resources/subscribe`, etc. would use it.
#
# Being *shaped* like a dispatch is not enough, though: the shape is the
# ordinary Python spelling of any dispatcher, and R011 is `breaking`. The
# Python gates the signal on the file independently showing MCP surface
# (#89). TypeScript additionally requires a sibling MCP method at the
# dispatch site.
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

# mcp 2.x registers the removed ping handler as a Server() constructor
# argument, which contains neither PingRequest nor a "ping" dispatch string:
#   Server("demo", on_ping=ping)
# Distinctive enough that it does not need the generic-name gate `.tool(` does.
# One-line fallback for files that do not parse. Multi-line and black-formatted
# Server(...) calls are handled by server_call_keywords (#314).
SDK_CONSTRUCTOR_KW_RX = r"\b(?:Server|MCPServer)\s*\([^)]*\bon_ping\s*="

# --- TypeScript -----------------------------------------------------------
#
# Same distinctive identifier signal, adapted for TS syntax.
TS_PING_CODE_RX = r"\bPingRequest(?:Params|Schema|Result|ResultSchema)?\b"

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
MESSAGE_SDK = "Registers the removed ping handler through the SDK."

MCP_METHODS = {
    "initialize", "tools/list", "tools/call", "resources/list", "resources/read",
    "resources/templates/list", "resources/subscribe", "resources/unsubscribe",
    "prompts/list", "prompts/get", "completion/complete", "logging/setLevel",
    "sampling/createMessage", "elicitation/create", "roots/list",
}


def _ts_dispatches(source, jsx):
    from ._r003_typescript import Syntax, children, literal, text

    root = Syntax(source, jsx).root
    if root.has_error:
        return

    def comparison(node):
        condition = node.child_by_field_name("condition")
        parts = children(condition)
        if len(parts) != 1 or parts[0].type != "binary_expression":
            return None
        expr = parts[0]
        operator = expr.child_by_field_name("operator")
        left = expr.child_by_field_name("left")
        right = expr.child_by_field_name("right")
        if text(operator) not in {"==", "==="}:
            return None
        if literal(left) is not None:
            left, right = right, left
        value = literal(right)
        if left.type == "identifier":
            name = text(left)
        elif left.type == "member_expression":
            obj = left.child_by_field_name("object")
            prop = left.child_by_field_name("property")
            if obj.type != "identifier" or prop.type != "property_identifier":
                return None
            name = text(obj) + "." + text(prop)
            if text(left) != name:
                return None
        else:
            return None
        if name.split(".")[-1] != "method":
            return None
        return (name, value) if value is not None else None

    def walk(node):
        if node.type == "switch_statement":
            body = node.child_by_field_name("body")
            cases = [c for c in children(body) if c.type == "switch_case"]
            values = [literal(c.child_by_field_name("value")) for c in cases]
            if MCP_METHODS.intersection(values):
                yield from (c for c, value in zip(cases, values) if value == "ping")
        elif node.type == "object":
            pairs = [c for c in children(node) if c.type == "pair"]
            values = [literal(c.child_by_field_name("key")) for c in pairs]
            if MCP_METHODS.intersection(values):
                yield from (c for c, value in zip(pairs, values) if value == "ping")
        elif node.type == "if_statement" and node.parent.type != "else_clause":
            comparisons = []
            current = node
            while current is not None and current.type == "if_statement":
                item = comparison(current)
                if item:
                    comparisons.append((current, *item))
                alternative = current.child_by_field_name("alternative")
                alternatives = children(alternative)
                current = alternatives[0] if len(alternatives) == 1 else None
            for branch, name, value in comparisons:
                if value == "ping" and any(
                    other_name == name and other_value in MCP_METHODS
                    for _, other_name, other_value in comparisons
                ):
                    yield branch
        for child in children(node):
            yield from walk(child)

    yield from walk(root)


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
    boundaries = (
        Fires(
            snippet="async def handle_ping(request: PingRequest): ...",
            reason="The SDK's own request type is distinctive without another surface gate.",
        ),
        Fires(
            snippet=(
                "async def dispatch(method):\n"
                "    if method == 'ping':\n"
                "        return {}\n"
                "\n"
                "REQUEST = 'tools/call'\n"
            ),
            reason="A hand-written dispatcher in a file that also speaks MCP's wire protocol.",
        ),
        Fires(
            snippet="server = Server('demo', on_ping=ping)",
            reason="The 2.x SDK takes the removed handler as a constructor keyword.",
        ),
        Silent(
            snippet=(
                "def handle(method, payload):\n"
                "    if method == 'ping':\n"
                "        return 'pong'\n"
                "    return 'unknown'\n"
                "\n"
                "\n"
                "ROUTES = {'ping': handle, 'stats': handle}\n"
            ),
            reason="An ordinary dispatcher with no MCP surface anywhere in the file.",
        ),
        Silent(
            snippet="helper = PingRequester()",
            reason="A different identifier that merely ends in the SDK's name.",
        ),
        Silent(
            snippet="// PingRequestSchema is gone, liveness rides on the transport now\nexport const NOTE = 1\n",
            reason="A comment naming the old API is migration prose, not a dependency.",
            language="typescript",
        ),
    )

    def check(self, project: Project) -> list[Finding]:
        if project.language == "typescript":
            return self._check_ts(project)
        return self._check_python(project)

    def _check_python(self, project: Project) -> list[Finding]:
        out: list[Finding] = []
        for f, line, text in project.search_code(PING_CODE_RX.pattern):
            out.append(self.finding(MESSAGE_CODE, f, line, text))
        # The dispatch signal is gated the same way the TypeScript half gates
        # it (`mcp_paths` below), via the shared `mcp_surface_paths` helper --
        # `ping` is an ordinary word in dispatcher code, so a file that
        # speaks MCP on no other evidence is not dispatching MCP's ping.
        surface = mcp_surface_paths(project)
        for f, line, text in project.search_code(PING_DISPATCH_RX.pattern):
            if f.path not in surface:
                continue
            out.append(self.finding(MESSAGE_DISPATCH, f, line, text))
        for f, line, text in server_call_keywords(
            project,
            ("on_ping",),
            SDK_CONSTRUCTOR_KW_RX,
        ):
            out.append(self.finding(MESSAGE_SDK, f, line, text))
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

        # A file-level gate alone cannot distinguish a health check from an
        # MCP dispatcher; require another MCP method in the same construct.
        mcp_paths = {f.path for f in project.files if TS_MCP_SURFACE_RX.search(f.text)}
        for f in project.files:
            if f.path not in mcp_paths:
                continue
            lines = f.text.splitlines()
            for node in _ts_dispatches(f.text, f.path.suffix in {".tsx", ".jsx"}):
                line = node.start_point.row + 1
                key = (str(f.path), line)
                if key in seen:
                    continue
                seen.add(key)
                out.append(self.finding(MESSAGE_DISPATCH, f, line, lines[line - 1].strip()))

        return sorted(out, key=lambda x: (str(x.path or ""), x.line or 0))
