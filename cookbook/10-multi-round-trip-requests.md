<!-- STUB: rule/spec filled in, before/after/gotchas still needed. See
     .github/GOOD_FIRST_ISSUES.md for the ready-to-file issue for this one. -->

# Multi Round-Trip Requests replace server-initiated roots/sampling/elicitation

- **Rule:** [R018](../src/mcp_migrate/rules/r018_multi_round_trip_replaces_server_initiated.py)
  (breaking -- overlaps on purpose with [R007](../src/mcp_migrate/rules/r007_deprecated_features.py),
  which reports the same code `deprecated` rather than `breaking`; see that
  rule's source for why both fire)
- **Fixer:** none
- **Severity:** breaking
- **Spec:** SEP-2322 -- https://modelcontextprotocol.io/specification/2026-07-28/changelog

## What broke

Server-initiated `roots/list`, `sampling/createMessage` and
`elicitation/create` -- along with `notifications/elicitation/complete` and
`elicitationId` -- are gone. Previously, a server that needed more
information mid-call (ask the client to pick a root, ask the user's LLM to
sample something, elicit a missing argument from the user) sent its own
request back to the client and waited for a response inline. 2026-07-28
replaces all of that with Multi Round-Trip Requests: the server returns an
`InputRequiredResult` (`resultType: "input_required"`, see
[recipe 05](05-result-type-and-cache-metadata.md)) and the *client* re-issues
the original call with `inputResponses` once it has what the server asked
for. The server never initiates a request of its own.

## Before

TODO: a tool handler that calls `create_message`/`list_roots` mid-call and
blocks on the result.

## After

TODO: the same handler restructured to return `InputRequiredResult` and a
second call path that consumes `inputResponses` on the retried call.

## Gotchas

TODO: this is the biggest control-flow change in the whole spec revision --
a synchronous "ask and block" call becomes two separate request/response
pairs correlated by the client's retry, and whatever local state the
handler needed between "asked" and "got the answer" has to survive across
that boundary somehow (it can't just sit on the stack of a blocked
coroutine anymore).

## Spec link

https://modelcontextprotocol.io/specification/2026-07-28/changelog
