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
    r"roots/list": "Server-initiated roots/list",
    r"sampling/createMessage": "Server-initiated sampling/createMessage",
    r"elicitation/create": "Server-initiated elicitation/create",
    r"notifications/elicitation/complete": "notifications/elicitation/complete",
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

    def check(self, project: Project) -> list[Finding]:
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
            for f, line, text in project.search_wire(wire_method(pattern)):
                out.append(self.finding(
                    f"{name} was replaced by Multi Round-Trip Requests (InputRequiredResult "
                    "+ inputResponses).",
                    f, line, text,
                ))
        return out
