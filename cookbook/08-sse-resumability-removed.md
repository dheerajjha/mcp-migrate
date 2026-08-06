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

```python
_events: dict[str, list[tuple[str, dict]]] = {}

async def stream(request):
    last_id = request.headers.get("Last-Event-ID")
    if last_id and last_id in _events:
        for event_id, payload in _replay_from(last_id):
            yield sse_event(event_id, payload)
    async for event_id, payload in generate_events():
        _events.setdefault(session_id, []).append((event_id, payload))
        yield sse_event(event_id, payload)
```

## After

```python
async def stream(request):
    async for event_id, payload in generate_events():
        yield sse_event(event_id, payload)
```

If the client's connection drops, it makes a new request from scratch. There
is no `Last-Event-ID` to read and nothing to replay.

## Gotchas

- **Don't delete the event store outright if it also serves audit logging or
  debugging.** Split the two purposes: keep persisting events for whatever
  else reads them, drop only the replay-on-reconnect code path and the
  `Last-Event-ID` request-header handling.
- **This rule matches the header name in any casing** (`Last-Event-ID`,
  `last_event_id`, `LAST_EVENT_ID`) via `search_code`, so a comment
  mentioning it in passing ("we used to support Last-Event-ID here") won't
  fire, but a variable or dict key still named `last_event_id` that's
  genuinely dead code will -- worth deleting the dead code rather than
  leaving it stubbed out.
- **Client-side code needs the matching change.** If the same codebase (or a
  paired client SDK) sends `Last-Event-ID` on reconnect, that call site has
  to go too -- the rule only scans for server-side implementation, it
  doesn't check whether a client elsewhere in the project still tries to
  resume.

## Spec link

https://modelcontextprotocol.io/specification/2026-07-28/changelog
