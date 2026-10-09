import re

from .base import (
    Finding,
    Fires,
    Project,
    Rule,
    Silent,
    server_call_keywords,
    wire_method,
)

# `SubscribeRequest`/`UnsubscribeRequest` are the MCP SDK's own model names
# -- distinctive, no false-positive risk.
SUBSCRIBE_CODE_RX = re.compile(r"\bSubscribeRequest\b|\bUnsubscribeRequest\b")

# The SDK also registers these without the request class name:
#   @app.subscribe_resource()                         -- mcp 1.x Server
#   Server("demo", on_subscribe_resource=subscribe)   -- mcp 2.x constructor
# Distinctive enough that they do not need the generic-name gate `.tool(` does.
# search_code (not raw search) so a docstring naming them stays silent.
SDK_DECORATOR_RX = re.compile(
    r"@[\w.]*\.(?:subscribe_resource|unsubscribe_resource)\s*\("
)
# One-line fallback for files that do not parse. Multi-line and black-formatted
# Server(...) calls are handled by server_call_keywords (#314).
SDK_CONSTRUCTOR_KW_RX = (
    r"\b(?:Server|MCPServer)\s*\([^)]*\bon_(?:subscribe_resource|unsubscribe_resource)\s*="
)

# The TypeScript SDK exports Zod schemas for request handling, and that's
# the name a server actually references -- `server.setRequestHandler(
# SubscribeRequestSchema, ...)`. Bounded to the exact SDK export names
# (optionally suffixed `Params`/`Schema`) rather than an unbounded `\w*`
# suffix, which would also match unrelated identifiers like
# `SubscribeRequester` -- see #87.
TS_SUBSCRIBE_CODE_RX = re.compile(
    r"\b(?:Subscribe|Unsubscribe)Request(?:Params|Schema)?\b"
)

WIRE_RX = wire_method("resources/subscribe", "resources/unsubscribe")
MESSAGE_CODE = "References the removed SubscribeRequest/UnsubscribeRequest handler."
MESSAGE_SDK = (
    "Registers the removed subscribe_resource/unsubscribe_resource handler "
    "through the SDK."
)
MESSAGE_WIRE = (
    "References the removed resources/subscribe or resources/unsubscribe "
    "JSON-RPC method."
)


class ResourceSubscriptionsReplaced(Rule):
    id = "R013"
    title = "Uses resources/subscribe or resources/unsubscribe, replaced by subscriptions/listen"
    severity = "breaking"
    spec_ref = "SEP-2575 https://modelcontextprotocol.io/specification/2026-07-28/changelog"
    fix = (
        "resources/subscribe and resources/unsubscribe are gone. Move subscription "
        "management to the new subscriptions/listen call."
    )
    languages = ("python", "typescript", "javascript")
    boundaries = (
        Fires(
            snippet="request: SubscribeRequest",
            reason="The removed SDK request type is active Python code.",
        ),
        Fires(
            snippet="@app.subscribe_resource()\nasync def subscribe(uri): pass",
            reason="The Python SDK still registers the removed subscription handler.",
        ),
        Fires(
            snippet='METHODS = {"resources/unsubscribe": handle_unsubscribe}',
            reason="A Python dispatch table still exposes the removed wire method.",
        ),
        Silent(
            snippet="# SubscribeRequest and resources/subscribe were removed",
            reason="A comment that only describes the old API is not an implementation.",
        ),
        Silent(
            snippet="class SubscribeRequester: pass",
            reason="An unrelated identifier with a longer suffix is not an SDK request type.",
        ),
        Silent(
            snippet='METRIC = "resources/subscriber"',
            reason="A longer Python wire name is outside the method boundary.",
        ),
        Fires(
            snippet="const schema: SubscribeRequestSchema = {};",
            reason="The removed SDK request schema is active TypeScript code.",
            language="typescript",
        ),
        Fires(
            snippet='server.setRequestHandler("resources/subscribe", handler);',
            reason="A TypeScript handler still registers the removed wire method.",
            language="typescript",
        ),
        Silent(
            snippet="// SubscribeRequestSchema and resources/subscribe were removed",
            reason="A TypeScript comment is prose, not active MCP surface.",
            language="typescript",
        ),
        Silent(
            snippet="class SubscribeRequester {}",
            reason="A longer TypeScript identifier is not an SDK request type.",
            language="typescript",
        ),
        Silent(
            snippet='const method = "resources/subscriber";',
            reason="A longer TypeScript wire name is outside the method boundary.",
            language="typescript",
        ),
        Fires(
            snippet="const schema = SubscribeRequestSchema;",
            reason="JavaScript references the removed SDK request schema.",
            language="javascript",
        ),
        Fires(
            snippet='if (method === "resources/unsubscribe") unsubscribe();',
            reason="A JavaScript dispatcher still handles the removed wire method.",
            language="javascript",
        ),
        Silent(
            snippet="// SubscribeRequestSchema and resources/subscribe were removed",
            reason="A JavaScript comment is prose, not active MCP surface.",
            language="javascript",
        ),
        Silent(
            snippet="const SubscribeRequester = makeHelper();",
            reason="A longer JavaScript identifier is not an SDK request type.",
            language="javascript",
        ),
        Silent(
            snippet='const method = "resources/subscriber";',
            reason="A longer JavaScript wire name is outside the method boundary.",
            language="javascript",
        ),
    )

    def check(self, project: Project) -> list[Finding]:
        if project.language == "typescript":
            return self._check_ts(project)
        if project.language == "javascript":
            return self._check_js(project)
        return self._check_python(project)

    def _check_python(self, project: Project) -> list[Finding]:
        out: list[Finding] = []
        for f, line, text in project.search_code(SUBSCRIBE_CODE_RX.pattern):
            out.append(self.finding(MESSAGE_CODE, f, line, text))
        for f, line, text in project.search_code(SDK_DECORATOR_RX.pattern):
            out.append(self.finding(MESSAGE_SDK, f, line, text))
        for f, line, text in server_call_keywords(
            project,
            ("on_subscribe_resource", "on_unsubscribe_resource"),
            SDK_CONSTRUCTOR_KW_RX,
        ):
            out.append(self.finding(MESSAGE_SDK, f, line, text))
        # resources/subscribe and resources/unsubscribe are JSON-RPC method
        # strings, not valid bare identifiers -- they can only appear
        # inside a STRING token, so search_code would never find them (see
        # the notifications/initialized note in r009). Scan raw text.
        for f, line, text in project.search_wire(WIRE_RX):
            out.append(self.finding(MESSAGE_WIRE, f, line, text))
        return out

    def _check_ts(self, project: Project) -> list[Finding]:
        seen: set[tuple[str, int]] = set()
        out: list[Finding] = []
        for pattern, message, search in (
            (TS_SUBSCRIBE_CODE_RX.pattern, MESSAGE_CODE, project.search_code),
            (WIRE_RX, MESSAGE_WIRE, project.search_wire),
        ):
            for f, line, text in search(pattern):
                # A dispatcher line can carry both signals at once, e.g.
                # `case "resources/subscribe": return this.subscribe(SubscribeRequestSchema);`
                # -- that's one removed-method usage, not two.
                if (str(f.path), line) in seen:
                    continue
                seen.add((str(f.path), line))
                out.append(self.finding(message, f, line, text))
        return sorted(out, key=lambda x: (str(x.path or ""), x.line or 0))

    def _check_js(self, project: Project) -> list[Finding]:
        return self._check_ts(project)
