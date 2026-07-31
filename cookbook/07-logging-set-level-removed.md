<!-- STUB: rule/spec filled in, before/after/gotchas still needed. See
     .github/GOOD_FIRST_ISSUES.md for the ready-to-file issue for this one. -->

# `logging/setLevel` removed

- **Rule:** [R012](../src/mcp_migrate/rules/r012_logging_set_level_removed.py)
- **Fixer:** none
- **Severity:** breaking
- **Spec:** SEP-2575 -- https://modelcontextprotocol.io/specification/2026-07-28/changelog

## What broke

`logging/setLevel` (and `SetLevelRequest`) is gone -- there's no more single,
process-wide log level a client can push to a server. Log level is now
per-request: read off `_meta["io.modelcontextprotocol/logLevel"]` on each
incoming request instead of tracking one mutable global. A server that still
implements `setLevel` never gets it called by a 2026-07-28 client, so any
logic gating verbosity on that stored level effectively freezes at whatever
level it was last set to (or its default) forever.

## Before

TODO: a `SetLevelRequest` handler that mutates a module-level log level
variable, and logging calls elsewhere that check it.

## After

TODO: the handler removed, and per-request log-level handling reading
`_meta["io.modelcontextprotocol/logLevel"]` off the incoming request instead.

## Gotchas

TODO: how does this interact with a logging framework that isn't
request-scoped (e.g. Python's stdlib `logging`, which is process-global by
default)? Contextvars-based scoping is probably the real answer here and
worth spelling out.

## Spec link

https://modelcontextprotocol.io/specification/2026-07-28/changelog
