# Good first issues

Ready-to-paste issue bodies for two categories of open work:

1. Cookbook recipes that exist only as stubs (rule/spec filled in, before/after
   and gotchas still needed) -- see [`cookbook/README.md`](../cookbook/README.md#stubs----open-slots).
2. Rules that have no fixer yet -- see the "Fixer" column in the
   [README's rule table](../README.md#every-rule).

Each block below is delimited by `### ISSUE_START` / `### ISSUE_END` so
[`scripts/file_issues.sh`](scripts/file_issues.sh) can parse and file them
in bulk with `gh issue create`. To file them all yourself:

```bash
.github/scripts/file_issues.sh                  # files into the repo gh is already pointed at
.github/scripts/file_issues.sh owner/mcp-migrate # or an explicit owner/repo
```

To file one by hand instead, copy the `TITLE`/`LABELS`/body between one
issue's markers into `gh issue create --title "..." --label "..." --body "..."`.

**Keep the label spelled `good first issue`, with spaces.** GitHub's
`/contribute` page -- the thing that surfaces a repo to people explicitly
looking for a first contribution -- only recognises that exact spelling. An
earlier batch used `good-first-issue`, and all 29 issues were invisible on
that page until the label was corrected. The hyphenated label still exists
and still means the same thing to a human; it just does nothing.

Don't edit the markers or the `TITLE:`/`LABELS:`/`DIFFICULTY:`/`BODY_START`/
`BODY_END` lines -- the script depends on them being exact.

---

### ISSUE_START
TITLE: Cookbook recipe: ping removed (R011)
LABELS: good first issue,cookbook
DIFFICULTY: easy (~15-30 min)
BODY_START
`cookbook/06-ping-removed.md` exists as a stub: the rule, severity and spec
link are already filled in, the before/after code and gotchas aren't.

**Context:** R011 ([`src/mcp_migrate/rules/r011_ping_removed.py`](../../src/mcp_migrate/rules/r011_ping_removed.py))
flags servers still implementing the removed `ping`/`PingRequest`
request-response. There's no fixer for this rule yet either (see the
separate "Add a fixer" issue for R011 if you want to take that on too, but
it's not required for this one).

**Spec:** SEP-2575 -- https://modelcontextprotocol.io/specification/2026-07-28/changelog

**What "done" looks like:** fill in the Before/After/Gotchas sections of
`cookbook/06-ping-removed.md` following `cookbook/_TEMPLATE.md`'s format
(see any of the five filled-in recipes, e.g. `cookbook/03-sse-to-streamable-http.md`,
for the level of detail expected). Move its row from the "Stubs" table to
the "Filed so far" table in `cookbook/README.md`. No code, no tests --
markdown only.

See CONTRIBUTING.md#add-a-cookbook-recipe-5-minutes.
BODY_END
### ISSUE_END

### ISSUE_START
TITLE: Cookbook recipe: logging/setLevel removed (R012)
LABELS: good first issue,cookbook
DIFFICULTY: easy (~15-30 min)
BODY_START
`cookbook/07-logging-set-level-removed.md` exists as a stub.

**Context:** R012 ([`src/mcp_migrate/rules/r012_logging_set_level_removed.py`](../../src/mcp_migrate/rules/r012_logging_set_level_removed.py))
flags servers still implementing the removed `logging/setLevel` request.
Log level is now per-request, read off `_meta["io.modelcontextprotocol/logLevel"]`.

**Spec:** SEP-2575 -- https://modelcontextprotocol.io/specification/2026-07-28/changelog

**What "done" looks like:** fill in Before/After/Gotchas in
`cookbook/07-logging-set-level-removed.md` per `cookbook/_TEMPLATE.md`.
Particularly useful: a concrete example of moving from a process-wide log
level to per-request handling with Python's stdlib `logging` (which is
process-global by default) -- contextvars-based scoping is probably the
real answer and worth spelling out. Move its row out of "Stubs" in
`cookbook/README.md` once filled in.

See CONTRIBUTING.md#add-a-cookbook-recipe-5-minutes.
BODY_END
### ISSUE_END

### ISSUE_START
TITLE: Cookbook recipe: SSE resumability removed (R014)
LABELS: good first issue,cookbook
DIFFICULTY: easy (~15-30 min)
BODY_START
`cookbook/08-sse-resumability-removed.md` exists as a stub.

**Context:** R014 ([`src/mcp_migrate/rules/r014_sse_resumability_removed.py`](../../src/mcp_migrate/rules/r014_sse_resumability_removed.py))
flags `Last-Event-ID`-based stream resumability, which is removed as of
2026-07-28 regardless of which HTTP transport you're on.

**Spec:** SEP-2575 -- https://modelcontextprotocol.io/specification/2026-07-28/changelog

**What "done" looks like:** fill in Before/After/Gotchas in
`cookbook/08-sse-resumability-removed.md` per `cookbook/_TEMPLATE.md`. A
worked example of an event store + `Last-Event-ID` replay handler being
retired, and a note on what (if anything) needs to change client-side to
stop sending `Last-Event-ID`.

See CONTRIBUTING.md#add-a-cookbook-recipe-5-minutes.
BODY_END
### ISSUE_END

### ISSUE_START
TITLE: Cookbook recipe: resource-not-found error code -32002 -> -32602 (R017)
LABELS: good first issue,cookbook
DIFFICULTY: easy (~15-30 min)
BODY_START
`cookbook/09-resource-not-found-error-code.md` exists as a stub. Note this
rule already ships a `safe`-confidence fixer -- this recipe is for the
worked example and the fixer's edge cases, not new code.

**Context:** R017 ([`src/mcp_migrate/rules/r017_resource_not_found_code_changed.py`](../../src/mcp_migrate/rules/r017_resource_not_found_code_changed.py))
flags the old `-32002` resource-not-found JSON-RPC error code, replaced by
`-32602`.

**Spec:** https://modelcontextprotocol.io/specification/2026-07-28/changelog

**What "done" looks like:** fill in Before/After/Gotchas in
`cookbook/09-resource-not-found-error-code.md` per `cookbook/_TEMPLATE.md`.
Specifically call out what happens when the qualifying context (a mention
of "resource" or "not found") is on a different line than the `-32002`
literal -- the fixer requires both on one line, and that's a real,
documentable limitation.

See CONTRIBUTING.md#add-a-cookbook-recipe-5-minutes.
BODY_END
### ISSUE_END

### ISSUE_START
TITLE: Cookbook recipe: Multi Round-Trip Requests replace server-initiated calls (R018)
LABELS: good first issue,cookbook
DIFFICULTY: medium (~30-45 min)
BODY_START
`cookbook/10-multi-round-trip-requests.md` exists as a stub. This is the
biggest control-flow change in the spec revision, so this recipe is worth
more time than most.

**Context:** R018 ([`src/mcp_migrate/rules/r018_multi_round_trip_replaces_server_initiated.py`](../../src/mcp_migrate/rules/r018_multi_round_trip_replaces_server_initiated.py))
flags server-initiated `roots/list`, `sampling/createMessage` and
`elicitation/create` -- all replaced by Multi Round-Trip Requests
(`InputRequiredResult` + client-driven `inputResponses`).

**Spec:** SEP-2322 -- https://modelcontextprotocol.io/specification/2026-07-28/changelog

**What "done" looks like:** fill in Before/After/Gotchas in
`cookbook/10-multi-round-trip-requests.md` per `cookbook/_TEMPLATE.md`. The
highest-value thing this recipe needs: a concrete answer for where the
handler's local state goes between "returned InputRequiredResult" and "got
the retried call with inputResponses" -- it can't just live on a blocked
coroutine's stack anymore.

See CONTRIBUTING.md#add-a-cookbook-recipe-5-minutes.
BODY_END
### ISSUE_END

### ISSUE_START
TITLE: Cookbook recipe: Tasks moved to an extension, polling replaces blocking result (R019)
LABELS: good first issue,cookbook
DIFFICULTY: medium (~30-45 min)
BODY_START
`cookbook/11-tasks-polling.md` exists as a stub.

**Context:** R019 ([`src/mcp_migrate/rules/r019_tasks_polling_replaces_blocking_result.py`](../../src/mcp_migrate/rules/r019_tasks_polling_replaces_blocking_result.py))
flags removed `tasks/list` and the removed blocking `tasks/result`, replaced
by polling `tasks/get` + `tasks/update`. Tasks itself moves into the
`io.modelcontextprotocol/tasks` extension.

**Spec:** SEP-2663 -- https://modelcontextprotocol.io/specification/2026-07-28/changelog

**What "done" looks like:** fill in Before/After/Gotchas in
`cookbook/11-tasks-polling.md` per `cookbook/_TEMPLATE.md`. Include a
client-side polling loop sketch (interval/backoff), and a note on the
relationship (if any) to R018's Multi Round-Trip Requests -- both concern
long-running work via different mechanisms.

See CONTRIBUTING.md#add-a-cookbook-recipe-5-minutes.
BODY_END
### ISSUE_END

### ISSUE_START
TITLE: Cookbook recipe: Dynamic Client Registration deprecated (R020)
LABELS: good first issue,cookbook
DIFFICULTY: medium (~30-45 min, needs external CIMD research)
BODY_START
`cookbook/12-dynamic-client-registration-deprecated.md` exists as a stub.
This is flagged as the least-documented change in the whole revision from a
"here's exactly what to do instead" angle -- expect to need to research
Client ID Metadata Documents (CIMD) beyond this repo to write it well.

**Context:** R020 ([`src/mcp_migrate/rules/r020_dynamic_client_registration_deprecated.py`](../../src/mcp_migrate/rules/r020_dynamic_client_registration_deprecated.py))
flags RFC 7591 Dynamic Client Registration, deprecated in favor of CIMD.

**Spec:** https://modelcontextprotocol.io/specification/2026-07-28/changelog

**What "done" looks like:** fill in Before/After/Gotchas in
`cookbook/12-dynamic-client-registration-deprecated.md` per
`cookbook/_TEMPLATE.md`, including a link to the actual CIMD spec/RFC and a
concrete description of the document shape a server publishes instead of
implementing `register_client`.

See CONTRIBUTING.md#add-a-cookbook-recipe-5-minutes.
BODY_END
### ISSUE_END

### ISSUE_START
TITLE: Cookbook recipe: JSON Schema 2020-12 required (R021)
LABELS: good first issue,cookbook
DIFFICULTY: easy (~15-30 min)
BODY_START
`cookbook/13-json-schema-2020-12.md` exists as a stub.

**Context:** R021 ([`src/mcp_migrate/rules/r021_json_schema_2020_12_required.py`](../../src/mcp_migrate/rules/r021_json_schema_2020_12_required.py))
flags an explicit older JSON Schema dialect (`draft-07`, `2019-09`, ...)
pinned on `inputSchema`/`outputSchema`. Advisory, not breaking -- most
servers never pin a dialect at all.

**Spec:** SEP-2106 -- https://modelcontextprotocol.io/specification/2026-07-28/changelog

**What "done" looks like:** fill in Before/After/Gotchas in
`cookbook/13-json-schema-2020-12.md` per `cookbook/_TEMPLATE.md`. Worth
noting whether dropping an explicit `$schema` pin changes validator
behavior in practice for common Python JSON Schema libraries.

See CONTRIBUTING.md#add-a-cookbook-recipe-5-minutes.
BODY_END
### ISSUE_END

### ISSUE_START
TITLE: Cookbook recipe: required Mcp-Method / Mcp-Name routing headers (R003)
LABELS: good first issue,cookbook
DIFFICULTY: easy (~15-30 min)
BODY_START
`cookbook/14-routing-headers.md` exists as a stub.

**Context:** R003 ([`src/mcp_migrate/rules/r003_routing_headers.py`](../../src/mcp_migrate/rules/r003_routing_headers.py))
flags hand-rolled HTTP clients speaking MCP's wire protocol that don't set
the required `Mcp-Method` (and, on `tools/call`/`resources/read`/
`prompts/get`, `Mcp-Name`) headers. Read the rule source's comments first --
this rule was downgraded from `breaking` to `advisory` after a real
false-positive incident (19 false hits on mcp-atlassian) and the recipe
should explain why.

**Spec:** https://modelcontextprotocol.io/specification/2026-07-28/basic/transports/streamable-http

**What "done" looks like:** fill in Before/After/Gotchas in
`cookbook/14-routing-headers.md` per `cookbook/_TEMPLATE.md`, with a
concrete example each of a file that *does* and *doesn't* trip the rule's
`_imports_mcp`/`MCP_METHOD_RX` gating, so a reader understands the
distinction between "hand-rolling MCP transport" and "wrapping an unrelated
backend REST API."

See CONTRIBUTING.md#add-a-cookbook-recipe-5-minutes.
BODY_END
### ISSUE_END

### ISSUE_START
TITLE: Cookbook recipe: deterministic tools/list ordering (R004)
LABELS: good first issue,cookbook
DIFFICULTY: easy (~15-30 min)
BODY_START
`cookbook/15-deterministic-tool-ordering.md` exists as a stub. Note this
rule already ships a `safe`-confidence fixer for the one unambiguous
shape -- this recipe is for everything the fixer doesn't reach.

**Context:** R004 ([`src/mcp_migrate/rules/r004_tool_ordering.py`](../../src/mcp_migrate/rules/r004_tool_ordering.py))
flags `tools/list` handlers that don't guarantee a stable order.

**Spec:** "Deterministic tool ordering" (SHOULD) -- https://modelcontextprotocol.io/specification/draft/changelog

**What "done" looks like:** fill in Before/After/Gotchas in
`cookbook/15-deterministic-tool-ordering.md` per `cookbook/_TEMPLATE.md`.
Specifically: a real example where the fixer's shape detection
(`src/mcp_migrate/fixers/r004_tool_ordering.py`) doesn't apply -- tools
built up across an `if`/`append` sequence rather than a single return of a
list literal -- and a note on when alphabetizing is the wrong call (an
intentional, product-driven order).

See CONTRIBUTING.md#add-a-cookbook-recipe-5-minutes.
BODY_END
### ISSUE_END

### ISSUE_START
TITLE: Cookbook recipe: extensions map on ServerCapabilities (R005)
LABELS: good first issue,cookbook
DIFFICULTY: easy (~15-30 min)
BODY_START
`cookbook/16-extensions-map.md` exists as a stub. Note this rule already
ships a `safe`-confidence fixer that adds `extensions={}` -- this recipe is
about the full picture, including populated extensions.

**Context:** R005 ([`src/mcp_migrate/rules/r005_extensions.py`](../../src/mcp_migrate/rules/r005_extensions.py))
flags `ServerCapabilities(...)` declared without an `extensions` map.

**Spec:** "extensions field on ServerCapabilities" -- https://modelcontextprotocol.io/specification/draft/changelog

**What "done" looks like:** fill in Before/After/Gotchas in
`cookbook/16-extensions-map.md` per `cookbook/_TEMPLATE.md`. Include a
second example beyond the trivial `extensions={}` no-op: a server that
declares a real extension (`io.modelcontextprotocol/tasks` is the obvious
one -- see `cookbook/11-tasks-polling.md`) and what a populated map looks
like.

See CONTRIBUTING.md#add-a-cookbook-recipe-5-minutes.
BODY_END
### ISSUE_END

### ISSUE_START
TITLE: Cookbook recipe: trace context propagation from _meta (R008)
LABELS: good first issue,cookbook
DIFFICULTY: easy (~15-30 min)
BODY_START
`cookbook/17-trace-context-propagation.md` exists as a stub.

**Context:** R008 ([`src/mcp_migrate/rules/r008_trace_context.py`](../../src/mcp_migrate/rules/r008_trace_context.py))
flags projects that import `opentelemetry` but never read `traceparent` off
`_meta`.

**Spec:** SEP-414 -- https://github.com/modelcontextprotocol/modelcontextprotocol/pull/414

**What "done" looks like:** fill in Before/After/Gotchas in
`cookbook/17-trace-context-propagation.md` per `cookbook/_TEMPLATE.md`. The
single highest-value addition: a real example using OpenTelemetry Python's
`TraceContextTextMapPropagator`/`propagate.extract` against a `_meta` dict.

See CONTRIBUTING.md#add-a-cookbook-recipe-5-minutes.
BODY_END
### ISSUE_END

### ISSUE_START
TITLE: Cookbook recipe: Roots / Sampling / Logging deprecated as core capabilities (R007)
LABELS: good first issue,cookbook
DIFFICULTY: easy (~15-30 min)
BODY_START
`cookbook/18-roots-sampling-logging-deprecated.md` exists as a stub.

**Context:** R007 ([`src/mcp_migrate/rules/r007_deprecated_features.py`](../../src/mcp_migrate/rules/r007_deprecated_features.py))
flags Roots, Sampling and Logging as deprecated core capabilities. This
rule intentionally overlaps with R018 for Sampling/elicitation specifically
(R007 reports `deprecated`, R018 reports the same code path `breaking`) --
the recipe should explain that relationship plainly.

**Spec:** "Roots, Sampling and Logging deprecated" -- https://modelcontextprotocol.io/specification/draft/changelog

**What "done" looks like:** fill in Before/After/Gotchas in
`cookbook/18-roots-sampling-logging-deprecated.md` per
`cookbook/_TEMPLATE.md`, with a worked Roots-to-resource-URIs example and a
short, explicit answer to "R007 and R018 both fired on my file, which do I
fix first?" (the breaking one, R018/R009/etc., but say so with an example).

See CONTRIBUTING.md#add-a-cookbook-recipe-5-minutes.
BODY_END
### ISSUE_END

### ISSUE_START
TITLE: Fixer: per-connection state in a module-level dict (R002)
LABELS: good first issue,fixer
DIFFICULTY: hard (~90+ min, may not be safely automatable)
BODY_START
No fixer exists yet for R002 ([`src/mcp_migrate/rules/r002_connection_state.py`](../../src/mcp_migrate/rules/r002_connection_state.py)),
which flags a module-level dict keyed by connection/session (state that
breaks the moment a server runs more than one replica).

**Spec:** SEP-2567 -- https://github.com/modelcontextprotocol/modelcontextprotocol/pull/2567

**Before attempting this:** read CONTRIBUTING.md's fixer section, especially
the standing principle -- **a false positive is worse than a missed
finding**, and a fixer that guesses wrong here silently corrupts a
project's persistence layer. Moving state into a real store is an
architectural decision (what store? what's the key shape?) that a text
editor cannot make safely. It's plausible the right outcome of this issue
is "no fixer ships, and the finding stands as `review`-only guidance
pointing at [`cookbook/01-sessions-to-explicit-handles.md`](../../cookbook/01-sessions-to-explicit-handles.md)"
-- that's a legitimate resolution, not a failure to close this out. If you
land on that conclusion, say so in the PR/comment instead of forcing code
that doesn't belong.

**What "done" looks like:** either a `Fixer` subclass in
`src/mcp_migrate/fixers/` (with the standard fixture + round-trip/idempotency
tests from `tests/test_fixers.py`'s pattern) for whatever narrow, genuinely
safe subset you can identify, or a documented decision that this rule stays
fixer-less with the reasoning recorded.

See CONTRIBUTING.md#add-a-fixer-45-minutes.
BODY_END
### ISSUE_END

### ISSUE_START
TITLE: Fixer: SSE resumability (Last-Event-ID) removed (R014)
LABELS: good first issue,fixer
DIFFICULTY: medium (~30-45 min)
BODY_START
No fixer exists yet for R014 ([`src/mcp_migrate/rules/r014_sse_resumability_removed.py`](../../src/mcp_migrate/rules/r014_sse_resumability_removed.py)),
which flags `Last-Event-ID`-based stream resumability, removed as of
2026-07-28.

**Spec:** SEP-2575 -- https://modelcontextprotocol.io/specification/2026-07-28/changelog

**A reasonable scope:** same TODO-annotation pattern as the R011/R012
fixer issues -- comment out the dead `Last-Event-ID` read/event-store
replay code with a `# TODO(mcp-migrate): ...` pointing at
`cookbook/08-sse-resumability-removed.md`. The event store itself (if it
serves other purposes, e.g. audit logging) should be left alone; only the
resumability-specific read/replay logic is in scope.

**What "done" looks like:** a `Fixer` subclass in `src/mcp_migrate/fixers/`,
`review` confidence, with fixtures and tests per `tests/test_fixers.py`.

See CONTRIBUTING.md#add-a-fixer-45-minutes.
BODY_END
### ISSUE_END

### ISSUE_START
TITLE: Fixer: missing Mcp-Method/Mcp-Name routing headers (R003)
LABELS: good first issue,fixer
DIFFICULTY: hard (~60-90 min, advisory severity -- lower priority)
BODY_START
No fixer exists yet for R003 ([`src/mcp_migrate/rules/r003_routing_headers.py`](../../src/mcp_migrate/rules/r003_routing_headers.py)),
which flags hand-rolled HTTP `.post()`/`.request()` calls missing the
required `Mcp-Method`/`Mcp-Name` headers.

**Spec:** https://modelcontextprotocol.io/specification/2026-07-28/basic/transports/streamable-http

**Why this is hard:** the rule itself is already `advisory` (downgraded
from `breaking` after a real false-positive incident -- read the rule
source's comments on mcp-atlassian's R003 history before starting). Any
fixer needs to be at least as conservative as the rule's own gating
(`_imports_mcp`/`MCP_METHOD_RX`), and inserting a header into an arbitrary
`.post(...)` call site correctly (as a kwarg? into an existing `headers=`
dict? a new one?) needs real call-site parsing, not just a regex match.

**What "done" looks like:** a `Fixer` subclass in `src/mcp_migrate/fixers/`
that only fires on the narrowest, most mechanical shape you're confident
about (e.g. a call site that already has a `headers={...}` dict literal
inline), leaving everything else alone, confidence tagged `review`. Include
fixtures and tests per `tests/test_fixers.py`'s pattern.

See CONTRIBUTING.md#add-a-fixer-45-minutes.
BODY_END
### ISSUE_END

### ISSUE_START
TITLE: Fixer: Roots/Sampling/Logging deprecated core features (R007)
LABELS: good first issue,fixer
DIFFICULTY: medium (~45-60 min)
BODY_START
No fixer exists yet for R007 ([`src/mcp_migrate/rules/r007_deprecated_features.py`](../../src/mcp_migrate/rules/r007_deprecated_features.py)),
which flags dependencies on Roots, Sampling or Logging as core capabilities.

**Spec:** "Roots, Sampling and Logging deprecated" -- https://modelcontextprotocol.io/specification/draft/changelog

**A reasonable scope:** rather than trying to migrate the functionality
(impossible without understanding what the handler does), consider the
`r001_session_id.py` fixer's pattern -- annotate the flagged line with a
`# TODO(mcp-migrate): ...` comment pointing at the spec and
`cookbook/18-roots-sampling-logging-deprecated.md`, `review` confidence,
without touching the code's behavior at all. That's mechanical, safe, and
genuinely useful (a loud, precise pointer at what needs human attention)
without pretending to migrate something this fuzzy automatically.

**What "done" looks like:** a `Fixer` subclass in `src/mcp_migrate/fixers/`
following that TODO-annotation pattern, with fixtures and tests per
`tests/test_fixers.py`.

See CONTRIBUTING.md#add-a-fixer-45-minutes.
BODY_END
### ISSUE_END

### ISSUE_START
TITLE: Fixer: trace context not propagated from _meta (R008)
LABELS: good first issue,fixer
DIFFICULTY: medium (~45 min)
BODY_START
No fixer exists yet for R008 ([`src/mcp_migrate/rules/r008_trace_context.py`](../../src/mcp_migrate/rules/r008_trace_context.py)),
which flags OpenTelemetry-using projects that never read `traceparent` off
`_meta`.

**Spec:** SEP-414 -- https://github.com/modelcontextprotocol/modelcontextprotocol/pull/414

**Why this is hard to make `safe`:** there's no single call site to patch --
the finding is project-wide ("OpenTelemetry is used somewhere, `traceparent`
is read nowhere"), not tied to one line. A useful, honest fixer here
probably can't insert working extraction code blind; it's more likely to
land as a `review`-confidence TODO inserted at the request-handling entry
point(s) the fixer can identify, pointing at
`cookbook/17-trace-context-propagation.md`.

**What "done" looks like:** a `Fixer` subclass in `src/mcp_migrate/fixers/`
with a scope you can defend as genuinely mechanical (even if that scope is
"insert a TODO comment," not "extract the trace context correctly"), with
fixtures and tests per `tests/test_fixers.py`.

See CONTRIBUTING.md#add-a-fixer-45-minutes.
BODY_END
### ISSUE_END

### ISSUE_START
TITLE: Fixer: initialize/initialized handshake still implemented (R009)
LABELS: good first issue,fixer
DIFFICULTY: hard (~60-90 min)
BODY_START
No fixer exists yet for R009 ([`src/mcp_migrate/rules/r009_initialize_handshake_removed.py`](../../src/mcp_migrate/rules/r009_initialize_handshake_removed.py)),
which flags the removed `initialize`/`notifications/initialized` handshake.

**Spec:** SEP-2575 -- https://modelcontextprotocol.io/specification/2026-07-28/changelog

**A reasonable scope:** the `r001_session_id.py` fixer's approach (comment
out the dead handler, leave a `# TODO(mcp-migrate): ...` pointing at
`cookbook/02-initialize-to-server-discover.md`) is a good template --
deleting the handler decorator/function outright risks leaving a dangling
reference elsewhere in the file (an import, a registration call) that a
text-level fixer can't safely trace. Commenting out is reversible and
loud; deleting is not.

**What "done" looks like:** a `Fixer` subclass in `src/mcp_migrate/fixers/`
using that pattern, `review` confidence, with fixtures and tests per
`tests/test_fixers.py`.

See CONTRIBUTING.md#add-a-fixer-45-minutes.
BODY_END
### ISSUE_END

### ISSUE_START
TITLE: Fixer: server/discover missing (R010)
LABELS: good first issue,fixer
DIFFICULTY: hard (~60+ min, may not be safely automatable)
BODY_START
No fixer exists yet for R010 ([`src/mcp_migrate/rules/r010_server_discover_missing.py`](../../src/mcp_migrate/rules/r010_server_discover_missing.py)),
which flags projects that register MCP handlers but never implement
`server/discover`.

**Spec:** SEP-2575 -- https://modelcontextprotocol.io/specification/2026-07-28/changelog

**Why this is hard:** unlike most fixers in this project, this finding
requires *adding* new, correct behavior (a `server/discover` response
describing this specific server's protocol versions, capabilities and
identity), not editing existing code. A fixer can't invent a server's name
or which capabilities it actually supports. A plausible outcome here is a
scaffold-only fixer that inserts a stub handler with obvious placeholder
values and a loud `# TODO(mcp-migrate): fill in your real capabilities` --
confidence `review`, never `safe`. It's also plausible this rule should
stay fixer-less; say so in the PR if you land there.

**What "done" looks like:** either a scaffold-inserting `Fixer` subclass
with fixtures/tests per `tests/test_fixers.py`, or a documented decision
that this stays fixer-less.

See CONTRIBUTING.md#add-a-fixer-45-minutes.
BODY_END
### ISSUE_END

### ISSUE_START
TITLE: Fixer: ping removed (R011)
LABELS: good first issue,fixer
DIFFICULTY: medium (~30-45 min)
BODY_START
No fixer exists yet for R011 ([`src/mcp_migrate/rules/r011_ping_removed.py`](../../src/mcp_migrate/rules/r011_ping_removed.py)),
which flags the removed `ping`/`PingRequest` request-response.

**Spec:** SEP-2575 -- https://modelcontextprotocol.io/specification/2026-07-28/changelog

**A reasonable scope:** this is close in shape to the shipped
`r001_session_id.py` fixer -- comment out the dead `PingRequest` handler
(and/or the `method == "ping"` dispatch branch) with a
`# TODO(mcp-migrate): ...` pointing at `cookbook/06-ping-removed.md`, being
careful (like R001's fixer) never to comment out a block-opener line that
would leave a dangling suite.

**What "done" looks like:** a `Fixer` subclass in `src/mcp_migrate/fixers/`,
`review` confidence, with fixtures and tests per `tests/test_fixers.py`.

See CONTRIBUTING.md#add-a-fixer-45-minutes.
BODY_END
### ISSUE_END

### ISSUE_START
TITLE: Fixer: logging/setLevel removed (R012)
LABELS: good first issue,fixer
DIFFICULTY: medium (~30-45 min)
BODY_START
No fixer exists yet for R012 ([`src/mcp_migrate/rules/r012_logging_set_level_removed.py`](../../src/mcp_migrate/rules/r012_logging_set_level_removed.py)),
which flags the removed `logging/setLevel` request.

**Spec:** SEP-2575 -- https://modelcontextprotocol.io/specification/2026-07-28/changelog

**A reasonable scope:** same pattern as the R011 fixer issue above -- comment
out the dead `SetLevelRequest` handler, leave a `# TODO(mcp-migrate): ...`
pointing at `cookbook/07-logging-set-level-removed.md`.

**What "done" looks like:** a `Fixer` subclass in `src/mcp_migrate/fixers/`,
`review` confidence, with fixtures and tests per `tests/test_fixers.py`.

See CONTRIBUTING.md#add-a-fixer-45-minutes.
BODY_END
### ISSUE_END

### ISSUE_START
TITLE: Fixer: resources/subscribe and resources/unsubscribe replaced (R013)
LABELS: good first issue,fixer
DIFFICULTY: hard (~60-90 min)
BODY_START
No fixer exists yet for R013 ([`src/mcp_migrate/rules/r013_subscriptions_replaced.py`](../../src/mcp_migrate/rules/r013_subscriptions_replaced.py)),
which flags the removed `resources/subscribe`/`resources/unsubscribe`
methods, replaced by `subscriptions/listen`.

**Spec:** SEP-2575 -- https://modelcontextprotocol.io/specification/2026-07-28/changelog

**Why this is hard:** unlike a rename, the new shape genuinely collapses two
handlers (subscribe, unsubscribe) plus a notification stream into one
long-lived listen call -- see `cookbook/04-subscribe-to-subscriptions-listen.md`
for the shape. A safe fixer probably can't rewrite this correctly in
general; a `review`-confidence TODO-annotation on the old handlers
(matching the R001/R009/R011/R012 fixer pattern) is the most defensible
starting scope.

**What "done" looks like:** a `Fixer` subclass in `src/mcp_migrate/fixers/`
with whatever scope you can defend as genuinely mechanical, with fixtures
and tests per `tests/test_fixers.py`.

See CONTRIBUTING.md#add-a-fixer-45-minutes.
BODY_END
### ISSUE_END

### ISSUE_START
TITLE: Fixer: required resultType missing (R015)
LABELS: good first issue,fixer
DIFFICULTY: hard (~45-60 min, may not be safely automatable)
BODY_START
No fixer exists yet for R015 ([`src/mcp_migrate/rules/r015_result_type_required.py`](../../src/mcp_migrate/rules/r015_result_type_required.py)),
which flags result-returning handlers missing the required `resultType`
field.

**Spec:** SEP-2322 -- https://modelcontextprotocol.io/specification/2026-07-28/changelog

**Why this is hard:** the correct value (`"complete"` vs `"input_required"`)
depends on what the specific handler actually does, and blindly inserting
`"resultType": "complete"` into every `return`/dict literal in a file risks
being *wrong* for a handler that genuinely needs another round trip --
which is arguably worse than the missing field, since it looks fixed. See
`cookbook/05-result-type-and-cache-metadata.md` for the distinction.

**What "done" looks like:** either a narrowly-scoped `safe` fixer for the
one shape you're confident is always `"complete"` (if you can identify
one), or a documented decision that this rule stays fixer-less because
guessing the value is unsafe. Either way, fixtures/tests per
`tests/test_fixers.py` if code ships.

See CONTRIBUTING.md#add-a-fixer-45-minutes.
BODY_END
### ISSUE_END

### ISSUE_START
TITLE: Fixer: ttlMs/cacheScope missing on list/read results (R016)
LABELS: good first issue,fixer
DIFFICULTY: hard (~45-60 min, may not be safely automatable)
BODY_START
No fixer exists yet for R016 ([`src/mcp_migrate/rules/r016_cacheable_result_required.py`](../../src/mcp_migrate/rules/r016_cacheable_result_required.py)),
which flags list/read handlers missing `ttlMs`/`cacheScope`.

**Spec:** SEP-2549 -- https://modelcontextprotocol.io/specification/2026-07-28/changelog

**Why this is hard:** both values are judgment calls specific to the data
being cached (how often does this list change? does it vary per-client?).
A fixer that inserts a wrong `cacheScope` could cause one client's data to
be served from another client's cache -- silently corrupting behavior,
which is exactly the failure mode this project's fixers are built to avoid.
See `cookbook/05-result-type-and-cache-metadata.md`.

**What "done" looks like:** either a fixer that inserts conservative
placeholder values with a loud `# TODO(mcp-migrate): confirm this TTL/scope
is correct` (review confidence, never safe), or a documented decision that
this rule stays fixer-less. Fixtures/tests per `tests/test_fixers.py` if
code ships.

See CONTRIBUTING.md#add-a-fixer-45-minutes.
BODY_END
### ISSUE_END

### ISSUE_START
TITLE: Fixer: server-initiated calls replaced by Multi Round-Trip Requests (R018)
LABELS: good first issue,fixer
DIFFICULTY: hard (~90+ min, may not be safely automatable)
BODY_START
No fixer exists yet for R018 ([`src/mcp_migrate/rules/r018_multi_round_trip_replaces_server_initiated.py`](../../src/mcp_migrate/rules/r018_multi_round_trip_replaces_server_initiated.py)),
which flags server-initiated `roots/list`, `sampling/createMessage` and
`elicitation/create` -- all replaced by Multi Round-Trip Requests.

**Spec:** SEP-2322 -- https://modelcontextprotocol.io/specification/2026-07-28/changelog

**Why this is hard:** this is a genuine control-flow rewrite (a blocking
call becomes two separate request/response pairs correlated by a client
retry -- see `cookbook/10-multi-round-trip-requests.md`), not a rename or
an added field. It is very unlikely a text-level fixer can do this safely
in general.

**What "done" looks like:** most likely, a documented decision that this
rule stays fixer-less, backed by the cookbook recipe instead (make sure
`cookbook/10-multi-round-trip-requests.md` is filled in first -- see the
matching cookbook issue). If you find a genuinely narrow, safe subset
(e.g. annotating the call site with a TODO), that's welcome too, with
fixtures/tests per `tests/test_fixers.py`.

See CONTRIBUTING.md#add-a-fixer-45-minutes.
BODY_END
### ISSUE_END

### ISSUE_START
TITLE: Fixer: tasks/list and blocking tasks/result removed (R019)
LABELS: good first issue,fixer
DIFFICULTY: hard (~60-90 min)
BODY_START
No fixer exists yet for R019 ([`src/mcp_migrate/rules/r019_tasks_polling_replaces_blocking_result.py`](../../src/mcp_migrate/rules/r019_tasks_polling_replaces_blocking_result.py)),
which flags removed `tasks/list` and the removed blocking `tasks/result`.

**Spec:** SEP-2663 -- https://modelcontextprotocol.io/specification/2026-07-28/changelog

**Why this is hard:** converting a blocking wait into a `tasks/get` +
`tasks/update` polling loop is a real control-flow rewrite (see
`cookbook/11-tasks-polling.md`), not a mechanical edit. A `review`-confidence
TODO-annotation on the old handler (same pattern as the R009/R011/R012/R013
fixer issues) is the most defensible starting scope.

**What "done" looks like:** a `Fixer` subclass in `src/mcp_migrate/fixers/`
with whatever scope you can defend as genuinely mechanical, with fixtures
and tests per `tests/test_fixers.py`.

See CONTRIBUTING.md#add-a-fixer-45-minutes.
BODY_END
### ISSUE_END

### ISSUE_START
TITLE: Fixer: Dynamic Client Registration deprecated (R020)
LABELS: good first issue,fixer
DIFFICULTY: medium (~45 min)
BODY_START
No fixer exists yet for R020 ([`src/mcp_migrate/rules/r020_dynamic_client_registration_deprecated.py`](../../src/mcp_migrate/rules/r020_dynamic_client_registration_deprecated.py)),
which flags RFC 7591 Dynamic Client Registration usage (`register_client`,
`RegisterClientRequest`, `DynamicClientRegistration`).

**Spec:** https://modelcontextprotocol.io/specification/2026-07-28/changelog

**A reasonable scope:** since `deprecated` (not `breaking`) and migrating
off DCR requires standing up a real Client ID Metadata Document, a
mechanical fixer probably can't do the migration itself -- but it could
annotate the flagged code with a `# TODO(mcp-migrate): ...` pointing at
`cookbook/12-dynamic-client-registration-deprecated.md`, matching the
TODO-annotation pattern used elsewhere in this project.

**What "done" looks like:** a `Fixer` subclass in `src/mcp_migrate/fixers/`
using that pattern, `review` confidence, with fixtures and tests per
`tests/test_fixers.py`.

See CONTRIBUTING.md#add-a-fixer-45-minutes.
BODY_END
### ISSUE_END

### ISSUE_START
TITLE: Fixer: older JSON Schema dialect pinned (R021)
LABELS: good first issue,fixer
DIFFICULTY: easy (~30-45 min)
BODY_START
No fixer exists yet for R021 ([`src/mcp_migrate/rules/r021_json_schema_2020_12_required.py`](../../src/mcp_migrate/rules/r021_json_schema_2020_12_required.py)),
which flags an explicit older JSON Schema dialect (`draft-07`, `2019-09`,
...) pinned via a `$schema` URL string.

**Spec:** SEP-2106 -- https://modelcontextprotocol.io/specification/2026-07-28/changelog

**A reasonable scope:** this is one of the more mechanical ones in this
list, similar in spirit to the shipped R017 fixer -- rewriting an old
`$schema` dialect URL string to the 2020-12 equivalent
(`http://json-schema.org/draft/2020-12/schema`) is a close-to-exact string
substitution once you're confident the match is a real `$schema` value and
not, say, a comment mentioning an old draft. Confidence `safe` is plausible
here if you scope it tightly (e.g. only rewrite when the match is inside a
`"$schema":` key's value).

**What "done" looks like:** a `Fixer` subclass in `src/mcp_migrate/fixers/`,
with fixtures and tests per `tests/test_fixers.py`, including a fixture that
proves the fixer backs off on an ambiguous shape (the dialect string
appearing somewhere that isn't clearly a `$schema` value).

See CONTRIBUTING.md#add-a-fixer-45-minutes.
BODY_END
### ISSUE_END
