import re

from .base import Finding, Project, Rule

# Every pattern here has to be unambiguously MCP. A bare `create_message`
# was not: it has no word boundary and no MCP context, so it matched
# `_create_message` in any wrapper around the Anthropic Messages API --
# which is a very large share of the Python AI ecosystem, and none of it
# has anything to do with MCP Sampling. Found by scanning the registry:
# browser-use took three `deprecated` findings for its Anthropic client.
#
# Real MCP sampling always goes through the session object --
# `ctx.session.create_message(...)` in the SDK examples,
# `server.request_context.session.create_message(...)` in the low-level
# API -- so the `session.` qualifier keeps every true positive while
# dropping the collision.
FEATURES = {
    r"\broots/list\b|list_roots|RootsCapability": ("Roots", "Use resource URIs instead."),
    r"sampling/createMessage|SamplingCapability|\bsession\.create_message\b"
    r"|\bCreateMessageRequest\b|\bCreateMessageResult\b": (
        "Sampling", "Sampling is deprecated; plan a migration."),
    r"notifications/message|LoggingCapability|set_logging_level": ("Logging", "Logging moves out of core; use an extension."),
}

# --- TypeScript -----------------------------------------------------------
#
# Three signals per feature, because the three kinds of evidence need three
# different search modes and three different levels of caution:
#
#   * SDK type/schema names (`ListRootsRequestSchema`, `SamplingCapability`)
#     -- code, and distinctive enough to stand alone. `\w*` suffix because
#     the TS SDK exports both the Zod schema and the inferred type
#     (`CreateMessageRequest` / `CreateMessageRequestSchema`), and
#     `\bCreateMessageRequest\b` cannot match inside the longer name.
#   * the SDK method calls (`.listRoots(`, `.createMessage(`,
#     `.sendLoggingMessage(`) -- code, but gated on MCP context, see
#     TS_OWNER/TS_MCP_SURFACE_RX below.
#   * the JSON-RPC method names (`roots/list`, `sampling/createMessage`,
#     `notifications/message`) -- string literals, so they need
#     `search_wire`; `search_code` discards every string token and would
#     never find them.
#
# The `owner.` qualifier is the TypeScript spelling of the Python rule's
# `session.` anchor, and exists for exactly the same reason: an unanchored
# `createMessage` collides with the wrappers people write around chat APIs.
# TS servers reach sampling through the protocol object rather than a
# request context -- `server.createMessage(...)` on the low-level `Server`,
# `mcpServer.server.createMessage(...)` on `McpServer` -- so the owner is a
# server/client/session-shaped name, matched with a `\w*` prefix so
# `mcpServer.` and `this.client.` qualify too.
TS_OWNER = r"\b\w*(?:[Ss]erver|[Cc]lient|[Ss]ession)\."

# Is this file MCP at all? Same gate r011_ping_removed.py uses, and for the
# same reason: `createMessage` on some `chatClient` in a file that never
# touches MCP is not MCP Sampling, and a wrong `deprecated` verdict costs a
# maintainer's trust while a missed one costs a little visibility.
TS_MCP_SURFACE_RX = re.compile(
    r"@modelcontextprotocol|tools/call|tools/list|resources/read|prompts/get|jsonrpc",
    re.IGNORECASE,
)

# (feature, advice, SDK names, gated method call, JSON-RPC method name)
TS_FEATURES = (
    (
        "Roots", "Use resource URIs instead.",
        r"\bListRootsRequest\w*|\bListRootsResult\w*|\bRootsCapability\b",
        TS_OWNER + r"listRoots\s*\(",
        r"roots/list",
    ),
    (
        "Sampling", "Sampling is deprecated; plan a migration.",
        r"\bCreateMessageRequest\w*|\bCreateMessageResult\w*|\bSamplingCapability\b",
        TS_OWNER + r"createMessage\s*\(",
        r"sampling/createMessage",
    ),
    (
        "Logging", "Logging moves out of core; use an extension.",
        r"\bLoggingCapability\b|\bLoggingMessageNotification\w*",
        TS_OWNER + r"sendLoggingMessage\s*\(",
        r"notifications/message",
    ),
)


class DeprecatedCoreFeatures(Rule):
    id = "R007"
    title = "Depends on a deprecated core feature (Roots / Sampling / Logging)"
    severity = "deprecated"
    spec_ref = "Roots, Sampling and Logging deprecated"
    fix = "These stay in the spec for at least 12 months, then leave. Start moving now."
    languages = ("python", "typescript")

    def check(self, project: Project) -> list[Finding]:
        if project.language == "typescript":
            return self._check_ts(project)
        return self._check_python(project)

    def _check_python(self, project: Project) -> list[Finding]:
        out: list[Finding] = []
        for pattern, (name, advice) in FEATURES.items():
            # search_code: a comment/docstring mentioning "sampling" or
            # "roots/list" isn't a real dependency on the deprecated
            # feature.
            for f, line, text in project.search_code(pattern):
                out.append(self.finding(f"{name} is deprecated. {advice}", f, line, text))
        return out

    def _check_ts(self, project: Project) -> list[Finding]:
        out: list[Finding] = []
        seen: set[tuple[str, int, str]] = set()
        mcp_paths = {f.path for f in project.files if TS_MCP_SURFACE_RX.search(f.text)}

        for name, advice, code_rx, owned_rx, wire_rx in TS_FEATURES:
            message = f"{name} is deprecated. {advice}"
            hits = [
                (f, line, text, True)
                for f, line, text in project.search_code(code_rx)
            ] + [
                (f, line, text, False)
                for f, line, text in project.search_code(owned_rx)
            ] + [
                (f, line, text, True)
                for f, line, text in project.search_wire(wire_rx)
            ]
            for f, line, text, ungated in hits:
                if not ungated and f.path not in mcp_paths:
                    continue
                # Keyed by feature as well as location: one import line can
                # legitimately name two different deprecated features, and
                # those are two findings. The same feature twice on one line
                # (`const r: CreateMessageResult = await server.createMessage(...)`)
                # is one.
                key = (str(f.path), line, name)
                if key in seen:
                    continue
                seen.add(key)
                out.append(self.finding(message, f, line, text))

        return sorted(out, key=lambda x: (str(x.path or ""), x.line or 0))
