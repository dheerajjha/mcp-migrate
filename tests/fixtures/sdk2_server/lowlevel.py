"""The low-level half of the 2.x API: handlers as constructor arguments."""
from mcp import types
from mcp.server import Server


async def list_tools(ctx, params):
    return types.ListToolsResult(tools=[])


async def call_tool(ctx, params):
    return types.CallToolResult(content=[])


server = Server("demo-lowlevel", on_list_tools=list_tools, on_call_tool=call_tool)
