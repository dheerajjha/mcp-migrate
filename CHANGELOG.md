# Changelog

All notable changes to this project are documented here.

## [Unreleased]

### Fixed

- **The badge `check` prints and the board's live badges disagreed on
  colour.** `grade.py`'s `BADGE_COLOR` (what `badge_url()` suggests you
  paste) and `render_badges.py`'s `GRADE_COLOR` (what actually renders
  under `docs/badge/`) had drifted apart on B and D — a B rendered green
  from the CLI and brightgreen on the board, and on the board A and B were
  the same colour. `render_badges.py` now imports `BADGE_COLOR` from
  `grade.py` instead of keeping its own copy, so there is one map, not two
  that can disagree. ([#224](https://github.com/dheerajjha/mcp-migrate/issues/224))

## [0.3.0] - 2026-08-08

### Added

- **SARIF 2.1.0 output: `check --format sarif`.** Findings land in GitHub
  code scanning as annotations on the diff and entries in the Security tab,
  tracked across commits instead of re-read from a CI log every time.
  ([#182](https://github.com/dheerajjha/mcp-migrate/issues/182))

  `--format {text,json,sarif}` is the new surface; `--json` keeps working as
  an alias for `--format json` and its output is byte-identical. The format
  decides what is printed and never what is returned — exit codes are
  unchanged across all three.

  Two decisions worth stating rather than burying:

  - **`deprecated` maps to `warning`, not `error`.** Code scanning's default
    gate fails on `error` alone, so this mapping decides whether a
    deprecation blocks a merge. The spec gives deprecated features 12+
    months; making a server unmergeable today over something that breaks
    next year gets the integration switched off, and then it catches
    nothing. `breaking` → `error` and `advisory` → `note`.
  - **The driver declares all 21 rules, not only those that fired.** That is
    what lets code scanning tell "this rule ran and found nothing" from
    "this rule does not exist", and therefore close a resolved alert instead
    of leaving it open forever. A clean tree still emits a full run with
    `results: []`.

  Paths are repo-relative and forward-slashed on every platform, because
  code scanning matches results to the diff by path and an absolute path
  from the scanning machine matches nothing — the annotations would silently
  never appear. Project-level findings (R010 asks about the whole tree) are
  kept with an empty `locations` array rather than dropped.

  Validated in CI against a vendored copy of the official schema at
  `schemas/sarif-2.1.0.schema.json`; it is checked in rather than fetched so
  the suite does not depend on the network across four Python versions.
- **Inline suppression: `# mcp-migrate: ignore[R001] -- reason`.** Silence a
  single wrong finding without switching a rule off for the whole project.
  Both comment syntaxes, so it reads naturally in Python and TypeScript.
  ([#180](https://github.com/dheerajjha/mcp-migrate/issues/180))

  A suppressed finding does not count against the grade. A suppression that
  still costs you the grade is not a suppression — the only move left would
  be to stop running the tool. That makes the grade partly self-reported, so
  it is auditable by construction rather than by convention:

  - the rule id is required; a blanket `ignore` would also silence rules that
    do not exist yet, and nobody revisits it
  - a reason is expected, and directives without one are reported
  - the suppression count prints on every run, never behind a flag
  - `--show-suppressions` lists each one with its file, rule and reason
  - directives that matched nothing are reported, so stale ones cannot
    quietly accumulate

  Malformed directives are reported rather than dropped: someone wrote it
  believing it worked, and the finding it was meant to silence is about to
  appear anyway.

  `R005`, `R015` and `R016` report at most one finding per file, so
  suppressing their line silences those rules for that whole file. Documented
  in the README; every other rule is genuinely per-line.

- **A registry entry records what its grade was computed from.**
  `mcp-migrate entry` emits an optional `suppressed:` count when the scan
  had any, `registry/schema.yaml` accepts it, `validate_registry.py`
  enforces a non-negative int, and the board marks those rows.
  ([#220](https://github.com/dheerajjha/mcp-migrate/issues/220), @soltonigiri)

  Suppression deliberately does not cost the grade, and that decision was
  fine while the number stayed in a terminal. It stopped being fine the
  moment the same grade could be submitted to a public board with nothing
  anywhere recording that findings were silenced — the board's whole claim
  is that its grades are reproducible, and a grade you cannot reproduce
  without knowing what was suppressed does not meet that bar.

  Optional and omitted when zero, so the sixteen existing entries and the
  rendered board are byte-identical. Whether the **badge** should change is
  a separate and genuinely contested question, still open in
  [discussion #210](https://github.com/dheerajjha/mcp-migrate/discussions/210).

### Changed

- **`check --json` gained two required keys, `suppressed` and
  `unused_suppressions`.** Both are always present, empty array included. A
  consumer validating against the 0.2.0 schema will reject 0.3.0 output until
  it is updated; `schemas/check-json.schema.json` is the executable contract.
  Findings that were suppressed are absent from `findings` and from `counts`,
  so a consumer that sums `counts` still gets a total matching `findings`.

  `unused_suppressions` carries one entry per rule id (`rule`, `path`, `line`,
  `reason`). It is in the JSON and not only on the console because stale
  suppressions accumulate in CI, and CI is exactly the consumer that reads
  `--json` and never sees a console line.

### Fixed

- **Fixers no longer edit inside string literals.** A new
  `string_lines()` helper in `fixers/_textedit.py` marks every line that is
  part of a Python docstring or a TypeScript template literal, and the
  line-based fixers decline to touch them.
  ([#105](https://github.com/dheerajjha/mcp-migrate/issues/105), @IronLad123)

  Two fixers were editing prose. `ResourceNotFoundErrorCodeFixer` rewrote
  `-32002` → `-32602` inside a docstring describing *historical* behaviour —
  at `safe` confidence, leaving the file parseable and the documentation
  wrong, so nothing caught it. `TasksPollingFixer` inserted
  `# TODO(mcp-migrate): ...` into a string literal, where `#` opens no
  comment and the line is simply corrupted. On failure the helper returns
  every line, so an unparseable file makes fixers decline rather than guess.

- **R018 and R019 now match the SDK names real code uses.** They keyed on
  `list_roots`, `create_message`, `ListTasksRequest` and friends, missing the
  `Params`/`Schema`/`Result` variants that appear in actual servers — a file
  importing `ListRootsRequestSchema` or `GetTaskPayloadResultSchema` scanned
  clean for both rules.
  ([#99](https://github.com/dheerajjha/mcp-migrate/issues/99), @IronLad123)

  Known consequence: R007 and R018 now both fire on the `CreateMessage*`
  family, two findings for one symbol at two severities. Both claims are
  true, so neither rule is wrong; the noise is tracked in
  [#221](https://github.com/dheerajjha/mcp-migrate/issues/221).

- **Wire method names are bounded at their end.** A new `wire_method()`
  helper builds `\b<name>(?![\w/-])`, so `roots/listeners`,
  `notifications/initializedAt`, `logging/setLevelPolicy` and
  `tasks/listeners` stop reading as the methods whose names they begin with.
  Five false positives on a four-line file, gone.
  ([#88](https://github.com/dheerajjha/mcp-migrate/issues/88), @IronLad123)

  Applied at each pattern's definition rather than its call site, because
  `WIRE_RX` in R009 and R019 and the `logging/setLevel` literal in R012 each
  feed both the Python and the TypeScript path — bounding only the Python
  call sites left the same file still producing false positives when scanned
  as TypeScript.

- **Two superseded rule modules removed, and a guard so it cannot recur.**
  `r001_session_id.py` and `r006_sse_transport.py` were the 0.1.0
  originals, superseded and never deleted. Both rule ids were declared
  twice, and which implementation went live was decided by filename sort
  order inside `all_rules()` rather than by intent.
  ([#219](https://github.com/dheerajjha/mcp-migrate/issues/219), @ankitverma31)

  Nothing was wrong at runtime — the maintained implementations were the
  live ones and the rule count was 21 either way. But rename the surviving
  module to anything that sorts earlier and the tool silently reverts to a
  superseded rule, with the count unchanged and every test still green.
  `test_rule_hygiene.py` now reads the declarations statically — not
  through `all_rules()`, whose import is where the dedup happens — and
  fails if a rule id is declared twice, or if a rule declared on disk does
  not survive into `all_rules()`.

  The README rule table linked R001 and R006 to the **dead** modules, so
  anyone following those links was reading a superseded implementation.
  Caught by `test_docs.py` the moment the files were removed.

- **R004 no longer fires on a wire method name that returns no tools.**
  Naming `tools/list` is not handling it, and the rule could not tell the
  difference. Three shapes are now excluded: a per-method config map key
  (`{"tools/list": {"ttl_ms": ...}}`), a lookup back into that map
  (`CACHE_POLICY["tools/list"]`), and the `method` field of an outbound
  request (`send({"jsonrpc": "2.0", "method": "tools/list"})` — only
  requests carry `method`, so that is always the client side of the wire).
  Both languages.
  ([#218](https://github.com/dheerajjha/mcp-migrate/issues/218))

  Found by reading `dealfluence/adeu` rather than by trusting our own
  output: **4 of the 5** R004 findings we reported against it were wrong,
  and the config map exists there *because* they implement this revision's
  cache metadata — so the rule was penalising them for correctly
  implementing another part of the same spec. Their grade goes **D (44) →
  C (72)** together with [#217](https://github.com/dheerajjha/mcp-migrate/issues/217).

  Handler shapes all still fire, including the one object-literal key whose
  value opens the handler body on the same line
  (`{"tools/list": async () => ...}`), where the sort look-ahead has
  something real to scan. A key whose value is a bare identifier is skipped
  and the miss accepted: that body lives in another function, so the
  look-ahead was never going to find its sort there anyway. R004 is
  advisory — three wrong points on a stranger's grade cost more than three
  missed ones.

  R015 and R016 were checked for the same trigger and are not affected;
  both anchor on a call-site shape (`setRequestHandler("tools/list", ...)`)
  rather than a bare literal.

## [0.2.0] - 2026-08-07

**Every rule now reads TypeScript** (up from 17 of 21), the fixer set went
from ten to **nineteen**, and the cookbook from six recipes to eighteen.
**JavaScript files are now read** — though no rule reads into them yet.
There is a **pre-commit hook**. All of it was contributed.

### Added

- **A pre-commit hook.** `.pre-commit-hooks.yaml` at the repo root, so this
  drops into a project's `.pre-commit-config.yaml`. `pass_filenames: false`
  is deliberate and documented in the yaml — several rules are
  whole-project questions (R010 asks whether `server/discover` exists
  *anywhere*), and handing them only the staged files would make them
  answer about a partial tree.
  ([#184](https://github.com/dheerajjha/mcp-migrate/issues/184), @ankitverma31)

  The hook runs `mcp-migrate-precommit`, a wrapper whose entire job is
  mapping exit 2 to 0. pre-commit treats any non-zero exit as a failure, so
  wired directly the hook would block every commit in a repository the tool
  cannot read — which is every repository until someone adds their first
  Python or TypeScript file. Exit 1, a breaking finding, still blocks.
  `check` itself is unchanged. Measured at **0.31–0.34s over 600 files**.
- **A fixer for R003** (routing headers), taking the set to **19 of 21** —
  only R010 and R015 lack one now, and R015's absence is a documented
  decision. It recovers `Mcp-Method`/`Mcp-Name` from the call site where it
  can and annotates where it cannot; it never invents a value.
  ([#16](https://github.com/dheerajjha/mcp-migrate/issues/16), @syf2211)
- **JavaScript source is loaded.** `.js`/`.jsx`/`.mjs`/`.cjs` were counted by
  `survey()` and never opened by `load_project()`, so a plain-JS server was
  reported on with zero findings because nothing was read — not because
  nothing was wrong. They now load and route through the TypeScript
  comment/string span scanner, so `//` is recognised as a comment rather
  than falling through to the Python tokenizer.
  ([#149](https://github.com/dheerajjha/mcp-migrate/issues/149), @aryansk)

  **No rule declares `javascript` yet** (0 of 21), so these projects still
  exit 2. Porting the rules is [#149](https://github.com/dheerajjha/mcp-migrate/issues/149),
  reopened; R006, R017 and R021 are one-line changes.
- **Two more fixers** — **R002** (per-connection state dicts) and **R016**
  (missing `ttlMs`/`cacheScope`) — taking the set to **18 of 21**. Only
  R003, R010 and R015 now lack one, and R015's absence is now a documented
  decision rather than a gap.
  ([#14](https://github.com/dheerajjha/mcp-migrate/issues/14),
  [#25](https://github.com/dheerajjha/mcp-migrate/issues/25),
  [#24](https://github.com/dheerajjha/mcp-migrate/issues/24), @waterlemonnn)

  Neither invents a value. R002 annotates the declaration and leaves it
  intact — choosing a store and a key shape is architectural. R016 never
  writes `ttlMs`/`cacheScope`, because a `cacheScope` guessed too wide can
  serve one client's cached data to another.
- **The docs are now checked against the code.** `tests/test_docs.py`
  verifies the cookbook index, the README rule table and every fixer's
  `COOKBOOK`/`SPEC_URL` pointer against `all_rules()`/`all_fixers()`.
  ([#174](https://github.com/dheerajjha/mcp-migrate/issues/174), @waterlemonnn)

  It caught two real drifts on its first run, both introduced hours
  earlier by the R002 and R016 fixers above: a fixer shipped, one of the
  three doc surfaces got updated, and the other two went on saying it did
  not exist. It also fixed eleven README rows that had claimed `no` for
  rules that had shipped fixers, some of them the same day.
- **Two static guards against traps that already bit us.**
  `test_rule_hygiene.py` walks the rule modules for
  `search_*(RX.pattern)` calls that drop a compiled flag — the shape of
  [#123](https://github.com/dheerajjha/mcp-migrate/issues/123) and
  [#143](https://github.com/dheerajjha/mcp-migrate/issues/143), neither of
  which any test caught. `test_typescript.py` now asserts that every rule
  declaring `typescript` is actually exercised on a `.ts` file, so a
  one-line language claim cannot go unverified.
  ([#173](https://github.com/dheerajjha/mcp-migrate/issues/173),
  [#177](https://github.com/dheerajjha/mcp-migrate/issues/177), @waterlemonnn)
- **`scripts/benchmark.py`** — wall-clock timing per phase (walk / load /
  rules), the half `test_scan_complexity.py` deliberately leaves out. It
  measured a real cost rather than a hypothetical one: `survey()` prunes
  `node_modules` via `os.walk`, `load_project()` does not, so 5000 vendored
  files took `load` from ~1.4s to ~6.3s.
  ([#185](https://github.com/dheerajjha/mcp-migrate/issues/185), @waterlemonnn)
- **Two more servers on the board** — `arxiv-mcp-server` and
  `excel-mcp-server`, both B, taking it to **16**. Both reproduced from a
  clean checkout at the stated commit before merging.
  ([#186](https://github.com/dheerajjha/mcp-migrate/issues/186), @waterlemonnn)

- **Every rule reads TypeScript.** R013, R014 and R021 landed first
  (@waterlemonnn), then **R002** — the last holdout — closed the gap
  (@IronLad123). R013 uses a bounded `(?:Schema|Params)` suffix rather than
  `\w*`, so `class SubscribeRequester` no longer reads as a removed
  subscription handler.
  ([#42](https://github.com/dheerajjha/mcp-migrate/issues/42),
  [#43](https://github.com/dheerajjha/mcp-migrate/issues/43),
  [#50](https://github.com/dheerajjha/mcp-migrate/issues/50),
  [#32](https://github.com/dheerajjha/mcp-migrate/issues/32))

  **This does not yet mean TypeScript gets a grade.** The `PARTIAL` flag
  still withholds it -- that part is unchanged. What `check` says about
  *why* is fixed below ([#172](https://github.com/dheerajjha/mcp-migrate/issues/172)).
- **Three more fixers** — **R009** (initialize handshake), **R011** (ping) and
  **R012** (`logging/setLevel`) — taking the set to **16 of 21**. Only R002,
  R003, R010, R015 and R016 now lack one.
  ([#19](https://github.com/dheerajjha/mcp-migrate/issues/19),
  [#21](https://github.com/dheerajjha/mcp-migrate/issues/21),
  [#22](https://github.com/dheerajjha/mcp-migrate/issues/22), @waterlemonnn)

  All three bound their identifier suffix rather than using `\w*`, so
  `PingRequester` and `SetLevelRequesterFactory` are left alone. For a
  while the *rules* still matched those, so `check` reported a line `fix`
  declined to touch — an asymmetry taken deliberately, because a wrong
  finding costs a reader ten seconds and a wrong `--write` costs them
  working code. **The rules are now bounded too** and the two agree; see
  [#87](https://github.com/dheerajjha/mcp-migrate/issues/87) below.
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

- **`fix --write` could make `check` report a file clean without fixing it.**
  R003 decided whether a routing header was set with a raw substring test
  over the whole file, comments included — and R003's fixer writes a TODO
  that names the header. So running the fixer silenced the rule without
  setting anything. Compounding it, the fixer wrote a placeholder
  (`"Mcp-Method": "<set-mcp-method>"`) when it could not recover the real
  value, producing source that compiles, runs, and sends that literal
  string as an HTTP header. End to end: `check` found a real advisory,
  `fix --write` wrote a broken header, and `check` then reported
  **"Grade A. Nothing to fix."**

  The rule now uses `search_wire`, which keeps ordinary string literals
  (where a real header lives) and skips comments (where a TODO lives);
  `search_code` would have been wrong, since it skips string literals and
  would never see a real header either. The fixer now falls through to its
  TODO path rather than guessing. Both were found while reviewing two
  independent R003 fixer PRs — either would have tripped the rule bug.
- **Four rules fired on identifiers that merely started with an SDK name.**
  `\bPingRequest\w*` matched `PingRequester`; `SetLevelRequesterFactory`,
  `InitializeRequesterHelper` and `CreateMessageRequestBuilder` were the
  same shape in R012, R009 and R007. Replaced with bounded alternation over
  the suffixes the SDKs actually export, on both the Python *and*
  TypeScript patterns — the latter were a second set of `\w*` sites, and
  leaving them would have kept the false positive alive for most MCP
  servers. Verified over 18 false-positive and 18 true-positive cases in
  both languages: every FP silent, every real SDK name still caught.
  ([#87](https://github.com/dheerajjha/mcp-migrate/issues/87), @IronLad123)

  This also closes the rule/fixer asymmetry noted above: R009, R011 and
  R012's fixers had bounded their patterns while the rules had not, so
  three fixers shipped working *around* this bug. They now agree.
- **A JavaScript project could be reported as clean.** Loading `.js` files
  put them in `project.files` for the first time, and `_checked_something()`
  was `bool(project.files)` — so a pure-JavaScript server with a live
  `Mcp-Session-Id` in it exited **0**, "clean", with zero rules having run
  against it. Exit 0 there is worse than the exit 2 it replaced: a refusal
  became a verdict. It now checks `SUPPORTED`/`PARTIAL` membership, so a
  language that loads without rule coverage is still "could not check".
  ([#149](https://github.com/dheerajjha/mcp-migrate/issues/149), @waterlemonnn)
- **Three more stale claims in `check`'s own output.** The no-readable-language
  fallback said `mcp-migrate only reads Python today`, months after every
  rule read TypeScript — and that is what a JavaScript user saw. Every
  TypeScript *and JavaScript* tree was told "TypeScript support is the
  most-wanted thing in this repo and it is up for grabs", pointing at
  [#30](https://github.com/dheerajjha/mcp-migrate/issues/30) (now closed at
  21 of 21); JavaScript now points at #149 and TypeScript at #172. And
  `unscannable_reason`'s comment still reasoned about "2 of 21 rules" and
  "the 19 that never ran". The first is now derived from
  `SUPPORTED | PARTIAL` so it cannot drift again.
- **The R016 fixer contradicted `check` on the same file.** It annotated
  handler shapes on sight, so a file that already configured `cache_hints`
  — which the rule correctly ignores — got a TODO telling it to add them.
  It now applies the rule's own presence check to the file in front of it.
  Across files it stays generous, since `fix()` cannot see the rest of the
  project.
- **`check` said "TypeScript support is partial -- 21 of 21 rules read it",
  which is not a partial anything.** The message was written when the
  fraction still moved; R002 landing closed it, and the tool kept quoting a
  coverage gap that no longer exists. It now says the honest thing when
  coverage is complete: grading a `PARTIAL` language is an open decision, not
  a count, and points at the issue that decides it instead of a fraction
  stuck at its own denominator. Three call sites carried the same claim --
  the refusal reason, the finding footnote, and the mixed-tree coverage
  note -- and all three now branch on whether the fraction has actually
  stopped moving, so this doesn't come back the next time a language sits at
  full coverage. ([#172](https://github.com/dheerajjha/mcp-migrate/issues/172))
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

@ankitverma31's first PR added the pre-commit hook; @syf2211's added the
R003 fixer. @waterlemonnn wrote most of the rest. @IronLad123 ported the last rule
(R002) and bounded the four `\w*` patterns behind #87; @ujjwalprakash17's first PR fixed R014's case handling;
@slegarraga's first PR added the `check --json` schema contract;
@aryansk's first PR made the scanner read JavaScript -- and got the half
that is easy to miss, routing it to the TypeScript span scanner rather
than only adding the extensions; @PuvaanRaaj's #56/#58/#60 were an
independent take on the same three TypeScript ports, and #60 was
measurably right about case-insensitivity -- that half became
[#143](https://github.com/dheerajjha/mcp-migrate/issues/143), which
@ujjwalprakash17 then closed.

@aryansk and @waterlemonnn arrived at the JavaScript scanner fix
independently, 1.5 hours apart. @aryansk's landed first as the earlier
work; @waterlemonnn's reduced to the `_checked_something` bug neither the
other PR nor its review had caught, which is the one that mattered.

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
