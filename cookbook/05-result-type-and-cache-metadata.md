# Required `resultType`, and `ttlMs`/`cacheScope` on list/read results

- **Rule:** [R015](../src/mcp_migrate/rules/r015_result_type_required.py)
  (advisory, a hand-rolled JSON-RPC server whose results omit `resultType`),
  [R016](../src/mcp_migrate/rules/r016_cacheable_result_required.py)
  (advisory, list/read results with no cache metadata configured)
- **Who this applies to:** **if you use the official SDK, R015 does not apply
  to you and will not fire.** `Runner._serialize` sets
  `resultType: "complete"` on every result it serializes, for every method,
  and mcp 2.0.0 ships it. There is nowhere in your handler to put the field
  and nothing for you to do. R015 is for servers that build their own
  JSON-RPC envelopes, which do own it.
  R016 *does* apply to SDK users, because the SDK fills `ttlMs`/`cacheScope`
  only when you configured the server with cache hints.
- **Fixer:** none, for both, and for different reasons. R016's `ttlMs`
  depends on how long *your* particular list response stays valid, which
  only you know; inventing a default risks being silently wrong in a way
  that's worse than the missing field. R015's blocker is the value, not a
  default: `resultType` is `"complete"` or `"input_required"` depending on
  what the specific handler does (see Gotchas below), and a fixer that
  stamps `"complete"` onto a handler that actually needs another round trip
  produces a result that looks fixed but silently drops the
  `InputRequiredResult` path. Even a TODO-only annotation doesn't have
  anywhere safe to land: the rule's finding line is the first MCP method
  name it sees in the file (typically a dispatch-table key), not the
  specific `return`/`yield` that's missing the field, so annotating it
  would point at the wrong line as often as the right one -- the same
  reason R018's fixer skips its own wire-literal call sites.
- **Severity:** advisory for both. Originally shipped `breaking`, then
  downgraded after a real audit: they check for things the new spec
  introduced, so almost nothing has adopted them yet and the finding has
  little discriminating power today.
- **Spec:** R015 is SEP-2322, R016 is SEP-2549 --
  https://modelcontextprotocol.io/specification/2026-07-28/changelog

## What broke

Every result crossing the wire now carries a required `resultType` field --
`"complete"` (this is the final answer) or `"input_required"` (the client
needs to supply more input before the call can finish; see
[recipe 10](10-multi-round-trip-requests.md) for that half). A result
missing it is malformed under 2026-07-28 and a strict client can reject it
outright.

Separately, the five list/read-shaped results (`tools/list`, `prompts/list`,
`resources/list`, `resources/read`, `resources/templates/list`) now extend
`CacheableResult`, which requires `ttlMs` (how long the client may cache
this response) and `cacheScope` (how broadly -- per-client, per-server,
global). Before this, clients had no protocol-level signal for how long a
list response stays valid, so they either re-fetched constantly or cached
with a guessed TTL that was wrong for someone.

Both are required for the same reason: they're required fields on response
shapes your handlers already return, so the fix is additive (nothing to
delete), but a response missing either is now an invalid response under the
spec, not just an incomplete one. The rules that detect this ship `advisory`
rather than `breaking`, though (see Severity above) -- the spec requirement
is real, but as absence checks against a brand-new field, they can't yet
distinguish "hasn't migrated" from "has a real problem."

## Before

```python
@server.call_tool()
async def call_tool(name: str, arguments: dict):
    if name == "get_notes":
        return {"notes": store.read(arguments["handle"])}


@server.list_tools()
async def list_tools() -> list[Tool]:
    return sorted(TOOLS, key=lambda t: t.name)
```

## After

```python
@server.call_tool()
async def call_tool(name: str, arguments: dict):
    if name == "get_notes":
        return {"resultType": "complete", "notes": store.read(arguments["handle"])}


@server.list_tools()
async def list_tools() -> list[Tool]:
    # ttlMs/cacheScope: how the *tool list itself* may be cached, not
    # anything about the notes data above -- this list rarely changes at
    # runtime, so a longer TTL and a wide cache scope are both defensible
    # here; that judgment call is exactly why this has no fixer.
    return {
        "resultType": "complete",
        "tools": sorted(TOOLS, key=lambda t: t.name),
        "ttlMs": 300_000,
        "cacheScope": "server",
    }
```

## Gotchas

- **`resultType` isn't always `"complete"`.** If your tool genuinely needs
  more input mid-call (see [recipe 10](10-multi-round-trip-requests.md)),
  return `"input_required"` with an `InputRequiredResult` shape instead --
  don't default every result to `"complete"` without checking whether some
  of your handlers actually hit that path.
- **R015/R016 use a generous presence check, not a strict schema check.**
  Once the rule decides it applies to you at all, it only checks whether the
  relevant string appears -- not that it's set on every return statement,
  spelled correctly, or attached to the right object. That's a deliberate
  false-positive/false-negative trade documented in the rule source: a wrong
  "still missing" claim costs a project visibility even at `advisory`
  severity, so the rule errs toward believing you if it sees the field
  mentioned at all. Don't take a clean `mcp-migrate check` here as proof
  every return path is correct -- grep your own handlers for every
  `return`/`yield` that produces a result.
- **A silent R015 is not a clean bill of health either.** The rule exits
  early for any project that imports the SDK, because the SDK owns the field
  there. If you use the SDK *and* hand-assemble some responses on a side
  path, R015 will not look at them. That is the price of not firing on every
  SDK server on earth, and it is the right trade -- but it means the check
  answers "is this your problem to fix?", not "is every result correct?"
- **`ttlMs` is milliseconds, not seconds** -- `300_000` above is five
  minutes, not five hundred thousand seconds.
- **`cacheScope` values are semantic, not just plumbing.** Pick per-client
  scope for anything that varies by caller identity or auth, not just
  because it's the "safe-sounding" default -- a resource list scoped
  `"server"` that actually differs per client will serve one client's data
  to another out of cache.

## Spec link

https://modelcontextprotocol.io/specification/2026-07-28/changelog
