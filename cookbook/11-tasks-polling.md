<!-- STUB: rule/spec filled in, before/after/gotchas still needed. See
     .github/GOOD_FIRST_ISSUES.md for the ready-to-file issue for this one. -->

# Tasks moved to an extension; polling replaces blocking `tasks/result`

- **Rule:** [R019](../src/mcp_migrate/rules/r019_tasks_polling_replaces_blocking_result.py)
- **Fixer:** none
- **Severity:** breaking
- **Spec:** SEP-2663 -- https://modelcontextprotocol.io/specification/2026-07-28/changelog

## What broke

`tasks/list` is removed outright, and the old blocking `tasks/result` (wait
until a long-running task finishes, then get the result in one call) is
replaced by polling: `tasks/get` to check status, `tasks/update` to act on
it. Tasks as a whole also moves out of core protocol capabilities into the
`io.modelcontextprotocol/tasks` extension, so a server needs to declare it
there (see [recipe 16](16-extensions-map.md) for the `extensions` map
mechanics) rather than assuming it's always available.

## Before

TODO: a handler for `GetTaskPayloadRequest`/blocking `tasks/result`, plus any
`tasks/list` implementation.

## After

TODO: the same functionality via `tasks/get` + `tasks/update` polling, with
`io.modelcontextprotocol/tasks` declared under `extensions`.

## Gotchas

TODO: what does a client-side polling loop look like against this, and what
polling interval/backoff is reasonable? This is also a good spot to note
the double-reporting relationship, if any, with R018's Multi Round-Trip
Requests -- both concern long-running/deferred work, but via different
mechanisms.

## Spec link

https://modelcontextprotocol.io/specification/2026-07-28/changelog
