from mcp.server import Server

server = Server("fixture-server")


@server.list_tools()
async def list_tools():
    return []