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

```python
class MyAuthProvider(OAuthAuthorizationServerProvider):
    async def register_client(self, metadata: ClientMetadata) -> RegisteredClient:
        client_id = generate_client_id()
        self._clients[client_id] = metadata
        return RegisteredClient(client_id=client_id, **metadata.dict())
```

## After

```python
class MyAuthProvider(OAuthAuthorizationServerProvider):
    async def resolve_client(self, client_id: str) -> ClientMetadata:
        # client_id is now a URL the client controls; fetch and validate
        # its metadata document instead of looking up a prior registration.
        metadata = await fetch_client_metadata_document(client_id)
        return metadata
```

## Gotchas

- **The client_id itself changes shape.** Under DCR, `client_id` is an
  opaque identifier the authorization server minted at registration time.
  Under CIMD, the client presents a URL as its `client_id`, and the
  authorization server fetches a metadata document from that URL to learn
  the client's redirect URIs, name, and other registration fields --
  there's no prior "register" call to remove, just a different source of
  truth for the same metadata.
- **This removes a stateful registration step, which simplifies deployment
  at the cost of trust assumptions.** DCR let you gate which clients could
  register (rate limiting, admin approval); with CIMD, any client
  presenting a resolvable URL can connect, so if your DCR implementation
  did access control at registration time, that control point has to move
  elsewhere (e.g. validating the resolved metadata against an allowlist of
  known-good URLs, rather than an admission check on the register call).
- **No fixer exists because there's no mechanical translation.** Swapping
  method names doesn't change the fact that CIMD needs a document-fetching
  code path DCR never had -- this is closer to an architecture change on
  the auth provider than a rename.
- **Check what your OAuth/auth SDK actually supports before migrating.**
  CIMD is newer than RFC 7591; if the library backing your
  `OAuthAuthorizationServerProvider` doesn't yet expose a document-fetch
  hook, you may be waiting on an upstream SDK release rather than writing
  application code.

## Spec link

https://modelcontextprotocol.io/specification/2026-07-28/changelog
