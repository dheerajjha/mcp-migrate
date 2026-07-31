<!-- STUB: rule/spec filled in, before/after/gotchas still needed. See
     .github/GOOD_FIRST_ISSUES.md for the ready-to-file issue for this one. -->

# `extensions` map on `ServerCapabilities`

- **Rule:** [R005](../src/mcp_migrate/rules/r005_extensions.py)
- **Fixer:** [R005](../src/mcp_migrate/fixers/r005_extensions.py), `safe`
  confidence -- adds `extensions={}` to a `ServerCapabilities(...)` call
  that doesn't already have one; this is a pure no-op at runtime since an
  absent value already meant "no extensions."
- **Severity:** advisory
- **Spec:** "extensions field on ServerCapabilities" -- https://modelcontextprotocol.io/specification/draft/changelog

## What broke

Optional capabilities now negotiate through an `extensions` map on
`ServerCapabilities` rather than being assumed absent. Declaring
capabilities without it doesn't break anything today -- a 2026-07-28 client
just sees no extensions and moves on -- but it also tells the client
nothing about which 2026-07-28-era extensions (like
`io.modelcontextprotocol/tasks`, see [recipe 11](11-tasks-polling.md)) this
server does or doesn't support.

## Before

TODO: a `ServerCapabilities(...)` construction without `extensions`.

## After

TODO: the same construction with `extensions={}` (or populated, if the
server actually implements one).

## Gotchas

TODO: worth an example of a server that *does* implement a real extension
(Tasks is the obvious one -- see recipe 11) and what a populated
`extensions` map looks like versus the empty-map "I speak 2026-07-28, I
just don't support any extensions" case the fixer produces.

## Spec link

https://modelcontextprotocol.io/specification/draft/changelog
