# Deterministic `tools/list` ordering

- **Rule:** [R004](../src/mcp_migrate/rules/r004_tool_ordering.py)
- **Fixer:** [R004](../src/mcp_migrate/fixers/r004_tool_ordering.py), `safe`
  confidence -- but only for the one unambiguous shape (a `return [...]`
  literal of all `Tool(...)` calls or all plain literals). Anything built up
  across several statements is left alone.
- **Severity:** advisory
- **Spec:** "Deterministic tool ordering" (SHOULD) -- https://modelcontextprotocol.io/specification/draft/changelog

## What broke

Nothing breaks a connection here -- this is advisory, the lowest-stakes
severity. But `tools/list` order was never guaranteed, and returning tools
in whatever order they happen to be defined (insertion order, dict
iteration order, historical "when we shipped it" order) defeats client-side
caching and hurts LLM prompt-cache hit rates: if the list looks different
on every call, nothing downstream can treat it as stable.

## Before

The fixer handles the unambiguous case -- a bare list literal:

```python
def list_tools():
    return [Tool(name="search"), Tool(name="add"), Tool(name="delete")]
```

But a handler that builds the list up across statements is a shape the
fixer deliberately leaves alone, since it can't prove the result is a plain
list of `Tool(...)` calls without tracing where `tools` came from:

```python
def list_tools():
    tools = list(_registry.values())
    if feature_flags.beta_enabled():
        tools.append(_beta_tool())
    return tools
```

## After

The literal case, after `mcp-migrate fix --write`:

```python
def list_tools():
    return sorted([Tool(name="search"), Tool(name="add"), Tool(name="delete")], key=lambda t: t.name)
```

The registry-based case needs the sort added by hand at the return site,
since the fixer won't touch it:

```python
def list_tools():
    tools = list(_registry.values())
    if feature_flags.beta_enabled():
        tools.append(_beta_tool())
    return sorted(tools, key=lambda t: t.name)
```

## Gotchas

- **"Sort alphabetically" isn't always the right call.** If your tool list
  has intentional grouping or ordering for UX reasons (e.g. the most
  commonly used tool listed first, or tools grouped by category), a blind
  `sorted(key=lambda t: t.name)` throws that away. The point isn't
  alphabetical specifically, it's *deterministic* -- pick whatever stable
  key preserves your intended grouping if you have one, rather than
  reaching for the fixer's default.
- **The fixer only fires on one exact shape for a reason.** `return
  [Tool(...), Tool(...)]` directly in the handler body is safe to wrap in
  `sorted()` because we can see every element. A `tools` variable populated
  by a registry, a database query, or conditional `.append()` calls could
  be anything by the time it reaches `return` -- guessing a sort key there
  risks a `safe`-confidence fixer silently changing behavior it can't
  verify, which is exactly what this project's fixers are built to avoid.
- **Tools without a natural sort key (no `.name`, or a dict-shaped tool
  spec) need a different key entirely.** `key=lambda t: t["name"]` for
  dict-shaped tools, or falling back to whatever unique field you do have
  -- the fixer's `Tool(...).name` assumption doesn't generalize past the
  SDK's own model class.
- **The rule itself stays silent when the sort lives one function away.**
  A handler that returns `{"tools": alphabetize(registry)}` isn't scanned
  any further -- `alphabetize` might sort, might not, and resolving it
  would mean following a call graph instead of scanning lines ([#91](https://github.com/dheerajjha/mcp-migrate/issues/91)).
  Extracting the sort into a helper is legitimate code; the rule would
  rather miss that case than wrongly accuse it of not sorting.

## Spec link

https://modelcontextprotocol.io/specification/draft/changelog
