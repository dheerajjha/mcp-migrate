"""A note-taking MCP server, written back when sessions were still a thing.

Predates the 2026-07-28 spec revision -- kept around as a migration example.
"""
from __future__ import annotations

from opentelemetry import trace
from mcp.server import Server
from mcp.server.sse import SseServerTransport
from mcp.types import (
    RootsCapability,
    SamplingCapability,
    ServerCapabilities,
    Tool,
    ToolsCapability,
)

tracer = trace.get_tracer(__name__)

# One entry per connected client. Cleared on disconnect, but while a client
# is connected its notes and cursor position live here in process memory.
sessions: dict[str, "SessionState"] = {}


class SessionState:
    def __init__(self, client_id: str) -> None:
        self.client_id = client_id
        self.notes: list[str] = []
        self.cursor = 0


server = Server("notes-server")

capabilities = ServerCapabilities(
    tools=ToolsCapability(list_changed=True),
    roots=RootsCapability(),
    sampling=SamplingCapability(),
)

transport = SseServerTransport("/messages")


def _session_for(request) -> SessionState:
    """Look up (or lazily create) the state for this connection."""
    mcp_session_id = request.headers.get("Mcp-Session-Id")
    if mcp_session_id is None:
        raise ValueError("missing Mcp-Session-Id header")
    if mcp_session_id not in sessions:
        sessions[mcp_session_id] = SessionState(mcp_session_id)
    return sessions[mcp_session_id]


@server.list_tools()
async def list_tools() -> list[Tool]:
    with tracer.start_as_current_span("list_tools"):
        # Historically ordered by "when we shipped it," not alphabetically.
        return [
            Tool(name="add_note", description="Append a note to the session."),
            Tool(name="clear_notes", description="Wipe all notes for the session."),
            Tool(name="get_notes", description="Return the session's notes."),
            Tool(
                name="import_note",
                description="Import a note from an external, schema-validated source.",
                inputSchema={
                    "$schema": "http://json-schema.org/draft-07/schema#",
                    "type": "object",
                    "properties": {"text": {"type": "string"}},
                },
            ),
        ]


@server.call_tool()
async def call_tool(name: str, arguments: dict, request=None):
    state = _session_for(request)
    if name == "add_note":
        state.notes.append(arguments["text"])
        return {"ok": True}
    if name == "get_notes":
        return {"notes": state.notes}
    if name == "clear_notes":
        state.notes.clear()
        return {"ok": True}
    raise ValueError(f"unknown tool {name}")


@server.list_roots()
async def list_roots(request=None):
    state = _session_for(request)
    return [{"uri": f"note://{state.client_id}"}]


async def summarize(request=None) -> str:
    """Ask the client's LLM to summarize the current notes via sampling."""
    state = _session_for(request)
    result = await server.request_context.session.create_message(
        messages=[{"role": "user", "content": "\n".join(state.notes)}],
        max_tokens=200,
    )
    return result.content.text
