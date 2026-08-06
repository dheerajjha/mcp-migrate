# Roots, Sampling and Logging deprecated as core capabilities

- **Rule:** [R007](../src/mcp_migrate/rules/r007_deprecated_features.py)
  (deprecated -- reports the same code as [R018](../src/mcp_migrate/rules/r018_multi_round_trip_replaces_server_initiated.py)'s
  `breaking` finding for Sampling/elicitation specifically; both firing on
  the same line is expected, not a bug)
- **Fixer:** none
- **Severity:** deprecated
- **Spec:** "Roots, Sampling and Logging deprecated" -- https://modelcontextprotocol.io/specification/draft/changelog

## What broke

Roots, Sampling and Logging are deprecated as core capabilities -- on the
same 12+ month clock as HTTP+SSE ([recipe 03](03-sse-to-streamable-http.md)).
Nothing stops working today. Roots' replacement is resource URIs; Sampling's
server-initiated form is superseded now by Multi Round-Trip Requests (see
[recipe 10](10-multi-round-trip-requests.md), which covers the `breaking`
half of this same change); Logging is moving to an extension entirely.

## Before

```python
server = Server("my-server", capabilities=ServerCapabilities(roots=RootsCapability()))

async def read_config():
    roots = await session.list_roots()
    return open(roots[0].uri).read()
```

## After

```python
server = Server("my-server")  # roots capability dropped

async def read_config(config_uri: str):
    return await read_resource(config_uri)
```

The client passes a resource URI directly instead of the server asking it
to enumerate roots -- the same shift from "server asks, client answers
inline" to "client supplies what it already has" that shows up across this
whole spec revision.

## Gotchas

- **R007 and R018 both fire on `session.create_message(...)` calls, and
  that's intentional, not double-counting.** R007 reports Sampling as
  `deprecated` -- it's on the slow clock, still works today. R018 reports
  the exact same server-initiated call as `breaking` under Multi
  Round-Trip Requests -- it's a different, faster-moving consequence of the
  same underlying change. When both show up on one line, act on the
  `breaking` one first (R018's fix, restructuring around
  `InputRequiredResult`); R007's `deprecated` finding for the same line
  resolves as a side effect once R018's fix lands, since the deprecated
  call is gone either way.
- **Roots and Logging don't have an R018 counterpart -- only Sampling
  does.** `roots/list` and Logging's `notifications/message` are purely
  `deprecated` here, with no matching `breaking` rule elsewhere, because
  neither is a server-initiated-request pattern the way Sampling is.
- **The Python match is anchored on `session.create_message` specifically,
  not a bare `create_message`.** A bare match collided with the Anthropic
  Messages API's own `create_message` wrapper in real servers scanned
  against this project's registry -- anchoring on the MCP session object
  keeps the true positives (`ctx.session.create_message(...)`,
  `server.request_context.session.create_message(...)`) while dropping
  unrelated LLM client code that happens to share the method name.

## Spec link

https://modelcontextprotocol.io/specification/draft/changelog
