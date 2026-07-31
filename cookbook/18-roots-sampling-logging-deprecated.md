<!-- STUB: rule/spec filled in, before/after/gotchas still needed. See
     .github/GOOD_FIRST_ISSUES.md for the ready-to-file issue for this one. -->

# Roots, Sampling and Logging deprecated as core capabilities

- **Rule:** [R007](../src/mcp_migrate/rules/r007_deprecated_features.py)
  (deprecated -- reports the same code as [R018](../src/mcp_migrate/rules/r018_multi_round_trip_replaces_server_initiated.py)'s
  `breaking` finding for Sampling/elicitation specifically; both firing on
  the same line is expected, not a bug)
- **Fixer:** none
- **Severity:** deprecated
- **Spec:** "Roots, Sampling and Logging deprecated" -- https://modelcontextprotocol.io/specification/draft/changelog

## What broke

Roots, Sampling and Logging are deprecated as core capabilities -- on the
same 12+ month clock as HTTP+SSE ([recipe 03](03-sse-to-streamable-http.md)).
Nothing stops working today. Roots' replacement is resource URIs; Sampling's
server-initiated form is superseded now by Multi Round-Trip Requests (see
[recipe 10](10-multi-round-trip-requests.md), which covers the `breaking`
half of this same change); Logging is moving to an extension entirely.

## Before

TODO: a server declaring/using `RootsCapability` and reading `roots/list`,
to show the "still works today, deprecated" framing distinct from R018's
"this exact call shape is also breaking" framing.

## After

TODO: the same functionality via resource URIs instead of Roots.

## Gotchas

TODO: this recipe is the natural place to explain the R007/R018
relationship in full -- when a reader sees both fire on the same file, what
should they actually do first (the breaking one, obviously, but worth
saying so plainly with an example).

## Spec link

https://modelcontextprotocol.io/specification/draft/changelog
