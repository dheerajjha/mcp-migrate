# Changelog

All notable changes to this project are documented here.

## [Unreleased]

**TypeScript coverage went from 17 of 21 rules to 20, the fixer set from ten
to sixteen, and the cookbook from six recipes to eighteen.** All of it was
contributed.

### Added

- **R013, R014 and R021 read TypeScript**, leaving **R002** as the only
  Python-only rule. R013 uses a bounded `(?:Schema|Params)` suffix rather
  than `\w*`, so `class SubscribeRequester` no longer reads as a removed
  subscription handler.
  ([#42](https://github.com/dheerajjha/mcp-migrate/issues/42),
  [#43](https://github.com/dheerajjha/mcp-migrate/issues/43),
  [#50](https://github.com/dheerajjha/mcp-migrate/issues/50), @waterlemonnn)
- **Three more fixers** — **R009** (initialize handshake), **R011** (ping) and
  **R012** (`logging/setLevel`) — taking the set to **16 of 21**. Only R002,
  R003, R010, R015 and R016 now lack one.
  ([#19](https://github.com/dheerajjha/mcp-migrate/issues/19),
  [#21](https://github.com/dheerajjha/mcp-migrate/issues/21),
  [#22](https://github.com/dheerajjha/mcp-migrate/issues/22), @waterlemonnn)

  All three bound their identifier suffix rather than using `\w*`, so
  `PingRequester` and `SetLevelRequesterFactory` are left alone. **The rules
  still match those** — that is [#87](https://github.com/dheerajjha/mcp-migrate/issues/87),
  still open — so `check` reports a line `fix` declines to touch. That
  asymmetry is deliberate: a wrong finding costs a reader ten seconds, a
  wrong `--write` costs them working code.
- **Three new fixers**, taking the set from ten to thirteen: **R013**
  (`resources/subscribe` removal), **R008** (trace context) and **R018**
  (Multi Round-Trip Requests), all `review` confidence.
  ([#23](https://github.com/dheerajjha/mcp-migrate/issues/23),
  [#18](https://github.com/dheerajjha/mcp-migrate/issues/18),
  [#26](https://github.com/dheerajjha/mcp-migrate/issues/26), @waterlemonnn)

  R008 and R018 **annotate without commenting out**, which is the right
  split: the code they flag is not wrong, it is incomplete. Commenting out
  a span or a `list_roots()` call would break a working server to point at
  a migration step. R013 does comment out, because a `SubscribeRequest`
  handler is dead once the method is gone.
- **The cookbook is finished.** Twelve recipes written: ping removed,
  `logging/setLevel` removed, SSE resumability, resource-not-found error
  code, Multi Round-Trip Requests, tasks polling, Dynamic Client
  Registration, JSON Schema 2020-12, deterministic `tools/list` ordering,
  the `extensions` map, trace context propagation, and Roots/Sampling/
  Logging deprecation. All eighteen slots are now written; there are no
  stubs left. (@waterlemonnn)
- **`check --json` now has an executable schema contract** in
  `schemas/check-json.schema.json`, documented in the README and validated
  against clean, legacy, unscannable, and SDK outputs. Pre-1.0 compatibility
  policy is stated next to the contract so external consumers know breaking
  shape changes will be documented under Changed.
  ([#188](https://github.com/dheerajjha/mcp-migrate/issues/188))

### Changed

- **`check --json` drops the `location` key. This breaks scripts.** A
  finding used to carry `"location": "server.py:12"`; it now carries
  `"path": "server.py"` and `"line": 12` separately. The combined string
  forced every consumer to re-parse something we already had structured,
  and it was ambiguous the moment a path contained a colon. Findings also
  gain `fix` (the rule's remediation text), and the document gains `tool`,
  `version` and a `counts` object.

  `location` shipped in 0.1.0 through 0.1.4. **If you parse `--json`, this
  is the one thing in this release that will break you** — nothing in this
  repository still reads it, but external scripts are not visible from
  here. ([#85](https://github.com/dheerajjha/mcp-migrate/issues/85),
  @waterlemonnn)

  For the record, #85 as filed claimed there was no machine-readable
  output at all. That was wrong — `--json` has existed since the first
  commit. The PR corrected the premise and improved the schema instead.

### Fixed

- **R014 missed most spellings of its own identifier.** The TypeScript path
  matched case-sensitively, so `lastEventId` was found and `lastEventID`,
  `LAST_EVENT_ID` and `last_event_id` were not. Now one bounded pattern,
  `\blast_?event_?id\b`, matched case-insensitively — the `_?` covers the
  SCREAMING_SNAKE form, which the flag alone would still have missed.
  `lastEventIdentifier` and `lastEventIds` stay silent.
  ([#143](https://github.com/dheerajjha/mcp-migrate/issues/143),
  @ujjwalprakash17 — found by @PuvaanRaaj's independent port in #60)
- **Generated `.d.mts` and `.d.cts` were scanned and graded.** Only `.d.ts`
  was excluded, so a project on `"type": "module"` had its emitted
  declarations read. Those files are dense with SDK type re-exports, which
  is the shape several rules match on — so this added findings that fed the
  score, not merely noise.
- **`languages.py` claimed the tool only reads Python** (untrue since 0.1.3)
  and described a grade as a claim about "the 19 rules that didn't run"
  when it is now one. The replacement carries no count deliberately.
- **R017 discarded its own `re.IGNORECASE`**, so it found
  `"resource not found"` and missed `"Resource Not Found"`. The flag sat on
  the compiled object while only `.pattern` was passed to `search_wire`,
  which recompiles with `flags=0`.
  ([#123](https://github.com/dheerajjha/mcp-migrate/issues/123),
  @waterlemonnn)
- **R015 fired on JSON-RPC *requests***, telling you to add `resultType` to
  an object that must not carry it. `id` + `method` with no `result`/`error`
  key is a request; the rule now requires evidence of a response before
  firing. ([#91](https://github.com/dheerajjha/mcp-migrate/issues/91),
  partially — R004 and R016 are still open. @waterlemonnn)
- **The cookbook index listed recipe 16 as an unwritten stub** while its
  recipe was complete, showed five recipes as having no fixer when R007,
  R014, R019, R020 and R021 all ship one, and still said five rules have
  fixers when ten have since 0.1.3.

### Known issues

- **The three false-positive classes from 0.1.4 are still open**:
  [#87](https://github.com/dheerajjha/mcp-migrate/issues/87) (unbounded
  `\w*` suffixes), [#88](https://github.com/dheerajjha/mcp-migrate/issues/88)
  (wire patterns without an end boundary),
  [#89](https://github.com/dheerajjha/mcp-migrate/issues/89) ("is this MCP?"
  decided too loosely).

### Contributors

@waterlemonnn wrote most of the above. @ujjwalprakash17's first PR fixed
R014's case handling; @PuvaanRaaj's #56/#58/#60 were an independent take on
the same three TypeScript ports, and #60 was measurably right about
case-insensitivity -- that half became
[#143](https://github.com/dheerajjha/mcp-migrate/issues/143), which
@ujjwalprakash17 then closed.

## [0.1.4] - 2026-08-06

**A correctness release. Two of these are the kind you upgrade for rather
than read about:** `fix --write` was corrupting TypeScript source, and no
TypeScript project could fail a CI build. Both were present in 0.1.3.
Everything here was contributed.

### Added

- **Live badge endpoints.** `scripts/render_badges.py` turns the registry into
  [shields.io endpoint](https://shields.io/badges/endpoint-badge) documents, so
  a badge reports the grade at request time instead of the grade at the moment
  someone pasted a URL. Addressed per-entry and per-repo; where a repo holds
  several servers the badge reports the **worst** grade with a count, because
  "something in here is an F" is the fact a reader needs and averaging hides
  it. Unlisted repos get a real `not listed` badge rather than a broken image.
  ([#101](https://github.com/dheerajjha/mcp-migrate/issues/101), @djubx)
- **R017 reads TypeScript**, taking coverage to 17 of 21 rules. No language
  branch needed — the qualifying context is a numeric literal plus nearby
  English, not a language-specific identifier.
  ([#46](https://github.com/dheerajjha/mcp-migrate/issues/46), @waterlemonnn)
- **A regression guard against quadratic scans.** `tests/test_scan_complexity.py`
  counts `search_*` calls rather than timing them: a correctly-written rule
  issues the same number of calls at 20 files as at 200, so the assertion needs
  no tolerance and cannot flake on shared CI runners.
  ([#86](https://github.com/dheerajjha/mcp-migrate/issues/86), @s35153)

### Fixed

- **`fix --write` corrupted TypeScript.** Five fixers emitted Python `#`
  comments regardless of the file being edited, so on a `.ts` file they wrote
  lines that are a syntax error — and the tool reported success on its way out.
  The prefix is now derived from the file once, in `fixers/base.py`, rather
  than remembered correctly by each fixer independently. Also covers
  `.mts`/`.cts`/`.mjs`/`.cjs`, which the scanner reads and the one previously
  correct fixer missed.
  ([#117](https://github.com/dheerajjha/mcp-migrate/issues/117), @Vicky-Jha)
- **Every TypeScript project exited `2`**, meaning "could not check", so a
  breaking finding could not fail a build. Exit codes are now derived from
  findings whenever files were actually read; `2` is reserved for trees where
  nothing was read at all. The "Nothing scannable here." headline is likewise
  reserved for that case.
  ([#98](https://github.com/dheerajjha/mcp-migrate/issues/98), @iphonekumar)
- **R003 re-ran a whole-project scan inside its per-file loop**, the same
  quadratic shape as #67. Found by the new complexity guard on its first run.
  ([#86](https://github.com/dheerajjha/mcp-migrate/issues/86), @s35153)
- **R010 could be silenced by a comment.** A `# TODO: server/discover is not
  implemented yet` satisfied the Python "does this project already implement
  it?" check, so the more clearly a project documented the gap, the more
  certain R010 was that there wasn't one. Now routed through `search_wire`,
  which keeps string literals and drops prose. A genuine wire-name literal
  still suppresses correctly. ([#113](https://github.com/dheerajjha/mcp-migrate/issues/113),
  @waterlemonnn)
- **R018 and R019 were blind to the TypeScript SDK schema names**, which is
  the spelling real servers actually write —
  `server.setRequestHandler(ListTasksRequestSchema, ...)` never contains the
  wire string, so a wire-only search saw nothing. Both now run a
  `search_code` pass alongside the wire pass, bounded to the exact SDK
  exports so this doesn't reintroduce
  [#87](https://github.com/dheerajjha/mcp-migrate/issues/87). R018 also picks
  up `elicitationId` on the TypeScript path, which the Python path already
  had. ([#99](https://github.com/dheerajjha/mcp-migrate/issues/99), partially
  — the Python `Params`/`Result` variants are still open. @waterlemonnn)

### Known issues

Still real, still shipping, listed because they are.

- **TypeScript is scanned but not graded.** 17 of 21 rules read it, which is
  enough to report findings and fail a build but not enough to stand behind a
  letter grade. Still Python-only: **R002, R013, R014, R021**.
- **Three false-positive classes remain**, affecting both languages: unbounded
  `\w*` suffixes matching unrelated identifiers
  ([#87](https://github.com/dheerajjha/mcp-migrate/issues/87)), wire patterns
  without an end boundary so `"roots/listeners"` matches `roots/list`
  ([#88](https://github.com/dheerajjha/mcp-migrate/issues/88)), and five rules
  deciding "is this MCP?" too loosely
  ([#89](https://github.com/dheerajjha/mcp-migrate/issues/89)). Fixes are in
  flight. Treat a finding as a prompt to look, not as a verdict.
- **R017 discards its own `re.IGNORECASE`**
  ([#123](https://github.com/dheerajjha/mcp-migrate/issues/123)), so it finds
  `"resource not found"` but misses `"Resource Not Found"`. A false negative,
  not a false positive.
- **Badge endpoints report the grade from the last registry scan**, not from a
  fresh scan of your repo. They update when the Board workflow regenerates
  them, which is what makes them live relative to the old baked-in image —
  but a grade there can still lag your `main`.

### Contributors

@Vicky-Jha, @iphonekumar, @waterlemonnn, @s35153, @djubx — plus
@li2631026381-alt, whose closed PR surfaced
[#123](https://github.com/dheerajjha/mcp-migrate/issues/123).

Every fix in this release came from outside the repo.

## [0.1.3] - 2026-08-05

**TypeScript scanning, which did not exist in 0.1.2.** Sixteen of the
twenty-one rules now read TypeScript as well as Python, and the fixer set has
doubled. Every rule port in this release was contributed.

### Added

**TypeScript support (new).** 0.1.2 scanned Python only — `SUPPORTED` was
`{"python"}` and no rule read anything else. 0.1.3 adds a TypeScript backend
with comment- and string-aware content spans, and ports sixteen rules onto it:

| Rule | What it finds | Contributed by |
|---|---|---|
| R001 | `Mcp-Session-Id` after sessions were removed | @dheerajjha (reference port) |
| R003 | Missing `Mcp-Method` / `Mcp-Name` routing headers | @atiqur-rahman-pro |
| R004 | Nondeterministic `tools/list` ordering | @atiqur-rahman-pro |
| R005 | No `extensions` declared on `ServerCapabilities` | @MasRama |
| R006 | Deprecated SSE transport | @dheerajjha (reference port) |
| R007 | Roots / Sampling / Logging deprecated as core | @s35153 |
| R008 | OpenTelemetry trace context not propagated from `_meta` | @djubx |
| R009 | `initialize` handshake still implemented | @dheerajjha |
| R010 | `server/discover` missing | @resuaico |
| R011 | Removed `ping` | @MasRama |
| R012 | Removed `logging/setLevel` | @PuvaanRaaj |
| R015 | Required `resultType` missing | @syf2211 |
| R016 | `ttlMs` / `cacheScope` missing on list/read results | @syf2211 |
| R018 | Multi Round-Trip Requests replace server-initiated calls | @PuvaanRaaj |
| R019 | Removed `tasks/list` and blocking `tasks/result` | @PuvaanRaaj |
| R020 | Dynamic Client Registration deprecated | @syf2211 |

Still Python-only: **R002, R013, R014, R017, R021**.

**Five new fixers**, taking the set from five to ten:

| Fixer | Confidence | What it does | Contributed by |
|---|---|---|---|
| R007 | review | Annotates deprecated Roots/Sampling/Logging usage with a TODO | @syf2211 |
| R014 | review | Comments out Last-Event-ID resumability plumbing, leaves a TODO | @syf2211 |
| R019 | review | Comments out removed `tasks/list` / blocking `tasks/result`, leaves a TODO | @syf2211 |
| R020 | review | Annotates RFC 7591 Dynamic Client Registration with a CIMD migration TODO | @IronLad123 |
| R021 | safe | Rewrites older `$schema` dialect pins to `https://json-schema.org/draft/2020-12/schema` | @IronLad123 |

R020 is the first fixer that emits the correct comment marker for TypeScript
(`//`) as well as Python (`#`).

### Fixed

- **R001** used a raw search for identifier patterns in TypeScript, so a
  docstring mentioning `Mcp-Session-Id` counted as a usage. Now routed through
  `search_code`. (@lesbass)
- **R004** scoped its `tools/list` check with a fixed line window, which both
  missed and over-matched depending on formatting. Replaced with a brace-depth
  scan. (@atiqur-rahman-pro)
- **R016** let a comment mentioning `ttlMs` / `cacheScope` silence a real
  finding. The mention check now runs through content spans. (@IronLad123)
- **`*.examples.ts`** files are skipped by default. They are documentation
  synced into JSDoc comments by a build script, not shipped server code.
  (@KhyFee)

### Performance

- **R015** hoisted its TypeScript `search_wire` scans out of the per-file loop,
  removing a quadratic scan on large trees. (@li2631026381-alt)

### Known issues

Listed because they are real and shipping, not because they are acceptable.

- **TypeScript projects always exit `2`.**
  ([#98](https://github.com/dheerajjha/mcp-migrate/issues/98)) `2` means
  "could not check", so a TypeScript project with a breaking finding does not
  fail a build. The findings are printed correctly; only the exit code is
  wrong. If you are wiring this into CI for a TypeScript server today, parse
  the output rather than trusting the status.
- **TypeScript is scanned but not graded.** Sixteen of twenty-one rules is
  enough to report findings and not enough to stand behind a letter grade, so
  no grade and no badge is issued for TypeScript trees. This is deliberate.
- **Four known false-positive classes remain**, affecting both languages:
  unbounded `\w*` suffixes matching unrelated identifiers
  ([#87](https://github.com/dheerajjha/mcp-migrate/issues/87)), wire patterns
  without an end boundary so `"roots/listeners"` matches `roots/list`
  ([#88](https://github.com/dheerajjha/mcp-migrate/issues/88)), five rules
  deciding "is this MCP?" too loosely
  ([#89](https://github.com/dheerajjha/mcp-migrate/issues/89)), and three rules
  reporting correct code that is spelled indirectly
  ([#91](https://github.com/dheerajjha/mcp-migrate/issues/91)). Fixes are in
  flight. Treat a finding as a prompt to look, not as a verdict.
- **R010 can be silenced by a comment.**
  ([#113](https://github.com/dheerajjha/mcp-migrate/issues/113)) On the Python
  path, a comment mentioning `server/discover` satisfies the
  "does this project already implement it?" check.

### Contributors

@syf2211, @atiqur-rahman-pro, @PuvaanRaaj, @MasRama, @IronLad123,
@li2631026381-alt, @lesbass, @djubx, @KhyFee, @s35153.

Every TypeScript rule port and four of the five new fixers in this release came
from outside the repo.

## [0.1.2] - 2026-08-01

Python-only. Twenty-one rules, five fixers (R001, R004, R005, R006, R017),
letter grading and the registry board.

[0.1.4]: https://github.com/dheerajjha/mcp-migrate/releases/tag/v0.1.4
[0.1.3]: https://github.com/dheerajjha/mcp-migrate/releases/tag/v0.1.3
[0.1.2]: https://github.com/dheerajjha/mcp-migrate/releases/tag/v0.1.2
