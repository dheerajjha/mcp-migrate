"""A single-file FastMCP server that also calls its own backend REST API.

Mirrors real false positives found scanning aws-documentation-mcp-server
and duckduckgo-mcp-server: both import only `mcp.server.fastmcp` (the
high-level decorator API, which owns the transport entirely) and
separately `.post()` to their own backend search API in the same file.
Neither references MCP's own wire protocol at all, so R003 should not
fire here even though the file both imports something under `mcp.*` and
calls `.post()`.
"""
from __future__ import annotations

import httpx
from mcp.server.fastmcp import Context, FastMCP

mcp = FastMCP("demo-search")


@mcp.tool()
async def search(query: str, ctx: Context) -> str:
    async with httpx.AsyncClient() as client:
        response = await client.post(
            "https://search.example.com/api/query",
            json={"q": query},
        )
        response.raise_for_status()
        return response.text
