# HTTP+SSE deprecated in favor of Streamable HTTP

- **Rule:** [R006](../src/mcp_migrate/rules/r006_sse_transport.py)
- **Fixer:** [R006](../src/mcp_migrate/fixers/r006_sse_transport.py), `review`
  confidence -- renames the import and constructor call, but drops any
  constructor arguments (`StreamableHTTPServerTransport` doesn't take the SSE
  endpoint path `SseServerTransport` did) and leaves a `TODO` so a human
  confirms nothing load-bearing was lost.
- **Severity:** deprecated (stays in the spec 12+ months, then leaves
  entirely -- see [`grade.py`](../src/mcp_migrate/grade.py) for how that's
  weighted differently than `breaking`)
- **Spec:** https://modelcontextprotocol.io/specification/draft/changelog

## What broke

HTTP+SSE was the original stateful streaming transport: one long-lived SSE
connection for server-to-client messages, a separate POST endpoint for
client-to-server messages, and resumability built on `Last-Event-ID` (see
[recipe 08](08-sse-resumability-removed.md) for that half). Streamable HTTP
replaced it well before 2026-07-28, and this revision formally marks SSE
deprecated: it isn't removed yet, but it's now on a clock, and the
resumability half of it (`Last-Event-ID`) *is* gone outright as of
2026-07-28 regardless of which transport you're on.

Nothing about running `SseServerTransport` today stops working under
2026-07-28 by itself -- this is the one recipe in this cookbook that isn't
an emergency. The risk is deferred: 12+ months from now SSE support leaves
the spec, and a server that hasn't moved by then breaks for any client that
has also dropped SSE support on schedule.

## Before

```python
from mcp.server.sse import SseServerTransport

transport = SseServerTransport("/messages")
```

## After

```python
from mcp.server.streamable_http import StreamableHTTPServerTransport

transport = StreamableHTTPServerTransport()
```

## Gotchas

- **The endpoint path argument has no equivalent.** `SseServerTransport`
  took an explicit message-POST path (`"/messages"` above); Streamable HTTP
  doesn't have a separate endpoint to configure the same way. If your
  routing (reverse proxy rules, ALB target groups, API gateway paths) hardcodes
  that path, you have real infrastructure changes to make beyond the Python,
  which is exactly why `mcp-migrate fix` flags this `review`, not `safe`.
- **This is a real transport swap, not a rename.** Streamable HTTP and
  HTTP+SSE differ in route mounting, request/response framing and how a
  single request can multiplex into a stream. Renaming the class and
  dropping the argument gets your imports and constructor call correct; it
  does not by itself port your route registration or any custom SSE framing
  code you wrote around the old transport.
- **`transport="sse"` string literals are a separate call site.** If your
  server also takes a `transport=` kwarg somewhere (CLI flag, config file
  default) with the literal string `"sse"`, that needs the same rename to
  `"streamable-http"` -- the fixer handles this as its own, independent
  step, so check for it separately even if you already found and fixed the
  constructor call.
- **A backward-compat test that deliberately keeps exercising SSE is not a
  bug.** `mcp-migrate check` skips `tests/`, `fixtures/`, `examples/` by
  default for exactly this reason -- pass `--include-tests` if you actually
  want those flagged too.

## Spec link

https://modelcontextprotocol.io/specification/draft/changelog
