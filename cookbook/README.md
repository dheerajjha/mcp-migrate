# Cookbook

One markdown file per breaking (or deprecated) change in the 2026-07-28 spec
revision. This is the cheapest way to contribute to this project: no Python,
no tests, no fixture files -- just a worked before/after example and the
gotchas you hit doing it for real.

`mcp-migrate check` and `mcp-migrate fix` tell you *that* something broke and,
for five rules, fix the mechanical part automatically. The cookbook is where
the *rest* of the migration lives -- the part a regex can't do because it
requires a judgment call (what do you name the new handle argument? where
does the durable store live? what does your `server/discover` response say
about your own server's identity?).

## Format

Every recipe follows [`_TEMPLATE.md`](_TEMPLATE.md):

- **Rule / Fixer** -- which `RNNN` this corresponds to (if any), and whether
  a fixer exists for it. Not every recipe needs a rule; a recipe can exist
  for a change that's real but too fuzzy to detect mechanically.
- **What broke** -- the actual failure mode, not just "it's different now".
- **Before / After** -- complete, runnable-looking Python, not a fragment.
- **Gotchas** -- what a mechanical fix gets wrong, or the edge cases that
  look done but aren't.
- **Spec link** -- the exact section or SEP, not just the changelog root.

## Filed so far

| # | Recipe | Rule(s) | Fixer |
| - | ------ | ------- | ----- |
| 01 | [Sessions to explicit handles](01-sessions-to-explicit-handles.md) | R001, R002 | R001 (review) |
| 02 | [initialize/initialized to server/discover](02-initialize-to-server-discover.md) | R009, R010 | none |
| 03 | [HTTP+SSE to Streamable HTTP](03-sse-to-streamable-http.md) | R006 | R006 (review) |
| 04 | [subscribe/unsubscribe to subscriptions/listen](04-subscribe-to-subscriptions-listen.md) | R013 | none |
| 05 | [resultType and cache metadata on results](05-result-type-and-cache-metadata.md) | R015, R016 | none |
| 14 | [Required Mcp-Method / Mcp-Name routing headers](14-routing-headers.md) | R003 | none |

## Stubs -- open slots

These exist as placeholders with the rule, spec link, and a one-line pointer
already filled in, so picking one up means writing the before/after and
gotchas, not starting from a blank page. See
[`.github/GOOD_FIRST_ISSUES.md`](../.github/GOOD_FIRST_ISSUES.md) for a
ready-to-file issue for each.

| # | Recipe | Rule(s) |
| - | ------ | ------- |
| 06 | [ping removed](06-ping-removed.md) | R011 |
| 07 | [logging/setLevel removed](07-logging-set-level-removed.md) | R012 |
| 08 | [SSE resumability removed](08-sse-resumability-removed.md) | R014 |
| 09 | [resource-not-found error code changed](09-resource-not-found-error-code.md) | R017 |
| 10 | [Multi Round-Trip Requests replace server-initiated calls](10-multi-round-trip-requests.md) | R018 |
| 11 | [Tasks moved to an extension, polling replaces blocking result](11-tasks-polling.md) | R019 |
| 12 | [Dynamic Client Registration deprecated](12-dynamic-client-registration-deprecated.md) | R020 |
| 13 | [JSON Schema 2020-12 required](13-json-schema-2020-12.md) | R021 |
| 15 | [Deterministic tools/list ordering](15-deterministic-tool-ordering.md) | R004 |
| 16 | [extensions map on ServerCapabilities](16-extensions-map.md) | R005 |
| 17 | [Trace context propagation from _meta](17-trace-context-propagation.md) | R008 |
| 18 | [Roots / Sampling / Logging deprecated as core capabilities](18-roots-sampling-logging-deprecated.md) | R007 |

## Adding one

```bash
cp cookbook/_TEMPLATE.md cookbook/NN-your-slug.md
```

Fill it in, add a row to whichever table above it belongs in (moving it out
of "Stubs" if you're finishing one of those), open a PR. See
[CONTRIBUTING.md](../CONTRIBUTING.md#add-a-cookbook-recipe-5-minutes) --
reviewed within 48 hours, and a recipe that follows the template merges
without back-and-forth.
