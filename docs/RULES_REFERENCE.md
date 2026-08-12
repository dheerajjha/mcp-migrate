# Rule Reference

Every rule shipped by `mcp-migrate`, with its severity, what the 2026-07-28
spec change breaks, and whether a fixer exists. Run `mcp-migrate rules` for
the exact list of your installed version and `mcp-migrate fixers` for the
fixer confidence table.

## The 21 rules

| Rule | Severity | What breaks | Fixer |
| ---- | -------- | ------------ | ----- |
| [R001](https://github.com/dheerajjha/mcp-migrate/blob/main/src/mcp_migrate/rules/r001_session_id_removed.py) | breaking | `Mcp-Session-Id` is gone from the Streamable HTTP transport ([SEP-2567](https://github.com/modelcontextprotocol/modelcontextprotocol/pull/2567)). | yes (`review`) |
| [R002](https://github.com/dheerajjha/mcp-migrate/blob/main/src/mcp_migrate/rules/r002_connection_state.py) | breaking | Servers are required to be stateless ([SEP-2567](https://github.com/modelcontextprotocol/modelcontextprotocol/pull/2567)); a module-level dict keyed by connection breaks behind a load balancer or a restart. | yes (`review`) |
| [R003](https://github.com/dheerajjha/mcp-migrate/blob/main/src/mcp_migrate/rules/r003_routing_headers.py) | advisory | Hand-rolled HTTP clients that skip the new required `Mcp-Method`/`Mcp-Name` [routing headers](https://modelcontextprotocol.io/specification/2026-07-28/basic/transports/streamable-http) get rejected by anything enforcing the new transport. | yes (`review`) |
| [R004](https://github.com/dheerajjha/mcp-migrate/blob/main/src/mcp_migrate/rules/r004_tool_ordering.py) | advisory | [`tools/list` order](https://modelcontextprotocol.io/specification/draft/changelog) is not guaranteed; non-deterministic ordering defeats caching. | yes (`safe`) |
| [R005](https://github.com/dheerajjha/mcp-migrate/blob/main/src/mcp_migrate/rules/r005_extensions.py) | advisory | Optional capabilities negotiate through an [`extensions`](https://modelcontextprotocol.io/specification/draft/changelog) map that isn't declared. | yes (`safe`) |
| [R006](https://github.com/dheerajjha/mcp-migrate/blob/main/src/mcp_migrate/rules/r006_sse_transport_deprecated.py) | deprecated | [HTTP+SSE](https://modelcontextprotocol.io/specification/draft/changelog) is deprecated in favor of Streamable HTTP; stays in the spec 12+ months, then leaves. | yes (`review`) |
| [R007](https://github.com/dheerajjha/mcp-migrate/blob/main/src/mcp_migrate/rules/r007_deprecated_features.py) | deprecated | [Roots, Sampling and Logging](https://modelcontextprotocol.io/specification/draft/changelog) are deprecated as core capabilities. | yes (`review`) |
| [R008](https://github.com/dheerajjha/mcp-migrate/blob/main/src/mcp_migrate/rules/r008_trace_context.py) | advisory | Trace context (`traceparent`, `tracestate`, `baggage`) now travels in `_meta` ([SEP-414](https://github.com/modelcontextprotocol/modelcontextprotocol/pull/414)); OpenTelemetry breaks at your server if it's never read. | yes (`review`) |
| [R009](https://github.com/dheerajjha/mcp-migrate/blob/main/src/mcp_migrate/rules/r009_initialize_handshake_removed.py) | breaking | The `initialize`/`notifications/initialized` handshake ([SEP-2575](https://modelcontextprotocol.io/specification/2026-07-28/changelog)) is gone; a server still implementing it never becomes usable to a 2026-07-28 client. | yes (`review`) |
| [R010](https://github.com/dheerajjha/mcp-migrate/blob/main/src/mcp_migrate/rules/r010_server_discover_missing.py) | advisory | Servers must implement [`server/discover`](https://modelcontextprotocol.io/specification/2026-07-28/changelog) ([SEP-2575](https://modelcontextprotocol.io/specification/2026-07-28/changelog)); registering handlers without it leaves clients with no way to learn what you support. | no |
| [R011](https://github.com/dheerajjha/mcp-migrate/blob/main/src/mcp_migrate/rules/r011_ping_removed.py) | breaking | `ping` ([SEP-2575](https://modelcontextprotocol.io/specification/2026-07-28/changelog)) is removed from the protocol; liveness rides on the transport now. | yes (`review`) |
| [R012](https://github.com/dheerajjha/mcp-migrate/blob/main/src/mcp_migrate/rules/r012_logging_set_level_removed.py) | breaking | `logging/setLevel` ([SEP-2575](https://modelcontextprotocol.io/specification/2026-07-28/changelog)) is removed; log level is per-request via `_meta` now. | yes (`review`) |
| [R013](https://github.com/dheerajjha/mcp-migrate/blob/main/src/mcp_migrate/rules/r013_subscriptions_replaced.py) | breaking | `resources/subscribe`/`resources/unsubscribe` ([SEP-2575](https://modelcontextprotocol.io/specification/2026-07-28/changelog)) are replaced by `subscriptions/listen`. | yes (`review`) |
| [R014](https://github.com/dheerajjha/mcp-migrate/blob/main/src/mcp_migrate/rules/r014_sse_resumability_removed.py) | breaking | SSE resumability via `Last-Event-ID` ([SEP-2575](https://modelcontextprotocol.io/specification/2026-07-28/changelog)) is removed; a dropped connection is just dropped now. | yes (`review`) |
| [R015](https://github.com/dheerajjha/mcp-migrate/blob/main/src/mcp_migrate/rules/r015_result_type_required.py) | advisory | Every result now requires `resultType` ([SEP-2322](https://modelcontextprotocol.io/specification/2026-07-28/changelog)). Fires only on servers that build their own JSON-RPC envelopes. | no |
| [R016](https://github.com/dheerajjha/mcp-migrate/blob/main/src/mcp_migrate/rules/r016_cacheable_result_required.py) | advisory | List/read results require `ttlMs`/`cacheScope` ([SEP-2549](https://modelcontextprotocol.io/specification/2026-07-28/changelog)). Advisory: nothing has adopted the new API yet. | yes (`review`) |
| [R017](https://github.com/dheerajjha/mcp-migrate/blob/main/src/mcp_migrate/rules/r017_resource_not_found_code_changed.py) | breaking | The resource-not-found [error code](https://modelcontextprotocol.io/specification/2026-07-28/changelog) changed from `-32002` to `-32602`. | yes (`safe`) |
| [R018](https://github.com/dheerajjha/mcp-migrate/blob/main/src/mcp_migrate/rules/r018_multi_round_trip_replaces_server_initiated.py) | breaking | Server-initiated Roots/Sampling/Elicitation ([SEP-2322](https://modelcontextprotocol.io/specification/2026-07-28/changelog)) are replaced by Multi Round-Trip Requests (`InputRequiredResult` + `inputResponses`). | yes (`review`) |
| [R019](https://github.com/dheerajjha/mcp-migrate/blob/main/src/mcp_migrate/rules/r019_tasks_polling_replaces_blocking_result.py) | breaking | `tasks/list` is removed and blocking `tasks/result` ([SEP-2663](https://modelcontextprotocol.io/specification/2026-07-28/changelog)) is replaced by polling; Tasks moves to an extension. | yes (`review`) |
| [R020](https://github.com/dheerajjha/mcp-migrate/blob/main/src/mcp_migrate/rules/r020_dynamic_client_registration_deprecated.py) | deprecated | RFC 7591 [Dynamic Client Registration](https://modelcontextprotocol.io/specification/2026-07-28/changelog) is deprecated in favor of Client ID Metadata Documents. | yes (`review`) |
| [R021](https://github.com/dheerajjha/mcp-migrate/blob/main/src/mcp_migrate/rules/r021_json_schema_2020_12_required.py) | advisory | Implementations must support at least [JSON Schema 2020-12](https://modelcontextprotocol.io/specification/2026-07-28/changelog) ([SEP-2106](https://modelcontextprotocol.io/specification/2026-07-28/changelog)) for `inputSchema`/`outputSchema`. | yes (`safe`) |

Only 19 of the 21 rules ship a fixer (R010 and R015 do not).

## The grade

Every finding costs points, but no single rule can sink a grade by itself:
each rule's contribution is capped no matter how many times it fires.

| Severity     | Cost per finding | Cap per rule |
| ------------ | ----------------- | ------------ |
| `breaking`   | -25                | -25           |
| `deprecated` | -8                 | -12           |
| `advisory`   | -3                 | -6            |

Score starts at 100 and floors at 0. The letter grade:

| Score  | Grade |
| ------ | ----- |
| 95-100 | A     |
| 80-94  | B     |
| 60-79  | C     |
| 40-59  | D     |
| 0-39   | F     |

**The letter counts kinds of problem, not amount of work.** Because every
rule is capped, one `Mcp-Session-Id` read and fourteen of them across four
files both score 75 and both grade C. The score moves when a *different*
rule fires, not when the same one fires again. To size a migration, read
`counts` and `findings` in `--json` — they carry every occurrence, uncapped.