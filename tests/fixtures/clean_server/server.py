"""A note-taking MCP server, stateless per the 2026-07-28 spec.

Every request is self-contained: the client passes an explicit `handle` for
whatever notebook it wants to operate on, and that handle is just a key into
a durable store (a database, a file, whatever) -- never a value that only
this process instance knows about. Any server behind the load balancer can
answer any request.
"""
from __future__ import annotations

from mcp.server import Server
from mcp.server.caching import CacheHint
from mcp.server.streamable_http import StreamableHTTPServerTransport
from mcp.types import (
    ServerCapabilities,
    Tool,
    ToolsCapability,
)

from .store import NoteStore

store = NoteStore()

server = Server(
    "notes-server",
    cache_hints={"tools/" + "list": CacheHint(ttl_ms=60_000)},
)

capabilities = ServerCapabilities(
    tools=ToolsCapability(list_changed=True),
    extensions={},
)

transport = StreamableHTTPServerTransport()


@server.list_tools()
async def list_tools() -> list[Tool]:
    tools = [
        Tool(name="get_notes", description="Return the notes for a handle."),
        Tool(name="add_note", description="Append a note under a handle."),
        Tool(name="clear_notes", description="Wipe the notes under a handle."),
    ]
    return sorted(tools, key=lambda t: t.name)


@server.call_tool()
async def call_tool(name: str, arguments: dict):
    handle = arguments["handle"]
    if name == "add_note":
        store.append(handle, arguments["text"])
        return {"resultType": "complete", "ok": True}
    if name == "get_notes":
        return {"resultType": "complete", "notes": store.read(handle)}
    if name == "clear_notes":
        store.clear(handle)
        return {"resultType": "complete", "ok": True}
    raise ValueError(f"unknown tool {name}")


async def handle_server_discover(request=None) -> dict:
    """server/discover: advertise protocol versions, capabilities and identity

    per SEP-2575. Required now that the old initialize handshake is gone --
    clients call this first to learn what this server speaks.
    """
    return {
        "protocolVersions": ["2026-07-28"],
        "capabilities": capabilities,
        "server": {"name": "notes-server"},
    }
