# Required `Mcp-Method` / `Mcp-Name` routing headers

- **Rule:** [R003](../src/mcp_migrate/rules/r003_routing_headers.py)
- **Fixer:** none
- **Severity:** advisory (downgraded from an earlier `breaking` after a real
  false-positive incident -- see the rule source's comment for the
  mcp-atlassian story before reaching for a fixer here)
- **Spec:** https://modelcontextprotocol.io/specification/2026-07-28/basic/transports/streamable-http

## What broke

Requests now carry `Mcp-Method` on every request, and `Mcp-Name` on the
three methods whose routing depends on which tool/resource/prompt is named
(`tools/call`, `resources/read`, `prompts/get`) -- so a proxy in front of
the server can route and rate-limit without parsing the JSON-RPC body. A
hand-rolled HTTP client speaking MCP's wire protocol directly (not through
an SDK that already sets these) that skips them gets rejected by anything
enforcing the new transport requirement.

The failure mode is a 4xx from a proxy or gateway that enforces the
Streamable HTTP header contract, not a JSON-RPC error in the body. Your
request may never reach the MCP server at all.

## Before

```python
import httpx

_client = httpx.Client(timeout=5.0)


def notify_downstream(tool_name: str, arguments: dict) -> None:
    """Hand-roll a JSON-RPC POST to an internal MCP relay."""
    resp = _client.post(
        "https://hooks.internal.example.com/mcp-events",
        json={
            "jsonrpc": "2.0",
            "method": "tools/call",
            "params": {"name": tool_name, "arguments": arguments},
        },
    )
    resp.raise_for_status()
```

## After

```python
import httpx

_client = httpx.Client(timeout=5.0)


def notify_downstream(tool_name: str, arguments: dict) -> None:
    """Hand-roll a JSON-RPC POST to an internal MCP relay."""
    resp = _client.post(
        "https://hooks.internal.example.com/mcp-events",
        headers={
            "Mcp-Method": "tools/call",
            "Mcp-Name": tool_name,
        },
        json={
            "jsonrpc": "2.0",
            "method": "tools/call",
            "params": {"name": tool_name, "arguments": arguments},
        },
    )
    resp.raise_for_status()
```

TypeScript looks the same in spirit:

```typescript
const res = await fetch(url, {
  method: "POST",
  headers: {
    "Content-Type": "application/json",
    "Mcp-Method": "tools/call",
    "Mcp-Name": "my-tool",
  },
  body: JSON.stringify({ method: "tools/call", params: payload }),
});
```

## Gotchas

- **`Mcp-Name` is not required on every POST.** Only `tools/call`,
  `resources/read`, and `prompts/get` carry a name a proxy can route on.
  A hand-rolled `tools/list` or `initialize` call needs `Mcp-Method` but
  not `Mcp-Name` -- flagging its absence was an early R003 bug.
- **R003 is deliberately conservative about what counts as "hand-rolling
  MCP transport."** The rule only fires when the file plausibly speaks
  MCP's own wire protocol: it imports `mcp` (but not `mcp.server.fastmcp`
  or `mcp.server.transport_security`, where the SDK owns transport
  entirely), or it contains a literal like `tools/call` / `jsonrpc`. A
  plain REST client for Jira or Confluence in the same project does not
  trip this rule even though it also calls `.post()` -- that combination
  was mcp-atlassian's worst false positive (19 hits before the rule was
  tightened), which is why severity is `advisory`, not `breaking`.
- **FastMCP + a backend REST API in one file is not a finding.** A tool
  that imports only `mcp.server.fastmcp` and separately `.post()`s to its
  own search API is doing its job, not re-implementing MCP transport.
- **Header presence is checked per file, not per project.** Setting
  `Mcp-Method` in one module does not excuse a hand-rolled POST in another
  file that omits it.
- **You need an HTTP client import.** Without `requests`, `httpx`, or
  `aiohttp` in the project, R003 stays silent -- a bare `.post(` on
  something else (an ORM, a queue) is unrelated noise.
- **Prefer the SDK when you can.** If you are not deliberately crafting
  JSON-RPC envelopes, move the call behind
  `StreamableHTTPServerTransport` / the official MCP SDK client instead of
  maintaining header names by hand.

## Spec link

https://modelcontextprotocol.io/specification/2026-07-28/basic/transports/streamable-http
