# Resource-not-found error code changed: `-32002` to `-32602`

- **Rule:** [R017](../src/mcp_migrate/rules/r017_resource_not_found_code_changed.py)
- **Fixer:** [R017](../src/mcp_migrate/fixers/r017_resource_not_found_code_changed.py), `safe` confidence
- **Severity:** breaking
- **Spec:** https://modelcontextprotocol.io/specification/2026-07-28/changelog

## What broke

A resource lookup that fails used to return JSON-RPC error code `-32002`.
2026-07-28 reassigns that failure to `-32602` (Invalid params). A client
written against the new spec that pattern-matches on `-32602` to mean "bad
input, don't retry the same way" never recognizes a server's old `-32002`
as the same condition -- and conversely, a server still emitting `-32002`
may get retried by a client the way it retries a transient error, when the
real problem (resource doesn't exist) will never resolve on retry.

This recipe already has a `safe`-confidence fixer -- unlike most of the
other entries in this cookbook, `mcp-migrate fix --write` fully resolves
this one whenever the line clearly reads as being about a resource lookup
failing. What's still missing here is the worked before/after and the
gotchas around the cases the fixer's context check (`-32002` *plus* a
mention of "resource" or "not found" on the same line) doesn't catch.

## Before

```python
def read_resource(uri: str) -> bytes:
    if uri not in _resources:
        raise JSONRPCError(code=-32002, message=f"resource not found: {uri}")
    return _resources[uri]
```

## After

```python
def read_resource(uri: str) -> bytes:
    if uri not in _resources:
        raise JSONRPCError(code=-32602, message=f"resource not found: {uri}")
    return _resources[uri]
```

`mcp-migrate fix --write` produces exactly this -- the `-32002` line has
both the code and the word "resource" on it, which is all the fixer's
context check requires before doing the numeric rename.

## Gotchas

- **The code and the qualifying context need to be on the same line.** A
  multi-line raise splits them apart:

  ```python
  raise JSONRPCError(
      code=-32002,
      message="not found",
  )
  ```

  Here the fixer (and the rule) never sees `-32002` and `not found` on one
  line, so neither fires -- this has to be caught and fixed by hand, or
  reformatted onto one line first.
- **`-32002` used for something other than resource-not-found is correctly
  left alone.** If your server (unusually) repurposes `-32002` for a
  different condition, a line like `raise JSONRPCError(code=-32002,
  message="rate limited")` has no "resource"/"not found" context, so
  neither the rule nor the fixer touches it -- that's intentional, not a
  gap.
- **This is one of the few `safe`-confidence fixers in the project.**
  Unlike most fixers here, which comment out code and leave a `TODO`
  because there's no mechanical replacement, this one is a pure numeric
  literal swap once the context check passes, so it applies the change
  directly rather than flagging it for review.

## Spec link

https://modelcontextprotocol.io/specification/2026-07-28/changelog
