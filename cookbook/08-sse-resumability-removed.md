<!-- STUB: rule/spec filled in, before/after/gotchas still needed. See
     .github/GOOD_FIRST_ISSUES.md for the ready-to-file issue for this one. -->

# SSE resumability (`Last-Event-ID`) removed

- **Rule:** [R014](../src/mcp_migrate/rules/r014_sse_resumability_removed.py)
- **Fixer:** none
- **Severity:** breaking
- **Spec:** SEP-2575 -- https://modelcontextprotocol.io/specification/2026-07-28/changelog

## What broke

Stream resumability -- a client sending `Last-Event-ID` to reconnect and
replay events it missed after a dropped connection -- is gone as of
2026-07-28, independent of whether you're still on HTTP+SSE (see
[recipe 03](03-sse-to-streamable-http.md)) or already on Streamable HTTP. A
dropped connection is just a dropped connection now: the client issues a
fresh request instead of resuming a stream. A server that maintains an event
store and replays it on `Last-Event-ID` is keeping infrastructure alive for
a client behavior that no longer exists.

## Before

TODO: an event store keyed by event ID, and logic that replays from
`Last-Event-ID` on reconnect.

## After

TODO: the event store and replay logic removed. What (if anything) needs to
change on the client side of the same server to stop sending
`Last-Event-ID` and instead just retry the original request.

## Gotchas

TODO: if the event store also served a purpose beyond resumability (e.g.
audit logging, debugging), what's the safe way to retire the resumability
half without losing that other purpose?

## Spec link

https://modelcontextprotocol.io/specification/2026-07-28/changelog
