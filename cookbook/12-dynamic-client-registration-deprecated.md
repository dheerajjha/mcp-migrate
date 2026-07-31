<!-- STUB: rule/spec filled in, before/after/gotchas still needed. See
     .github/GOOD_FIRST_ISSUES.md for the ready-to-file issue for this one. -->

# Dynamic Client Registration (RFC 7591) deprecated

- **Rule:** [R020](../src/mcp_migrate/rules/r020_dynamic_client_registration_deprecated.py)
- **Fixer:** none
- **Severity:** deprecated
- **Spec:** https://modelcontextprotocol.io/specification/2026-07-28/changelog

## What broke

RFC 7591 Dynamic Client Registration -- OAuth clients self-registering with
an authorization server at connect time -- is deprecated in favor of Client
ID Metadata Documents (CIMD). Nothing stops working immediately: this is
`deprecated`, not `breaking`, same clock as HTTP+SSE
([recipe 03](03-sse-to-streamable-http.md)). A server whose auth provider
still implements `register_client` should plan the migration rather than
treat this as urgent.

## Before

TODO: an OAuth provider implementing `register_client`
(`RegisterClientRequest`) for dynamic registration.

## After

TODO: the same onboarding flow via Client ID Metadata Documents instead.

## Gotchas

TODO: what's the actual CIMD onboarding flow, concretely, for a server that
currently does DCR? This is the least-documented change in the whole
revision from a "here's exactly what to do instead" perspective -- a good
recipe here should link to whatever CIMD spec/RFC exists and spell out the
document shape.

## Spec link

https://modelcontextprotocol.io/specification/2026-07-28/changelog
