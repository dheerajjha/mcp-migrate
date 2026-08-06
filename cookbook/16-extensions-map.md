# `extensions` map on `ServerCapabilities`

- **Rule:** [R005](../src/mcp_migrate/rules/r005_extensions.py)
- **Fixer:** [R005](../src/mcp_migrate/fixers/r005_extensions.py), `safe`
  confidence -- adds `extensions={}` to a `ServerCapabilities(...)` call
  that doesn't already have one; this is a pure no-op at runtime since an
  absent value already meant "no extensions."
- **Severity:** advisory
- **Spec:** "extensions field on ServerCapabilities" -- https://modelcontextprotocol.io/specification/draft/changelog

## What broke

Optional capabilities now negotiate through an `extensions` map on
`ServerCapabilities` rather than being assumed absent. Declaring
capabilities without it doesn't break anything today -- a 2026-07-28 client
just sees no extensions and moves on -- but it also tells the client
nothing about which 2026-07-28-era extensions (like
`io.modelcontextprotocol/tasks`, see [recipe 11](11-tasks-polling.md)) this
server does or doesn't support.

## Before

```python
from mcp.server import Server
from mcp.types import ServerCapabilities, ToolsCapability

server = Server("notes-server")

capabilities = ServerCapabilities(
    tools=ToolsCapability(list_changed=True),
)
```

## After

The no-op case -- the server doesn't implement any 2026-07-28 extension, but
says so explicitly rather than leaving the client to guess:

```python
from mcp.server import Server
from mcp.types import ServerCapabilities, ToolsCapability

server = Server("notes-server")

capabilities = ServerCapabilities(
    tools=ToolsCapability(list_changed=True),
    extensions={},
)
```

This is exactly what `mcp-migrate fix` produces -- the fixer only ever adds
`extensions={}` to an existing construction, at `safe` confidence, because
an absent value already meant "no extensions" and this makes that explicit
without changing behavior.

The other case -- a server that *does* implement one, such as
[Tasks](11-tasks-polling.md) after moving out of core capabilities:

```python
capabilities = ServerCapabilities(
    tools=ToolsCapability(list_changed=True),
    extensions={"io.modelcontextprotocol/tasks": {}},
)
```

The R005 fixer never produces this form on its own -- populating an
extension with real config, rather than an empty placeholder, is a
decision about what the server actually supports, not a mechanical edit.
[R019's fixer](../src/mcp_migrate/fixers/r019_tasks_polling.py) reflects
the same limit from the other direction: it comments out the removed
`tasks/list`/blocking `tasks/result` call sites and leaves a TODO pointing
at this recipe, at `review` confidence, rather than guessing at the
`extensions={"io.modelcontextprotocol/tasks": {}}` declaration itself --
that part still needs a human.

## Gotchas

- The rule (R005) only fires when it sees an actual `ServerCapabilities(...)`
  call missing `extensions` -- it will not tell you *which* extensions to
  add, only that the map itself is absent. Adding `extensions={}` silences
  the finding whether or not the server should really be declaring
  something under it.
- If your project declares capabilities in more than one place (a `factory`
  function, a test helper, a real server construction), the rule checks
  each file that references `ServerCapabilities` independently -- fixing
  one call site does not silence a separate one in another file.
- An empty `extensions={}` and no `extensions` key at all mean the same
  thing to a 2026-07-28 client today. The value of adding it now is
  forward compatibility: it tells a reader (and eventually a stricter
  client) that this server has been reviewed against the current spec, not
  that it predates it.

## Spec link

https://modelcontextprotocol.io/specification/draft/changelog
