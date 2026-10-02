"""The low-level half of the 2.x API: handlers as constructor arguments.

Formatted the way black writes it, with `Server(` on a line of its own and
each handler below. Until 0.11.1 a line-at-a-time match missed exactly this
shape, and the most common formatting of a 2.x server graded as if it had no
handlers at all.
"""
from mcp import types
from mcp.server import Server


async def list_tools(ctx, params):
    return types.ListToolsResult(tools=[])


async def call_tool(ctx, params):
    return types.CallToolResult(content=[])


server = Server(
    "demo-lowlevel",
    on_list_tools=list_tools,
    on_call_tool=call_tool,
)
