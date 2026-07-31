import re

from .base import Finding, Project, Rule

# All three are specific enough to MCP/OAuth client-registration code to
# carry low false-positive risk: `RegisterClientRequest` is MCP-SDK
# specific, `DynamicClientRegistration` is the RFC 7591 term of art, and
# `register_client` is the real SDK auth provider hook
# (mcp.server.auth.provider.OAuthAuthorizationServerProvider.register_client).
# A generic "register a client" method in an unrelated CRM/billing app
# wouldn't spell it exactly `register_client`, so this is precise enough
# for `deprecated` (the lower-stakes severity this item calls for).
DCR_CODE_RX = re.compile(
    r"\bRegisterClientRequest\b|\bDynamicClientRegistration\b|\bregister_client\b"
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

    def check(self, project: Project) -> list[Finding]:
        out: list[Finding] = []
        # search_code: a comment/docstring mentioning dynamic client
        # registration isn't a real dependency on it.
        for f, line, text in project.search_code(DCR_CODE_RX.pattern):
            out.append(self.finding(
                "Uses RFC 7591 Dynamic Client Registration, deprecated in favour of "
                "Client ID Metadata Documents.",
                f, line, text,
            ))
        return out
