from .base import Finding, Project, Rule, wire_method

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
    rf"{wire_method('roots/list')}|list_roots|RootsCapability": ("Roots", "Use resource URIs instead."),
    r"sampling/createMessage|SamplingCapability|\bsession\.create_message\b"
    r"|\bCreateMessageRequest(?:Params|Schema)?\b|\bCreateMessageResult(?:Schema)?\b": (
        "Sampling", "Sampling is deprecated; plan a migration."),
    r"notifications/message|LoggingCapability|set_logging_level": ("Logging", "Logging moves out of core; use an extension."),
}


class DeprecatedCoreFeatures(Rule):
    id = "R007"
    title = "Depends on a deprecated core feature (Roots / Sampling / Logging)"
    severity = "deprecated"
    spec_ref = "Roots, Sampling and Logging deprecated"
    fix = "These stay in the spec for at least 12 months, then leave. Start moving now."

    def check(self, project: Project) -> list[Finding]:
        out: list[Finding] = []
        for pattern, (name, advice) in FEATURES.items():
            # search_code: a comment/docstring mentioning "sampling" or
            # "roots/list" isn't a real dependency on the deprecated
            # feature.
            for f, line, text in project.search_code(pattern):
                out.append(self.finding(f"{name} is deprecated. {advice}", f, line, text))
        return out
