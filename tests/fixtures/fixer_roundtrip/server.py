"""Minimal broken MCP server fixture, owned by the fixer test suite.

Deliberately trips exactly the rules this package ships fixers for: the
removed session header, an unsorted tool list, a capabilities object
declared without the new 2026-07-28 field, and the deprecated streaming
transport. That lets a round-trip test run `mcp-migrate fix --write`
followed by `mcp-migrate check` and assert the grade actually improved.
Kept separate from tests/fixtures/legacy_server (owned by the rules test
suite) so this fixture's shape can't drift out from under the fixer tests
as new rules are added elsewhere.
"""
from __future__ import annotations

from mcp.server import Server
from mcp.server.sse import SseServerTransport
from mcp.types import ServerCapabilities, Tool, ToolsCapability

server = Server("fixture-server")

capabilities = ServerCapabilities(
    tools=ToolsCapability(list_changed=True),
)

transport = SseServerTransport("/messages")


def _session_for(request):
    mcp_session_id = request.headers.get("Mcp-Session-Id")
    return mcp_session_id


@server.list_tools()
async def list_tools() -> list[Tool]:
    return [
        Tool(name="zeta", description="Last alphabetically."),
        Tool(name="alpha", description="First alphabetically."),
    ]
