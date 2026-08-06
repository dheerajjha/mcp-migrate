# `ping` removed from the protocol

- **Rule:** [R011](../src/mcp_migrate/rules/r011_ping_removed.py)
- **Fixer:** none yet on `main`, see [#21](https://github.com/dheerajjha/mcp-migrate/issues/21)
  (a `review`-confidence fixer is up in [#124](https://github.com/dheerajjha/mcp-migrate/pull/124))
- **Severity:** breaking
- **Spec:** SEP-2575 -- https://modelcontextprotocol.io/specification/2026-07-28/changelog

## What broke

`ping`/`PingRequest` is removed as a JSON-RPC method. Liveness now rides on
the transport itself (HTTP keepalive, TCP-level health checks) instead of an
application-level ping/pong. A server that still implements a `ping` handler
isn't broken by having it -- a 2026-07-28 client simply never calls it -- but
a server whose *own* health-check tooling or reverse-proxy probe sends
`ping` over the MCP connection and waits for a JSON-RPC response now waits
forever, because nothing on the client side sends that request anymore.

## Before

```python
async def handle_request(method: str, params: dict) -> dict:
    if method == "ping":
        return {}
    if method == "tools/call":
        return await handle_tool_call(params)
    raise ValueError(f"unknown method: {method}")
```

## After

```python
async def handle_request(method: str, params: dict) -> dict:
    if method == "tools/call":
        return await handle_tool_call(params)
    raise ValueError(f"unknown method: {method}")
```

Liveness checks move to the transport: an HTTP load balancer hitting a
`/healthz` route, or TCP keepalive on a raw socket transport -- not a
JSON-RPC round trip.

## Gotchas

- **A `/ping` HTTP health-check route is not this.** `R011`'s dispatch
  signal only fires on `"ping"` compared against a `method` variable or used
  as a dispatch key (`case "ping":`, `{"ping": handler}`) -- ordinary web
  framework routes like `@app.route("/ping")` never match, since there's no
  `method ==` comparison anywhere near them.
- **Removing the branch can leave a dangling `if`/`case`.** If your
  dispatcher is a chain of `if method == "ping": ... elif method == "...":`,
  deleting the ping branch is safe; if it's the *only* branch in a `match`
  statement, you'll need to remove the enclosing block too, not just the
  case line.
- **A block-opener line (anything ending in `:`) can't just be commented
  out.** Doing so would leave a dangling suite -- `#124`'s fixer only
  touches non-block-opener dispatch shapes (e.g. a dict-keyed handler
  table) and declines the `if`/`case` shapes above entirely, leaving them
  for a human.

## Spec link

https://modelcontextprotocol.io/specification/2026-07-28/changelog
