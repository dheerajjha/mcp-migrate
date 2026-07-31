<!-- STUB: rule/spec filled in, before/after/gotchas still needed. See
     .github/GOOD_FIRST_ISSUES.md for the ready-to-file issue for this one. -->

# Deterministic `tools/list` ordering

- **Rule:** [R004](../src/mcp_migrate/rules/r004_tool_ordering.py)
- **Fixer:** [R004](../src/mcp_migrate/fixers/r004_tool_ordering.py), `safe`
  confidence -- but only for the one unambiguous shape (a `return [...]`
  literal of all `Tool(...)` calls or all plain literals). Anything built up
  across several statements is left alone.
- **Severity:** advisory
- **Spec:** "Deterministic tool ordering" (SHOULD) -- https://modelcontextprotocol.io/specification/draft/changelog

## What broke

Nothing breaks a connection here -- this is advisory, the lowest-stakes
severity. But `tools/list` order was never guaranteed, and returning tools
in whatever order they happen to be defined (insertion order, dict
iteration order, historical "when we shipped it" order) defeats client-side
caching and hurts LLM prompt-cache hit rates: if the list looks different
on every call, nothing downstream can treat it as stable.

## Before

TODO: a real example of a `list_tools` handler where the fixer's shape
detection *doesn't* apply -- e.g. tools built up across an `if`/`append`
sequence, or returned from a variable assembled elsewhere -- to show what's
still a manual fix even with the fixer shipped.

## After

TODO: the same handler with an explicit, deterministic sort.

## Gotchas

TODO: what's the right sort key when tools don't have a natural one (no
`.name`, or intentionally grouped/ordered for UX reasons)? "Sort
alphabetically" isn't always correct if there's product intent behind an
order -- worth a note on when *not* to blindly alphabetize.

## Spec link

https://modelcontextprotocol.io/specification/draft/changelog
