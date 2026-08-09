from .base import Finding, Project, Rule, mcp_surface_paths

# Two of these are distinctive on their own: `RegisterClientRequest` is
# MCP-SDK specific and `DynamicClientRegistration` is the RFC 7591 term of
# art. Neither shows up by accident, so neither is gated.
DISTINCTIVE_RX = r"\bRegisterClientRequest\b|\bDynamicClientRegistration\b"

# `register_client` is different, and an earlier version of this file was
# wrong about it. It argued:
#
#   A generic "register a client" method in an unrelated CRM/billing app
#   wouldn't spell it exactly `register_client`, so this is precise enough
#
# It would, and does -- `ConnectionPool.register_client` is an entirely
# ordinary thing to write. The identifier is the SDK's auth-provider hook
# (mcp.server.auth.provider.OAuthAuthorizationServerProvider.register_client)
# *and* a plain English method name, so on its own it says nothing about
# whether the file speaks MCP. Gated on independent MCP surface, the same
# way R011 gates the equally overloaded `"ping"`. See #234.
PY_HOOK_RX = r"\bregister_client\b"

# TypeScript uses camelCase for the SDK auth hook (`registerClient` in
# @modelcontextprotocol/sdk/client/auth.ts) where Python spells it
# `register_client`. The type names are the same across languages. Same
# split applies: the type names stand alone, the hook name does not.
TS_HOOK_RX = r"\bregisterClient\b"


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
        hook_rx = TS_HOOK_RX if project.language == "typescript" else PY_HOOK_RX

        out: list[Finding] = []
        seen: set[tuple[str, int]] = set()

        # search_code throughout: a comment or docstring mentioning dynamic
        # client registration isn't a real dependency on it.
        for f, line, text in project.search_code(DISTINCTIVE_RX):
            seen.add((str(f.path), line))
            out.append(self.finding(self.MESSAGE, f, line, text))

        surface = mcp_surface_paths(project)
        for f, line, text in project.search_code(hook_rx):
            if f.path not in surface:
                continue
            if (str(f.path), line) in seen:
                continue
            seen.add((str(f.path), line))
            out.append(self.finding(self.MESSAGE, f, line, text))

        return sorted(out, key=lambda x: (str(x.path or ""), x.line or 0))
