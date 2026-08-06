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

```python
TOOL_SCHEMA = {
    "$schema": "http://json-schema.org/draft-07/schema#",
    "type": "object",
    "properties": {"query": {"type": "string"}},
    "required": ["query"],
}
```

## After

```python
TOOL_SCHEMA = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "type": "object",
    "properties": {"query": {"type": "string"}},
    "required": ["query"],
}
```

Or just drop the `$schema` key entirely and let whatever validator you use
apply its own current default -- for most projects that's the simpler fix,
since the pin usually wasn't load-bearing in the first place.

## Gotchas

- **Don't add a `$schema` pin where there wasn't one, just to "fix" this.**
  The rule is positive-evidence only: an unpinned schema never fires,
  because the overwhelming majority of MCP servers don't pin a dialect at
  all and that's fine. Adding `"$schema": "https://json-schema.org/draft/2020-12/schema"`
  to a schema that never had one doesn't improve compliance, it just adds a
  line.
- **draft-07 and 2020-12 aren't purely additive -- some keyword behavior
  changed.** `items` as an array (tuple validation) moved to `prefixItems`
  in 2019-09+; if your schema uses the older array-`items` form and you
  bump the `$schema` pin without touching the schema body, a strict
  2020-12 validator may interpret it differently than a draft-07 one did.
  Bumping the pin and re-validating a representative payload is worth doing
  together, not as two separate steps.
- **This only checks the pin, not actual validator behavior.** A project
  can genuinely validate against 2020-12 semantics while never writing the
  literal string `"2020-12"` anywhere (again, the common case) -- R021
  can't detect that either way, which is exactly why it only flags the
  rarer, unambiguous case of an explicit older-draft reference.

## Spec link

https://modelcontextprotocol.io/specification/2026-07-28/changelog
