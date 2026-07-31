<!-- STUB: rule/spec filled in, before/after/gotchas still needed. See
     .github/GOOD_FIRST_ISSUES.md for the ready-to-file issue for this one. -->

# `ping` removed from the protocol

- **Rule:** [R011](../src/mcp_migrate/rules/r011_ping_removed.py)
- **Fixer:** none
- **Severity:** breaking
- **Spec:** SEP-2575 -- https://modelcontextprotocol.io/specification/2026-07-28/changelog

## What broke

`ping`/`PingRequest` is removed as a JSON-RPC method. Liveness now rides on
the transport itself (HTTP keepalive, TCP-level health checks) instead of an
application-level ping/pong. A server that still implements a `ping` handler
isn't broken by having it (2026-07-28 clients simply never call it), but a
server whose *own* client-facing health check or reverse-proxy probe relies
on sending `ping` and expecting a JSON-RPC response now gets nothing back.

## Before

TODO: a real handler for `PingRequest`, or a manual dispatcher branch
matching `method == "ping"`.

## After

TODO: the handler removed, and (if applicable) whatever previously drove
health checks over `ping` moved to a transport-level check instead.

## Gotchas

TODO: does this rule's `PING_DISPATCH_RX` heuristic (matching `"ping"`
compared against a `method` variable, or used as a dispatch key) miss any
real-world dispatch shapes? Worth checking against an actual server that
implements manual JSON-RPC routing.

## Spec link

https://modelcontextprotocol.io/specification/2026-07-28/changelog
