# `resources/subscribe` / `resources/unsubscribe` replaced by `subscriptions/listen`

- **Rule:** [R013](../src/mcp_migrate/rules/r013_subscriptions_replaced.py)
- **Fixer:** none yet. The old model was two separate calls (subscribe once,
  unsubscribe once, get a stream of `notifications/resources/updated` in
  between); the new one is a single long-lived listen call. Collapsing that
  shape is a real control-flow rewrite, not a text substitution -- see
  [`.github/GOOD_FIRST_ISSUES.md`](../.github/GOOD_FIRST_ISSUES.md) if you
  want to take a swing at a fixer for the simplest shape of this anyway.
- **Severity:** breaking
- **Spec:** SEP-2575 -- https://modelcontextprotocol.io/specification/2026-07-28/changelog

## What broke

Before 2026-07-28, a client that wanted to be told when a resource changed
called `resources/subscribe` once, received `notifications/resources/updated`
pushes for as long as it stayed subscribed, and called
`resources/unsubscribe` when it was done. Servers implemented this as a
subscribe handler that recorded interest and an unsubscribe handler that
removed it.

2026-07-28 removes both `resources/subscribe` and `resources/unsubscribe`
and replaces them with `subscriptions/listen`: a single call that itself
represents the ongoing interest, with no separate teardown call -- the
listen ends when the client stops listening. A server whose subscribe
handler still exists never gets called (2026-07-28 clients don't send that
method), so any resource-change notification logic built on top of it goes
dead silently: no error, just a client that never hears about updates.

## Before

```python
from mcp.server import Server

server = Server("docs-mcp")
_subscribers: dict[str, set[str]] = {}


@server.subscribe_resource()
async def subscribe(uri: str, client_id: str) -> None:
    _subscribers.setdefault(uri, set()).add(client_id)


@server.unsubscribe_resource()
async def unsubscribe(uri: str, client_id: str) -> None:
    _subscribers.get(uri, set()).discard(client_id)


async def notify_resource_changed(uri: str) -> None:
    for client_id in _subscribers.get(uri, ()):
        await server.send_notification(
            client_id, "notifications/resources/updated", {"uri": uri}
        )
```

## After

```python
from mcp.server import Server

server = Server("docs-mcp")


@server.listen_subscriptions()
async def listen(uri: str, stream) -> None:
    """subscriptions/listen -- one call represents the subscription for as
    long as it's open. There's no separate unsubscribe: the client (or the
    connection) going away ends the listen, full stop.
    """
    async for change in resource_change_feed(uri):
        await stream.send({"resultType": "complete", "uri": uri, "change": change})
```

(This sketch elides the real implementation of `resource_change_feed` --
the point being made is the shape of the API, not a working pub/sub system.)

## Gotchas

- **There's no unsubscribe method to port your cleanup logic into.** Move
  whatever ran in your old unsubscribe handler (releasing a lock, decrementing
  a refcount, closing a cursor) to wherever your framework signals the
  listen call ending -- generator cleanup, a `finally` block, a disconnect
  callback -- not to a method that no longer exists.
- **This is not the same shape as a single request/response.** Unlike most
  of the other RNNN rules in this cookbook, `subscriptions/listen` is a
  long-lived call, closer to the old SSE model than to a `tools/call`. If
  your server framework's abstraction for "long-lived streaming call" is
  different from its abstraction for "one-shot request," you'll be
  reaching for a different primitive here than for the rest of the
  migration.
- **`R013` matches the JSON-RPC method strings as well as the SDK model
  names** (`SubscribeRequest`/`UnsubscribeRequest`) -- so a hand-rolled
  dispatcher matching on the literal string `"resources/subscribe"` gets
  caught even without importing the SDK's pydantic models.

## Spec link

https://modelcontextprotocol.io/specification/2026-07-28/changelog
