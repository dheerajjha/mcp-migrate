from .base import Finding, Fires, Project, Rule, Silent, wire_method

# Code-shaped identifiers -- SDK model/class names or plain Python names,
# matched with search_code so a docstring/comment mention doesn't count.
# `list_roots`/`create_message` are not "a little more generic-sounding",
# which is what this comment used to say -- they are the names anyone gives
# the function that builds a message or lists roots, in any protocol. A bare
# `create_message` matched an LSP wire-framing helper in oraios/serena and
# contributed to a `breaking` grade published about a project whose MCP code
# was clean (#289). r007 already solved this by requiring the `session.`
# receiver, so this now carries the same anchor rather than the bare name,
# The SDK schema names beside it are distinctive and stay unanchored --
# gating those would only add a way to miss a real finding. They are
# otherwise the same signals r007 ships
# with for these two features, just now also reported as `breaking` under
# SEP-2322's replacement of the whole server-initiated-request pattern (as
# opposed to r007's "still deprecated, not yet gone" framing). The two
# rules firing on the same line is expected, not a bug -- both claims are
# true -- but showing the reader two contradicting severities for one
# symbol isn't, so `overlap.py` collapses the pair back into a single
# finding at report time (see #221).
FEATURES_CODE = {
    r"\bsession\.list_roots\b|\bListRootsRequest(?:Params|Schema)?\b|\bListRootsResult(?:Schema)?\b": "Server-initiated roots/list",
    r"\bsession\.create_message\b|\bCreateMessageRequest(?:Params|Schema)?\b|\bCreateMessageResult(?:Schema)?\b": "Server-initiated sampling/createMessage",
    r"\bElicitRequest(?:Params|Schema)?\b|\bElicitResult(?:Schema)?\b": "Server-initiated elicitation/create",
    r"\bElicitCompleteNotificationParams(?:Schema)?\b": "notifications/elicitation/complete",
    r"\belicitationId\b": "elicitationId",
}

# JSON-RPC method-name strings. Namespaced with a slash, so unlike a bare
# word these aren't things unrelated code reuses by accident -- but for
# that same reason (a slash isn't valid in a Python identifier) they can
# only ever appear inside a STRING token, so search_code would never find
# them (see the notifications/initialized note in r009). Raw scan instead.
FEATURES_LITERAL = {
    wire_method("roots/list"): "Server-initiated roots/list",
    wire_method("sampling/createMessage"): "Server-initiated sampling/createMessage",
    wire_method("elicitation/create"): "Server-initiated elicitation/create",
    wire_method("notifications/elicitation/complete"): (
        "notifications/elicitation/complete"
    ),
}

# The TypeScript SDK exports Zod schemas for request handling. These names
# are specific to the removed MCP server-initiated requests, unlike generic
# callback names such as `createMessage` or `listRoots`.
#
# `elicitationId` is the odd one out here: it isn't a request/schema class,
# it's a field name a handler reads off an incoming payload
# (`params.elicitationId`), the same shape in both languages -- see
# `elicitationId` in FEATURES_CODE above. It has no `Schema` counterpart to
# miss, so it's just the bare identifier, same as the Python side.
TS_FEATURES_CODE = {
    r"\bListRootsRequestSchema\b": "Server-initiated roots/list",
    r"\bCreateMessageRequestSchema\b": "Server-initiated sampling/createMessage",
    r"\bElicitRequestSchema\b": "Server-initiated elicitation/create",
    r"\belicitationId\b": "elicitationId",
}


class MultiRoundTripReplacesServerInitiated(Rule):
    id = "R018"
    title = "Uses a server-initiated request replaced by Multi Round-Trip Requests"
    severity = "breaking"
    spec_ref = "SEP-2322 https://modelcontextprotocol.io/specification/2026-07-28/changelog"
    fix = (
        "Server-initiated roots/list, sampling/createMessage and elicitation/create are "
        "gone, along with notifications/elicitation/complete and elicitationId. Return "
        "an InputRequiredResult instead and let the client retry the call with "
        "inputResponses."
    )
    languages = ("python", "typescript")
    boundaries = (
        Fires(
            snippet=(
                "async def handler(ctx):\n"
                "    return await ctx.session.create_message(messages=[])"
            ),
            reason="Sampling through the MCP session is a removed server-initiated request.",
        ),
        Fires(
            snippet=(
                "async def gather(ctx):\n"
                "    return await ctx.session.list_roots()\n"
            ),
            reason="Listing roots through the MCP session is a removed server-initiated request.",
        ),
        Fires(
            snippet="from mcp.types import ListRootsResult",
            reason="The SDK result type belongs to the removed server-initiated roots flow.",
        ),
        Fires(
            snippet='METHOD = "elicitation/create"',
            reason="The exact removed elicitation wire method is still present.",
        ),
        Fires(
            snippet="def on_complete(params):\n    return params.elicitationId\n",
            reason="The removed elicitation correlation field is active Python code.",
        ),
        Silent(
            snippet=(
                "def create_message(payload):\n"
                "    return payload"
            ),
            reason="A generic message-building helper without the session receiver is not MCP sampling.",
        ),
        Silent(
            snippet=(
                "import os\n\n"
                "def list_roots(base):\n"
                "    return sorted(os.listdir(base))\n"
            ),
            reason="A directory-listing helper without the session receiver is not MCP roots.",
        ),
        Silent(
            snippet=(
                'def handler():\n'
                '    """Sent CreateMessageRequest before Multi Round-Trip Requests replaced it."""\n'
            ),
            reason="A docstring that names the old request type is documentation, not surface.",
        ),
        Silent(
            snippet="# CreateMessageRequest and sampling/createMessage were replaced by MRTR",
            reason="A migration comment is prose, not an active server-initiated request.",
        ),
        Silent(
            snippet='METRIC = "roots/listeners"',
            reason="A longer wire name is outside the exact roots/list method boundary.",
        ),
        Silent(
            snippet="result = InputRequiredResult(inputResponses=[])",
            reason="The replacement Multi Round-Trip result shape is already migrated.",
        ),
        Fires(
            snippet=(
                'import { CreateMessageRequestSchema } from "@modelcontextprotocol/sdk/types.js";\n'
                "client.setRequestHandler(CreateMessageRequestSchema, handler);"
            ),
            reason="The removed sampling request schema is active TypeScript MCP code.",
            language="typescript",
        ),
        Fires(
            snippet='const legacyMethod = "sampling/createMessage";',
            reason="The exact removed sampling wire method is still present in TypeScript.",
            language="typescript",
        ),
        Fires(
            snippet="function onReply(params: { elicitationId: string }) { return params.elicitationId; }",
            reason="The removed elicitation correlation field is active TypeScript code.",
            language="typescript",
        ),
        Silent(
            snippet="// CreateMessageRequestSchema and sampling/createMessage were replaced by MRTR.",
            reason="A TypeScript migration comment is prose, not active MCP surface.",
            language="typescript",
        ),
        Silent(
            snippet='const method = "sampling/createMessageLatency";',
            reason="A longer TypeScript wire name is outside the exact method boundary.",
            language="typescript",
        ),
        Silent(
            snippet="const result = { inputResponses: [] };",
            reason="The replacement Multi Round-Trip result shape is already migrated.",
            language="typescript",
        ),
        Silent(
            snippet=(
                'const createMessage = (text: string) => ({ role: "user", text });\n'
                'const listRoots = () => fs.readdirSync("/");\n'
            ),
            reason="Generic createMessage/listRoots callbacks are not the SDK's request schemas.",
            language="typescript",
        ),
    )

    def check(self, project: Project) -> list[Finding]:
        if project.language == "typescript":
            out: list[Finding] = []
            for pattern, name in TS_FEATURES_CODE.items():
                for f, line, text in project.search_code(pattern):
                    out.append(self.finding(
                        f"{name} was replaced by Multi Round-Trip Requests (InputRequiredResult "
                        "+ inputResponses).",
                        f,
                        line,
                        text,
                        feature=name,
                    ))
            for pattern, name in FEATURES_LITERAL.items():
                for f, line, text in project.search_wire(pattern):
                    out.append(self.finding(
                        f"{name} was replaced by Multi Round-Trip Requests (InputRequiredResult "
                        "+ inputResponses).",
                        f,
                        line,
                        text,
                        feature=name,
                    ))
            return out

        out: list[Finding] = []
        for pattern, name in FEATURES_CODE.items():
            # search_code: a comment/docstring mentioning "sampling" or
            # "roots/list" isn't a real dependency on it (see
            # r007_deprecated_features.py, same reasoning).
            for f, line, text in project.search_code(pattern):
                out.append(self.finding(
                    f"{name} was replaced by Multi Round-Trip Requests (InputRequiredResult "
                    "+ inputResponses).",
                    f, line, text,
                    feature=name,
                ))
        for pattern, name in FEATURES_LITERAL.items():
            # Already bounded at the definition, so both this path and the
            # TypeScript one above get the end boundary from the same place.
            # Wrapping again here would escape the pattern's own metacharacters
            # and match nothing.
            for f, line, text in project.search_wire(pattern):
                out.append(self.finding(
                    f"{name} was replaced by Multi Round-Trip Requests (InputRequiredResult "
                    "+ inputResponses).",
                    f, line, text,
                    feature=name,
                ))
        return out
