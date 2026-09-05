# The `initialize`/`initialized` handshake is replaced by `server/discover`

- **Rule:** [R009](../src/mcp_migrate/rules/r009_initialize_handshake_removed.py)
  (breaking, still implements the old handshake), [R010](../src/mcp_migrate/rules/r010_server_discover_missing.py)
  (advisory, registers handlers but never implements `server/discover` in
  source-visible code)
- **Fixer:** R010 adds a review-only `server/discover` scaffold when it finds
  one unambiguous low-level Python server receiver. It leaves TODO placeholders
  for protocol versions, capabilities, and server identity; FastMCP,
  functional, and ambiguous registrations are left unchanged. The generated
  handler is intentionally left unregistered as a starting point. Complete the
  protocol response and verify how the target MCP SDK exposes `server/discover`
  before adding any registration. In SDKs that provide an explicit decorator
  or wire mapping, use that mechanism; in SDKs that register `server/discover`
  automatically, no additional registration is required. R010 recognizes
  active source-visible registrations as evidence of an implementation, but a
  bare function definition does not clear the finding.
- **Severity:** R009 is breaking; R010 is advisory (downgraded from
  `breaking` after a real audit found it fires on ~100% of servers, since
  it checks for something the new spec introduced).
- **Spec:** SEP-2575 -- https://modelcontextprotocol.io/specification/2026-07-28/changelog

## What broke

Every MCP connection used to open with a negotiation round trip: the client
sent `initialize` with its own protocol version and capabilities, the server
replied with `InitializeResult` describing its own, and the client then sent
a `notifications/initialized` notification before issuing any real request.
Nothing else was usable until all three messages had gone by.

2026-07-28 removes that handshake entirely and replaces it with a single
`server/discover` request: no negotiation round trip, no `initialized`
notification, no dependency on message ordering to know when the connection
is "ready." A server that still waits for `initialize` before answering
anything else never becomes usable to a 2026-07-28 client, because that
client never sends it -- it sends `server/discover` and, on getting a
response, immediately starts issuing real requests.

## Before

```python
from mcp.server import Server
from mcp.types import InitializeResult, ServerCapabilities

server = Server("weather-mcp")


@server.initialize()
async def handle_initialize(params) -> InitializeResult:
    return InitializeResult(
        protocolVersion="2025-06-18",
        capabilities=ServerCapabilities(tools={}),
        serverInfo={"name": "weather-mcp", "version": "1.4.0"},
    )


@server.initialized()
async def handle_initialized(params) -> None:
    logger.info("client finished handshake")
```

## After

```python
from mcp.server import Server
from mcp.types import ServerCapabilities

server = Server("weather-mcp")

CAPABILITIES = ServerCapabilities(tools={}, extensions={})


@server.discover()
async def handle_server_discover(request=None) -> dict:
    """server/discover -- the first (and only pre-request) call a
    2026-07-28 client makes. No round trip: this single response tells the
    client which protocol versions, capabilities and identity this server
    has, and the client can issue a real request immediately after.
    """
    return {
        "protocolVersions": ["2026-07-28"],
        "capabilities": CAPABILITIES,
        "server": {"name": "weather-mcp", "version": "1.4.0"},
    }
```

## Gotchas

- **Don't just rename the method and keep the two-message shape.** There is
  no `discovered`/`discover_complete` follow-up notification --
  `server/discover` is a single request/response, full stop. If you keep
  code that waits for a second message before considering the client
  "ready," you've reintroduced the handshake under a new name.
- **`protocolVersions` is plural.** The old `InitializeResult.protocolVersion`
  was a single string the client had to match exactly or fail; `discover`
  lets a server advertise every version it can speak, so a client picks the
  best mutually supported one. Returning a single hardcoded string here
  works but throws away the whole point of the field.
- **R010 only fires if the project registers handlers at all.** It's gated
  on finding `list_tools`/`call_tool`/etc. (or FastMCP's `.tool()` decorator
  plus a `FastMCP(...)` instantiation) somewhere in the project first -- a
  library or a pure MCP *client* with no handlers won't be flagged, and
  shouldn't be. For Python source, R010 recognizes an explicit registered
  decorator or wire mapping when one is present. TypeScript also recognizes a
  conventional `discover`-named handler. SDK-provided registrations that
  exist only inside the installed dependency may not be visible to the source
  scanner.
- **SDK-provided handlers:** R010 is a source scanner and cannot infer a
  `server/discover` handler that exists only inside an installed SDK. Verify
  the SDK's behavior when interpreting the result.

## Spec link

https://modelcontextprotocol.io/specification/2026-07-28/changelog
