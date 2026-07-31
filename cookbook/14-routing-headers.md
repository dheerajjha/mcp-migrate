<!-- STUB: rule/spec filled in, before/after/gotchas still needed. See
     .github/GOOD_FIRST_ISSUES.md for the ready-to-file issue for this one. -->

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

## Before

TODO: a hand-rolled `.post()` call sending a raw JSON-RPC envelope
(`{"method": "tools/call", ...}`) without setting `Mcp-Method`/`Mcp-Name`.

## After

TODO: the same call with both headers set.

## Gotchas

TODO: this rule is deliberately conservative about what counts as "hand-rolling
MCP transport" versus "wrapping some unrelated backend REST API in the same
file" -- worth walking through the actual gating logic
(`_imports_mcp`/`MCP_METHOD_RX`) with a concrete example of each so a reader
understands why one file trips this and a similar-looking one doesn't.

## Spec link

https://modelcontextprotocol.io/specification/2026-07-28/basic/transports/streamable-http
