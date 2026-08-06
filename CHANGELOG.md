# Changelog

All notable changes to this project are documented here.

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
- **The badge endpoints are generated but not yet served** until GitHub Pages
  is publishing `docs/`.

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
