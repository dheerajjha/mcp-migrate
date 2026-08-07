from .base import Finding, Project, Rule, wire_method

# Code-shaped identifiers -- SDK model/class names or plain Python names,
# matched with search_code so a docstring/comment mention doesn't count.
# `list_roots`/`create_message` are a little more generic-sounding, but
# they're the exact same signal r007_deprecated_features.py already ships
# with for these two features, just now also reported as `breaking` under
# SEP-2322's replacement of the whole server-initiated-request pattern (as
# opposed to r007's "still deprecated, not yet gone" framing) -- so some
# double-reporting between R007 and R018 on the same line is expected, not
# a bug.
FEATURES_CODE = {
    r"\blist_roots\b|\bListRootsRequest(?:Params|Schema)?\b|\bListRootsResult(?:Schema)?\b": "Server-initiated roots/list",
    r"\bcreate_message\b|\bCreateMessageRequest(?:Params|Schema)?\b|\bCreateMessageResult(?:Schema)?\b": "Server-initiated sampling/createMessage",
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
                    ))
            for pattern, name in FEATURES_LITERAL.items():
                for f, line, text in project.search_wire(pattern):
                    out.append(self.finding(
                        f"{name} was replaced by Multi Round-Trip Requests (InputRequiredResult "
                        "+ inputResponses).",
                        f,
                        line,
                        text,
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
                ))
        return out
