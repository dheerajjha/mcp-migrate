<!--
Copy this file to cookbook/NN-slug.md (next free number, lowercase-hyphen
slug) and fill it in. Delete this comment block before opening the PR.

One recipe = one breaking (or deprecated) change from the 2026-07-28 spec
revision. If mcp-migrate already ships a rule/fixer for it, link them; if
not, that's fine -- the recipe still helps someone doing the migration by
hand. See cookbook/README.md for the full format contract.
-->

# Title: what broke, in one line

- **Rule:** R0NN (link: `src/mcp_migrate/rules/r0NN_slug.py`) -- or "none yet,
  see [issue link]" if this change has no rule
- **Fixer:** yes (`src/mcp_migrate/fixers/r0NN_slug.py`, `safe`/`review`) --
  or "none yet, see [issue link]"
- **Severity:** breaking | deprecated | advisory
- **Spec:** link to the exact spec section or SEP

## What broke

One or two paragraphs. What did the old spec let you do, what does
2026-07-28 remove or change, and why does that make the old code stop
working (not just "it's different now" -- the actual failure mode: a
rejected request, a 4xx from a proxy, a client that can never call your
server because the old handshake never completes, etc).

## Before

```python
# The pre-2026-07-28 pattern. Complete enough to run/type-check on its own,
# not a fragment -- someone should be able to see exactly what's wrong
# without guessing at surrounding context.
```

## After

```python
# The fixed version. If mcp-migrate ships a fixer for this, this should be
# close to (or exactly) what running `mcp-migrate fix --write` produces --
# say so if it differs and why (e.g. the fixer only does the mechanical
# part and a human still has to fill in one piece).
```

## Gotchas

- Anything a mechanical find/replace gets wrong.
- Edge cases that look fixed but aren't (e.g. a second call site the regex
  doesn't reach).
- Anything that depends on which SDK/version the server is on.

## Spec link

https://modelcontextprotocol.io/specification/2026-07-28/changelog (swap for
the precise section/SEP anchor if there is one)
