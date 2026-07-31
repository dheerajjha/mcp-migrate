"""Integration test asserting the server still constructs the deprecated
HTTP+SSE transport, for backward compatibility with older clients.

This mirrors real evidence found scanning motherduck's MCP server: a
deliberate legacy-transport backward-compat test tripped R006 in the
project's own test suite, even though the *server* had long since moved to
Streamable HTTP. A well-tested project should not be penalized for
exercising deprecated-but-still-supported code paths in its tests.
"""
from __future__ import annotations

from mcp.server.sse import SseServerTransport


def test_legacy_transport_still_constructs():
    transport = SseServerTransport("/messages")
    assert transport is not None
