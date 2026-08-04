# mcp-migrate

![Scattered, unsorted source blocks on the left resolving through a scan into an ordered, graded grid on the right](docs/banner.jpg)

`mcp-migrate` finds and fixes what the MCP 2026-07-28 spec revision breaks in
your server: protocol sessions and `Mcp-Session-Id` removed, `initialize` /
`notifications/initialized` replaced by `server/discover`, `ping` and
`logging/setLevel` gone, `resources/subscribe` replaced by
`subscriptions/listen`, required `resultType` and cache metadata on results,
server-initiated Sampling/Roots/Elicitation replaced by Multi Round-Trip
Requests, and more. The official Python SDK ships no codemod for any of
this -- only a manual migration guide. The TypeScript codemod only handles
the v1→v2 package rename, not the protocol changes. `mcp-migrate fix` is the
only thing that edits your server's code for you.

```bash
uvx mcp-migrate check .
uvx mcp-migrate fix . --write
```

## `mcp-migrate check`

```
$ uvx mcp-migrate check tests/fixtures/fixer_roundtrip

mcp-migrate v0.1.2  ->  fixer_roundtrip
2 Python files, 21 rules, spec 2026-07-28

            rule    where         what
breaking    R001    server.py:28  Mcp-Session-Id was removed from the Streamable HTTP transport.
breaking    R001    server.py:29  Mcp-Session-Id was removed from the Streamable HTTP transport.
breaking    R017    errors.py:8   -32002 for resource-not-found is the old code; 2026-07-28 uses -32602.
deprecated  R006    server.py:15  HTTP+SSE transport is deprecated.
deprecated  R006    server.py:24  HTTP+SSE transport is deprecated.
advisory    R004    server.py:32  Tools are returned without an explicit sort.
advisory    R005    server.py:16  Capabilities are declared but `extensions` is absent.
advisory    R010    (project)     This project registers MCP request handlers (tools/resources/prompts)
                                  but has no server/discover implementation anywhere in the project.
advisory    R016    server.py:32  This file implements a list/read handler but neither `ttlMs` nor
                                  `cacheScope` appears in it.

  R001  Uses Mcp-Session-Id, which no longer exists
  SEP-2567 https://github.com/modelcontextprotocol/modelcontextprotocol/pull/2567
  Sessions are gone from the transport. Mint an explicit handle server-side and take it as an
  ordinary tool argument instead.

  [... one block like this per rule that fired ...]

Grade F (26/100)  3 breaking, 2 deprecated, 4 advisory

Add your server to the board:  mcp-migrate entry --repo owner/name
```

Zero findings prints `Grade A` and a ready-to-paste badge instead. Add
`--json` for machine-readable, uncapped output (the terminal table caps each
rule at 5 rows with a "+N more" line so it stays readable; JSON always has
every finding).

Exit codes, so it drops straight into CI:

| code | meaning |
| ---- | ------- |
| `0`  | checked it, nothing `breaking` |
| `1`  | checked it, found something `breaking` |
| `2`  | **could not check it** — no readable source in a supported language |

The third one matters. **mcp-migrate only reads Python today.** Point it at a
TypeScript server and it refuses, with no grade and no badge:

```
$ mcp-migrate check ./my-ts-server

mcp-migrate v0.1.2  ->  my-ts-server

Nothing scannable here. Found 24 TypeScript, 3 JavaScript, but no Python --
and mcp-migrate only reads Python today.
TypeScript support is the most-wanted thing in this repo and it is up for
grabs: https://github.com/dheerajjha/mcp-migrate/issues/30
No grade and no badge: this tool has no opinion about code it could not read.
```

An empty finding set means "we read it and it's clean" *or* "we read
nothing", and a grade that can't tell those apart is worthless. So a tree
with nothing readable in it gets silence instead of an A — see
[issue #30](https://github.com/dheerajjha/mcp-migrate/issues/30) if you want
to make TypeScript work.

By default, `check` skips test code: anything under a `tests/`, `test/`,
`testing/`, `fixtures/`, `examples/`, or `docs/` directory, plus `test_*.py`,
`*_test.py`, and `conftest.py` files. A backward-compat test that
deliberately exercises a deprecated transport, or an integration test that
posts a literal `{"method": "tools/list"}` payload, is evidence your project
is well tested -- not evidence the server itself is broken. Pass
`--include-tests` to scan those paths too.

## `mcp-migrate fix`

```
$ uvx mcp-migrate fix tests/fixtures/fixer_roundtrip

errors.py
--- a/errors.py
+++ b/errors.py
@@ -5,7 +5,7 @@
 
 def read_resource(handle: str) -> dict:
     if not _exists(handle):
-        return {"code": -32002, "message": "resource not found"}
+        return {"code": -32602, "message": "resource not found"}
     return {"contents": _load(handle)}
 
 
  [R017/safe] line 8: resource-not-found error code -32002 -> -32602

server.py
--- a/server.py
+++ b/server.py
@@ -12,26 +12,29 @@
 from __future__ import annotations
 
 from mcp.server import Server
-from mcp.server.sse import SseServerTransport
+from mcp.server.streamable_http import StreamableHTTPServerTransport
 from mcp.types import ServerCapabilities, Tool, ToolsCapability
 
 server = Server("fixture-server")
 
 capabilities = ServerCapabilities(
     tools=ToolsCapability(list_changed=True),
+    extensions={},
 )
 
-transport = SseServerTransport("/messages")
+# TODO(mcp-migrate): verify no constructor args were lost moving off SSE, see https://modelcontextprotocol.io/specification/draft/changelog
+transport = StreamableHTTPServerTransport()
 
 
 def _session_for(request):
-    mcp_session_id = request.headers.get("Mcp-Session-Id")
+    # TODO(mcp-migrate): replaced by an explicit handle argument, see https://github.com/modelcontextprotocol/modelcontextprotocol/pull/2567
+    # mcp_session_id = request.headers.get("Mcp-Session-Id")
     return mcp_session_id
 
 
 @server.list_tools()
 async def list_tools() -> list[Tool]:
-    return [
+    return sorted([
         Tool(name="zeta", description="Last alphabetically."),
         Tool(name="alpha", description="First alphabetically."),
-    ]
+    ], key=lambda t: t.name)
  [R001/review] line 28: commented out Mcp-Session-Id header access, added TODO
  [R004/safe] line 35: wrapped returned tool list in sorted(key=lambda t: t.name)
  [R005/safe] line 20: added extensions={} to ServerCapabilities(...)
  [R006/review] line 15: import Streamable HTTP transport instead of SSE
  [R006/review] line 25: SseServerTransport(...) -> StreamableHTTPServerTransport(), flagged for review

2 file(s), 6 change(s): 3 safe, 3 flagged for human review
4 finding(s) still need a human after this fix -- run `mcp-migrate check tests/fixtures/fixer_roundtrip` for details.
Dry run -- nothing was written. Re-run with --write to apply.
```

`fix` runs in dry-run mode by default (that's what `--dry-run` names
explicitly; it's implied when you pass neither flag) -- it prints the exact
unified diff for every file that would change and writes nothing. Pass
`--write` to apply it. `--dry-run` and `--write` are mutually exclusive.

Every change is tagged `safe` or `review` in the diff output:

- **`safe`** -- the fixer is certain the transformation can't change
  behavior (e.g. wrapping an already-unordered list literal in `sorted()`,
  or adding `extensions={}` where absent already meant "no extensions").
  Apply these with confidence.
- **`review`** -- the fixer did the mechanical part it *can* be sure of
  (renaming an import, commenting out a now-nonexistent header read) and
  left a `# TODO(mcp-migrate): ...` exactly where a human has to finish the
  job, because the rest genuinely requires a judgment call this tool can't
  make for you (what do you name the new handle argument? what constructor
  args did the old transport need that the new one doesn't take?).

Pass `--safe-only` to apply only `safe` fixers, `--rule R006` to restrict to
one rule, `--include-tests` to also fix test/fixture paths (skipped by
default, same rule as `check`). Only 5 of the 21 rules ship a fixer at all --
see the table below and [`mcp-migrate fixers`](#other-commands). Fixers are
deliberately conservative: when a fixer can't be sure a transformation is
correct, it leaves the source untouched rather than guess. A wrong fix that
silently corrupts your server is worse than reporting the finding and doing
nothing.

## Other commands

```bash
mcp-migrate rules                     # list every rule this version ships, with severity and spec ref
mcp-migrate fixers                    # list every fixer, with confidence (safe/review)
mcp-migrate entry --repo owner/name   # print a registry/servers/*.yaml entry for the board
```

## Every rule

| Rule | Severity | What breaks | Fixer |
| ---- | -------- | ------------ | ----- |
| [R001](src/mcp_migrate/rules/r001_session_id.py) | breaking | `Mcp-Session-Id` is gone from the Streamable HTTP transport ([SEP-2567](https://github.com/modelcontextprotocol/modelcontextprotocol/pull/2567)). | yes (`review`) |
| [R002](src/mcp_migrate/rules/r002_connection_state.py) | breaking | Servers are required to be stateless ([SEP-2567](https://github.com/modelcontextprotocol/modelcontextprotocol/pull/2567)); a module-level dict keyed by connection breaks behind a load balancer or a restart. | no |
| [R003](src/mcp_migrate/rules/r003_routing_headers.py) | advisory | Hand-rolled HTTP clients that skip the new required `Mcp-Method`/`Mcp-Name` [routing headers](https://modelcontextprotocol.io/specification/2026-07-28/basic/transports/streamable-http) get rejected by anything enforcing the new transport. | no |
| [R004](src/mcp_migrate/rules/r004_tool_ordering.py) | advisory | [`tools/list` order](https://modelcontextprotocol.io/specification/draft/changelog) is not guaranteed; non-deterministic ordering defeats caching. | yes (`safe`) |
| [R005](src/mcp_migrate/rules/r005_extensions.py) | advisory | Optional capabilities negotiate through an [`extensions`](https://modelcontextprotocol.io/specification/draft/changelog) map that isn't declared. | yes (`safe`) |
| [R006](src/mcp_migrate/rules/r006_sse_transport.py) | deprecated | [HTTP+SSE](https://modelcontextprotocol.io/specification/draft/changelog) is deprecated in favor of Streamable HTTP; stays in the spec 12+ months, then leaves. | yes (`review`) |
| [R007](src/mcp_migrate/rules/r007_deprecated_features.py) | deprecated | [Roots, Sampling and Logging](https://modelcontextprotocol.io/specification/draft/changelog) are deprecated as core capabilities. | no |
| [R008](src/mcp_migrate/rules/r008_trace_context.py) | advisory | Trace context (`traceparent`, `tracestate`, `baggage`) now travels in `_meta` ([SEP-414](https://github.com/modelcontextprotocol/modelcontextprotocol/pull/414)); OpenTelemetry breaks at your server if it's never read. | no |
| [R009](src/mcp_migrate/rules/r009_initialize_handshake_removed.py) | breaking | The `initialize`/`notifications/initialized` handshake ([SEP-2575](https://modelcontextprotocol.io/specification/2026-07-28/changelog)) is gone; a server still implementing it never becomes usable to a 2026-07-28 client. | no |
| [R010](src/mcp_migrate/rules/r010_server_discover_missing.py) | advisory | Servers must implement [`server/discover`](https://modelcontextprotocol.io/specification/2026-07-28/changelog) ([SEP-2575](https://modelcontextprotocol.io/specification/2026-07-28/changelog)); registering handlers without it leaves clients with no way to learn what you support. Downgraded from `breaking`: this checks for something the new spec introduced, so it fires on ~100% of pre-migration servers and has no discriminating power. | no |
| [R011](src/mcp_migrate/rules/r011_ping_removed.py) | breaking | `ping` ([SEP-2575](https://modelcontextprotocol.io/specification/2026-07-28/changelog)) is removed from the protocol; liveness rides on the transport now. | no |
| [R012](src/mcp_migrate/rules/r012_logging_set_level_removed.py) | breaking | `logging/setLevel` ([SEP-2575](https://modelcontextprotocol.io/specification/2026-07-28/changelog)) is removed; log level is per-request via `_meta` now. | no |
| [R013](src/mcp_migrate/rules/r013_subscriptions_replaced.py) | breaking | `resources/subscribe`/`resources/unsubscribe` ([SEP-2575](https://modelcontextprotocol.io/specification/2026-07-28/changelog)) are replaced by `subscriptions/listen`. | no |
| [R014](src/mcp_migrate/rules/r014_sse_resumability_removed.py) | breaking | SSE resumability via `Last-Event-ID` ([SEP-2575](https://modelcontextprotocol.io/specification/2026-07-28/changelog)) is removed; a dropped connection is just dropped now. | no |
| [R015](src/mcp_migrate/rules/r015_result_type_required.py) | advisory | Every result now requires `resultType` ([SEP-2322](https://modelcontextprotocol.io/specification/2026-07-28/changelog)). Fires only on servers that build their own JSON-RPC envelopes: the official SDK stamps the field on every result it serializes, so an SDK-based server has nothing to add. | no |
| [R016](src/mcp_migrate/rules/r016_cacheable_result_required.py) | advisory | List/read results require `ttlMs`/`cacheScope` ([SEP-2549](https://modelcontextprotocol.io/specification/2026-07-28/changelog)). The SDK fills these only when the server is built with `cache_hints=`, so configuring hints anywhere satisfies it. Advisory: nothing has adopted the new API yet. | no |
| [R017](src/mcp_migrate/rules/r017_resource_not_found_code_changed.py) | breaking | The resource-not-found [error code](https://modelcontextprotocol.io/specification/2026-07-28/changelog) changed from `-32002` to `-32602`. | yes (`safe`) |
| [R018](src/mcp_migrate/rules/r018_multi_round_trip_replaces_server_initiated.py) | breaking | Server-initiated Roots/Sampling/Elicitation ([SEP-2322](https://modelcontextprotocol.io/specification/2026-07-28/changelog)) are replaced by Multi Round-Trip Requests (`InputRequiredResult` + `inputResponses`). | no |
| [R019](src/mcp_migrate/rules/r019_tasks_polling_replaces_blocking_result.py) | breaking | `tasks/list` is removed and blocking `tasks/result` ([SEP-2663](https://modelcontextprotocol.io/specification/2026-07-28/changelog)) is replaced by polling; Tasks moves to an extension. | no |
| [R020](src/mcp_migrate/rules/r020_dynamic_client_registration_deprecated.py) | deprecated | RFC 7591 [Dynamic Client Registration](https://modelcontextprotocol.io/specification/2026-07-28/changelog) is deprecated in favor of Client ID Metadata Documents. | no |
| [R021](src/mcp_migrate/rules/r021_json_schema_2020_12_required.py) | advisory | Implementations must support at least [JSON Schema 2020-12](https://modelcontextprotocol.io/specification/2026-07-28/changelog) ([SEP-2106](https://modelcontextprotocol.io/specification/2026-07-28/changelog)) for `inputSchema`/`outputSchema`. | no |

Run `mcp-migrate rules` to see this list for the exact version you have
installed, and `mcp-migrate fixers` for the fixer confidence table. Full
spec changelog: https://modelcontextprotocol.io/specification/draft/changelog.

Missed something and want to fill in a fixer, or just document the manual
fix? See [Contribute](#contribute) below and
[`cookbook/`](cookbook/README.md) for every change that doesn't have a
recipe yet.

## The grade

Every finding costs points, but no single rule can sink your grade by
itself: each rule's total contribution is capped, no matter how many times
it fires. Real evidence for why this matters: `mcp-atlassian`'s R003 once
hit 19 times on the same false-positive pattern, for 475 raw penalty
points -- over 4x what one rule is now allowed to cost.

| Severity     | Cost per finding | Cap per rule | Meaning                                     |
| ------------ | ----------------- | ------------ | -------------------------------------------- |
| `breaking`   | -25                | -25          | Your server stops working under 2026-07-28.   |
| `deprecated` | -8                 | -12          | Still works today, on a 12+ month clock.      |
| `advisory`   | -3                 | -6           | Best practice, not a compatibility risk.      |

Score starts at 100 and floors at 0. The letter grade comes from the score:

| Score  | Grade | Badge color   |
| ------ | ----- | ------------- |
| 95-100 | A     | brightgreen   |
| 80-94  | B     | green         |
| 60-79  | C     | yellow        |
| 40-59  | D     | orange        |
| 0-39   | F     | red           |

## Get your badge

Run the check, fix what's `breaking`, then generate your entry and badge in
one shot:

```bash
uvx mcp-migrate entry --repo owner/name > registry/servers/name.yaml
```

`entry` refuses — writing nothing to stdout, so the redirect above leaves no
file behind — if it can't read your server, or if your Python is a small
minority of a repo that's mostly something else. A board entry is a claim
about a whole repo, and this project would rather publish nothing than
publish a grade it can't stand behind.

That prints something like:

```
# registry/servers/name.yaml
name: name
repo: owner/name
language: python
grade: A
score: 100
checked_with: mcp-migrate 0.1.0
spec: "2026-07-28"
status: ready
notes: >-
  Replace this line with one sentence about what your server does.
```

Edit the `notes:` line to one sentence about what your server does, then PR
it into this repo (steps in
[CONTRIBUTING.md](CONTRIBUTING.md#add-your-server-to-the-board-60-seconds)).
CI validates the YAML against `registry/schema.yaml` and regenerates the
board below on merge. Listing is automated and unopinionated: schema
passes and the repo exists, it merges -- no maintainer reviews the server
itself or argues about your grade.

Drop this in your own README once you know your grade (swap the letter and
color using the table above):

```markdown
[![MCP 2026-07-28](https://img.shields.io/badge/MCP%202026--07--28-A-brightgreen)](https://github.com/owner/name)
```

## The board

<!-- BOARD:START -->

**14 servers checked** (6x A, 6x B, 1x C, 1x D)

| server | grade | status | language | what it does |
| --- | --- | --- | --- | --- |
| [aws-documentation-mcp-server](https://github.com/awslabs/mcp) | **A** | ready | python | AWS Labs MCP server that fetches, searches, and recommends AWS documentation pages, converted to markdown. |
| [cloudwatch-mcp-server](https://github.com/awslabs/mcp) | **A** | ready | python | AWS Labs MCP server for CloudWatch that gives troubleshooting agents alarm, metric, and log data for root cause analysis. |
| [duckduckgo-mcp-server](https://github.com/nickclyde/duckduckgo-mcp-server) | **A** | ready | python | MCP server that provides web search through DuckDuckGo, with additional content fetching and parsing features. |
| [dynamodb-mcp-server](https://github.com/awslabs/mcp) | **A** | ready | python | Official AWS DynamoDB MCP server providing expert data modeling guidance, validation, and cost analysis tools. |
| [mcp-server-motherduck](https://github.com/motherduckdb/mcp-server-motherduck) | **A** | ready | python | Local MCP server connecting AI assistants to DuckDB and MotherDuck for SQL analytics and data engineering. |
| [mcp-server-qdrant](https://github.com/qdrant/mcp-server-qdrant) | **A** | ready | python | Official MCP server for Qdrant that acts as a semantic memory layer for keeping and retrieving memories in the vector search engine. |
| [mcp-server-tree-sitter](https://github.com/wrale/mcp-server-tree-sitter) | **B** | ready | python | MCP server providing tree-sitter code analysis so AI assistants get structure-aware access to codebases in many languages. |
| [mcp-server-fetch](https://github.com/modelcontextprotocol/servers) | **B** | ready | python | Reference MCP server that fetches web pages and converts HTML to markdown so LLMs can read them in chunks. |
| [mcp-server-sentry](https://github.com/modelcontextprotocol/servers-archived) | **B** | ready | python | Archived reference MCP server for retrieving and analyzing issues, stacktraces, and debugging info from Sentry.io. |
| [mcp-server-sqlite](https://github.com/modelcontextprotocol/servers-archived) | **B** | ready | python | Archived reference MCP server for SQLite that runs SQL queries and auto-generates business insight memos. |
| [mcp-server-time](https://github.com/modelcontextprotocol/servers) | **B** | ready | python | Reference MCP server giving LLMs current time and timezone conversion using IANA timezone names. |
| [mcp-neo4j-cypher](https://github.com/neo4j-contrib/mcp-neo4j) | **B** | ready | python | MCP server for Neo4j that runs Cypher graph queries and supports Text2Cypher workflows over graph data. |
| [mcp-atlassian](https://github.com/sooperset/mcp-atlassian) | **C** | migrating | python | MCP server for Atlassian products (Confluence and Jira), supporting both Cloud and Server/Data Center deployments. |
| [mcp-server-git](https://github.com/modelcontextprotocol/servers) | **D** | ready | python | Reference MCP server for Git repository interaction, giving LLMs tools to read, search, and manipulate repos. |

<!-- BOARD:END -->

## Contribute

Three ways in, cheapest first:

- **A cookbook recipe (~5 minutes).** Pick an open slot in
  [`cookbook/`](cookbook/README.md) -- markdown, no Python, no tests. See
  [CONTRIBUTING.md](CONTRIBUTING.md#add-a-cookbook-recipe-5-minutes).
- **A rule (~15 minutes).** A `Rule` subclass -- a `check(project)` method,
  a regex or an AST walk, a `Finding` for every hit. Most rules are under 25
  lines. See [CONTRIBUTING.md](CONTRIBUTING.md#add-a-rule-15-minutes).
- **A fixer (~45 minutes).** A `Fixer` subclass that turns one rule's
  finding into a text-level edit, tagged `safe` or `review`. See
  [CONTRIBUTING.md](CONTRIBUTING.md#add-a-fixer-45-minutes).

The standing principle behind all three: **a false positive is worse than a
missed finding.** When a rule can't be made precise, it ships `advisory`, or
it doesn't ship. Reviews happen within 48 hours; one passing test is enough
to merge.

Listing your own server on the board is separate from all three and takes
about 60 seconds -- see
[CONTRIBUTING.md](CONTRIBUTING.md#add-your-server-to-the-board-60-seconds).

## Contributors

TypeScript support exists because these people built it. The language
backend shipped with two reference ports (R001 and R006). **The other twelve
were contributed** -- in parallel, by seven people who mostly hadn't spoken
to each other, each working from a separate issue.

| | Contribution |
| --- | --- |
| [@syf2211](https://github.com/syf2211) | R015, R016, R020 ports; R007 and R014 fixers; the R003 cookbook recipe. Also found and reported the R016 false negative that became [#66](https://github.com/dheerajjha/mcp-migrate/issues/66) rather than leaving it buried. |
| [@PuvaanRaaj](https://github.com/PuvaanRaaj) | R012, R018, R019 ports |
| [@atiqur-rahman-pro](https://github.com/atiqur-rahman-pro) | R003 and R004 ports, then replaced R004's fixed 40-line look-ahead with a brace-depth scan ([#65](https://github.com/dheerajjha/mcp-migrate/issues/65)) |
| [@MasRama](https://github.com/MasRama) | R005 and R011 ports. Reported the hardcoded coverage assertion that would have made every parallel port conflict with every other one -- the single most useful bug anyone has filed here. |
| [@s35153](https://github.com/s35153) | R007 and R009 ports |
| [@IronLad123](https://github.com/IronLad123) | Routed R016's metadata check through content spans, so a comment can no longer silence a real finding ([#66](https://github.com/dheerajjha/mcp-migrate/issues/66)) |
| [@li2631026381-alt](https://github.com/li2631026381-alt) | Hoisted R015's TypeScript scans out of the per-file loop -- 63.0ms to 3.1ms at 200 files |

`git shortlog -sne` is the authoritative list; [`.mailmap`](.mailmap) folds
the duplicate identities so nobody is counted twice or split in half.

## Working principles

**A false positive is worse than a missed finding.** This tool publishes
public grades about other people's projects. A wrong `breaking` verdict costs
a maintainer their badge and their trust in the tool; a missed `advisory`
costs a little visibility and nothing else. When a detection can't be made
precise it ships `advisory`, or it doesn't ship. Fixers follow the same rule:
one that can't be certain a transformation is correct leaves the source
untouched.

**An unearned grade is as damaging as an undeserved finding**, and harder to
notice. A server that scores A because a rule couldn't see its handlers is a
bug, not a pass -- see
[`r010_server_discover_missing.py`](src/mcp_migrate/rules/r010_server_discover_missing.py),
where three registration idioms used by real servers went undetected.

**No grade is published that hasn't been reproduced.** Every entry in
`registry/servers/` comes from a scan someone ran and read, at that server's
own directory. Nothing is estimated, and nothing is carried forward from a
previous version of the rules.

**Contributing stays cheap.** One small file is the unit of contribution, and
a submission that passes schema validation and points at a real repository is
merged -- there's no usage bar, no curation step, and no reviewer taste test.
Reviews happen within 48 hours and one passing test is enough to merge a rule.

The longer form of all of this, with the API you'd actually use, is in
[CONTRIBUTING.md](CONTRIBUTING.md).

## License

Apache-2.0. See [LICENSE](LICENSE).

Listing on the board is automated and unopinionated: if
`registry/servers/*.yaml` passes schema validation and the repo it points at
exists, it gets merged. No maintainer reviews the server itself.
