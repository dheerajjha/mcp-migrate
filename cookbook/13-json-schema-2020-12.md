<!-- STUB: rule/spec filled in, before/after/gotchas still needed. See
     .github/GOOD_FIRST_ISSUES.md for the ready-to-file issue for this one. -->

# JSON Schema 2020-12 required for `inputSchema`/`outputSchema`

- **Rule:** [R021](../src/mcp_migrate/rules/r021_json_schema_2020_12_required.py)
- **Fixer:** none
- **Severity:** advisory
- **Spec:** SEP-2106 -- https://modelcontextprotocol.io/specification/2026-07-28/changelog

## What broke

Implementations must support at least JSON Schema 2020-12 for
`inputSchema`/`outputSchema`. Most servers (FastMCP included) generate these
schemas automatically and never pin a `$schema` dialect at all, so this is
`advisory`, not `breaking` -- the rule only fires on an *explicit* reference
to an older draft (`draft-07`, `2019-09`, etc.), which is real, rare
evidence that this project pins a dialect the new spec doesn't guarantee
support for.

## Before

TODO: a tool `inputSchema` with an explicit `"$schema":
"http://json-schema.org/draft-07/schema#"` (or a validator configured to
require draft-07/2019-09).

## After

TODO: the same schema on 2020-12, or the explicit pin dropped entirely so a
modern validator's default applies.

## Gotchas

TODO: are there real validator libraries where dropping the `$schema` pin
changes behavior in a way worth calling out (stricter/looser validation
between drafts)?

## Spec link

https://modelcontextprotocol.io/specification/2026-07-28/changelog
