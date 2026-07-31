# Required `resultType`, and `ttlMs`/`cacheScope` on list/read results

- **Rule:** [R015](../src/mcp_migrate/rules/r015_result_type_required.py)
  (breaking, any result missing `resultType`), [R016](../src/mcp_migrate/rules/r016_cacheable_result_required.py)
  (breaking, list/read results missing `ttlMs`/`cacheScope`)
- **Fixer:** none. Both fields depend on information only the handler
  author has (is this call actually done, or does it need another round
  trip? how long can *this* particular list response be cached?) --
  inventing a default risks being silently wrong in a way that's worse than
  the missing field, so neither ships a fixer.
- **Severity:** breaking
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

Both are breaking for the same reason: they're required fields on response
shapes your handlers already return, so the fix is additive (nothing to
delete), but a response missing either is now an invalid response, not just
an incomplete one.

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
  Both rules only check whether the string `resultType` (or `ttlMs`/
  `cacheScope`) appears anywhere in the file that implements the handler --
  not that it's set on every return statement, or spelled correctly, or
  attached to the right object. That's a deliberate false-positive/false-negative
  trade documented in the rule source: a wrong "still missing" claim on a
  `breaking` rule costs a project its badge, so the rule errs toward
  believing you if it sees the field mentioned at all. Don't take a clean
  `mcp-migrate check` here as proof every return path is actually correct --
  grep your own handlers for every `return`/`yield` that produces a result.
- **`ttlMs` is milliseconds, not seconds** -- `300_000` above is five
  minutes, not five hundred thousand seconds.
- **`cacheScope` values are semantic, not just plumbing.** Pick per-client
  scope for anything that varies by caller identity or auth, not just
  because it's the "safe-sounding" default -- a resource list scoped
  `"server"` that actually differs per client will serve one client's data
  to another out of cache.

## Spec link

https://modelcontextprotocol.io/specification/2026-07-28/changelog
