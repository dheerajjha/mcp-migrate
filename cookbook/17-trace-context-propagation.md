<!-- STUB: rule/spec filled in, before/after/gotchas still needed. See
     .github/GOOD_FIRST_ISSUES.md for the ready-to-file issue for this one. -->

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

TODO: a handler that creates/continues an OpenTelemetry span without
reading `traceparent`/`tracestate`/`baggage` from `_meta`.

## After

TODO: the same handler extracting trace context from `_meta` and handing it
to the tracer (e.g. via `opentelemetry.propagate.extract`).

## Gotchas

TODO: what does this look like concretely with the OpenTelemetry Python
SDK's `TraceContextTextMapPropagator`? A real worked example using that
API is the single highest-value thing this recipe is missing.

## Spec link

https://github.com/modelcontextprotocol/modelcontextprotocol/pull/414
