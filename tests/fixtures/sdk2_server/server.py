"""A server written the way the Python SDK 2.x tells you to (#255).

In mcp 2.x `FastMCP` is `MCPServer`, and the low-level decorators are gone:
handlers arrive as `Server(...)` constructor arguments (see lowlevel.py) or
through `add_request_handler`. Before #307 none of that counted as evidence of
an MCP server, so this project graded A with nothing found.

Both files were checked against mcp 2.2.0: they import, and constructing both
servers succeeds.

Expected: R016 fires once in each file, because `cache_hints` defaults to None
on both `Server` and `MCPServer` in 2.x. R010 stays silent, because the SDK
registers the method it looks for inside `Server.__init__`, and
pyproject.toml's 2.x floor is how the rule knows that.

Do not write R010's wire method name anywhere in this directory. The rule
counts a mention in code as an implementation, and one would silence it here
for a reason unrelated to the one this fixture exists to test.
"""
from mcp.server import MCPServer

app = MCPServer("demo", version="1.0.0")


@app.tool()
async def search(query: str) -> str:
    """Search the demo index."""
    return query
