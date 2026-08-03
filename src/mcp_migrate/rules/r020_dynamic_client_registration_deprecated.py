from .base import Finding, Project, Rule

# All three are specific enough to MCP/OAuth client-registration code to
# carry low false-positive risk: `RegisterClientRequest` is MCP-SDK
# specific, `DynamicClientRegistration` is the RFC 7591 term of art, and
# `register_client` is the real SDK auth provider hook
# (mcp.server.auth.provider.OAuthAuthorizationServerProvider.register_client).
# A generic "register a client" method in an unrelated CRM/billing app
# wouldn't spell it exactly `register_client`, so this is precise enough
# for `deprecated` (the lower-stakes severity this item calls for).
PY_DCR_CODE_RX = (
    r"\bRegisterClientRequest\b|\bDynamicClientRegistration\b|\bregister_client\b"
)

# TypeScript uses camelCase for the SDK auth hook (`registerClient` in
# @modelcontextprotocol/sdk/client/auth.ts) where Python spells it
# `register_client`. The type names are the same across languages.
TS_DCR_CODE_RX = (
    r"\bRegisterClientRequest\b|\bDynamicClientRegistration\b|\bregisterClient\b"
)


class DynamicClientRegistrationDeprecated(Rule):
    id = "R020"
    title = "Uses Dynamic Client Registration (RFC 7591), now deprecated"
    severity = "deprecated"
    spec_ref = "https://modelcontextprotocol.io/specification/2026-07-28/changelog"
    fix = (
        "RFC 7591 Dynamic Client Registration is deprecated in favour of Client ID "
        "Metadata Documents. Plan a migration to CIMD for onboarding new OAuth clients."
    )
    languages = ("python", "typescript")

    MESSAGE = (
        "Uses RFC 7591 Dynamic Client Registration, deprecated in favour of "
        "Client ID Metadata Documents."
    )

    def check(self, project: Project) -> list[Finding]:
        pattern = TS_DCR_CODE_RX if project.language == "typescript" else PY_DCR_CODE_RX
        # search_code: a comment/docstring mentioning dynamic client
        # registration isn't a real dependency on it.
        return [
            self.finding(self.MESSAGE, f, line, text)
            for f, line, text in project.search_code(pattern)
        ]
