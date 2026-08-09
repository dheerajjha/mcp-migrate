"""OAuth client onboarding.

Predates Client ID Metadata Documents: registers new clients dynamically
per RFC 7591 (Dynamic Client Registration), which the 2026-07-28 spec
deprecates in CIMD's favour.

Shaped after a real implementation rather than the minimum that matched
the regex. R020's `register_client` signal is gated on the file showing
independent MCP surface (#234), because the identifier is also an entirely
ordinary method name -- `ConnectionPool.register_client` is not RFC 7591.
An earlier version of this fixture was a bare module-level function with
no MCP import anywhere, which is indistinguishable from that connection
pool and so is no longer a fixture for this rule. Real code that overrides
the SDK hook imports the provider it overrides: `mcp-atlassian`'s
`servers/oauth_proxy.py` is the shape copied here.
"""
from __future__ import annotations

from mcp.server.auth.provider import (
    OAuthAuthorizationServerProvider,
    OAuthClientInformationFull,
)


class LegacyClientRegistrar(OAuthAuthorizationServerProvider):
    async def register_client(self, client_info: OAuthClientInformationFull) -> None:
        """Dynamically register a new OAuth client (RFC 7591)."""
        self._clients[client_info.client_id] = client_info
