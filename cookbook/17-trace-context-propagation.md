# Trace context now travels in `_meta`

- **Rule:** [R008](../src/mcp_migrate/rules/r008_trace_context.py)
- **Fixer:** none
- **Severity:** advisory
- **Spec:** SEP-414 -- https://github.com/modelcontextprotocol/modelcontextprotocol/pull/414

## What broke

`traceparent`, `tracestate` and `baggage` -- the W3C Trace Context headers
OpenTelemetry uses to propagate a distributed trace across process
boundaries -- now travel in the MCP request's `_meta` object instead of
wherever a server might previously have improvised (a custom header, an
argument, nothing at all). A server that uses OpenTelemetry internally but
never reads `traceparent` off `_meta` breaks distributed tracing at exactly
this hop: spans on either side of this server exist, but nothing links
them, because the trace ID never crossed.

This rule only fires when the project already imports `opentelemetry` --
projects with no tracing story at all have nothing to propagate and aren't
flagged.

## Before

```python
from opentelemetry import trace

tracer = trace.get_tracer(__name__)

async def handle_tool_call(name: str, args: dict) -> dict:
    with tracer.start_as_current_span(f"tool.{name}"):
        return await dispatch(name, args)
```

The span above is a brand new root span every time -- it never learns about
the trace the client started, so it shows up disconnected in whatever
backend collects these traces.

## After

```python
from opentelemetry import trace
from opentelemetry.propagate import extract

tracer = trace.get_tracer(__name__)

async def handle_tool_call(name: str, args: dict, meta: dict) -> dict:
    ctx = extract(meta)
    with tracer.start_as_current_span(f"tool.{name}", context=ctx):
        return await dispatch(name, args)
```

`opentelemetry.propagate.extract` is the standard entry point --
`TraceContextTextMapPropagator` is registered as the default propagator in
most OTel SDK setups, so `extract()` reads `traceparent`/`tracestate` out of
`meta` (a dict-like carrier) the same way it would read HTTP headers in a
web framework integration, and hands back a `Context` that
`start_as_current_span` continues instead of starting fresh.

## Gotchas

- **`extract()` expects a plain mapping of header-name to string value.**
  If `_meta` is a nested structure or your MCP SDK exposes it as something
  other than a flat dict, you may need to project `traceparent`/`tracestate`
  (and `baggage`, if you use it) out into a plain dict before calling
  `extract()` -- passing the raw `_meta` object through unchanged only
  works if it already looks like that.
- **This rule can't see propagation done through the OTel API instead of by
  name.** The TypeScript side of R008 explicitly treats a
  `propagation.extract(...)` call as evidence tracing is wired up
  correctly, even if `traceparent` never appears as a literal string
  anywhere -- the Python side doesn't have that same allowance yet, so a
  Python server calling `extract()` on a variable instead of a dict keyed
  by the literal string `traceparent` could still show up as a false
  positive. Worth checking manually before assuming the finding means
  nothing is wired up.
- **No fixer exists because this needs the tracer variable in scope.** The
  fix isn't a rename or a deletion, it's threading `meta`/`_meta` through
  to wherever the span starts -- something a mechanical fixer can't do
  without risking passing the wrong object.

## Spec link

https://github.com/modelcontextprotocol/modelcontextprotocol/pull/414
