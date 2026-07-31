<!-- STUB: rule/spec filled in, before/after/gotchas still needed. See
     .github/GOOD_FIRST_ISSUES.md for the ready-to-file issue for this one. -->

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

TODO: a real error-raising call site using `-32002` for a resource lookup
failure -- ideally one shaped realistically enough to show what the fixer's
context requirement (`-32002` plus "resource"/"not found" on the same line)
does and doesn't catch.

## After

TODO: the same call site with `-32602`.

## Gotchas

TODO: what happens when the code and the qualifying context ("resource",
"not found") are on different lines (e.g. a multi-line `raise
JSONRPCError(\n    code=-32002,\n    message="resource not found",\n)`)? The
fixer's rule-mirrored heuristic requires both on one line -- this is a real
limitation worth documenting with an example.

## Spec link

https://modelcontextprotocol.io/specification/2026-07-28/changelog
