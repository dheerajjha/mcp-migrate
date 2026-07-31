"""A FastMCP server that subclasses FastMCP and registers tools functionally.

Mirrors two real servers that silently escaped R010/R015/R016 entirely and
were handed an A they had not earned:

  * mcp-server-qdrant -- `class QdrantMCPServer(FastMCP)`, then
    `self.tool(find_foo, name="qdrant-find")` inside setup. The class is
    never *called* as `FastMCP(...)`, and the registration is a plain call
    rather than a decorator, so neither half of the old detection matched.
  * cloudwatch-mcp-server -- `mcp.tool(name='get_active_alarms')(self.get_active_alarms)`,
    the call-returning-a-decorator idiom, again with no `@` in sight.

This project registers real MCP handlers and implements no discovery RPC, so
R010 must fire on it.

Note for anyone editing this fixture: do not write the literal wire method
name in this file. R010 matches it with a *raw* search (it can only ever
appear as a JSON-RPC string, never a bare identifier), which is deliberately
permissive and counts a mention in a docstring or comment as evidence the
method is implemented. Mentioning it here would silence the very rule this
fixture exists to exercise.
"""
from __future__ import annotations

from mcp.server.fastmcp import FastMCP


class WeatherMCPServer(FastMCP):
    def __init__(self, **kwargs) -> None:
        super().__init__(name="weather", **kwargs)
        self.setup_tools()

    def setup_tools(self) -> None:
        async def get_forecast(city: str) -> str:
            return f"sunny in {city}"

        async def list_stations() -> list[str]:
            return ["stn-1", "stn-2"]

        # Functional registration -- no decorator anywhere in this file.
        self.tool(get_forecast, name="get-forecast")
        self.tool(list_stations, name="list-stations")
