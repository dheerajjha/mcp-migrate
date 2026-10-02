# Maintaining `mcp-migrate`

Notes for whoever maintains this next. The architecture is readable from the
code, so this file is deliberately not about architecture — it is about the
things that cost someone a day to learn and are invisible in a diff.

Accurate as of 0.11.1 (2026-10-02).

## 1. What it is, in one sentence

The MCP `2026-07-28` spec revision broke a large amount of existing server
code; `mcp-migrate` finds what it broke in a given server and mechanically
fixes what can be fixed safely.

It has a right to exist because the official Python SDK ships **no codemod** —
only a prose migration guide — and the TypeScript codemod handles v1→v2
package renames rather than the protocol changes.

```
$ mcp-migrate check ./my-server
mcp-migrate v0.11.1  ->  my-server
17 Python files, 21 rules, spec 2026-07-28

            rule    where                        what
breaking    R001    server.py:28                 Mcp-Session-Id was removed from
                                                 the Streamable HTTP transport.
breaking    R002    server.py:22                 `sessions` looks like per-connection
                                                 state held in process memory.
```

`check` reports. `fix` rewrites. The three things that matter, in order:
**never corrupt a file**, **never report a finding that is not real**, then
coverage.

## 2. Running it

```bash
uv sync --extra dev
uv run pytest                                  # 856 tests, ~6s
uv run python scripts/validate_registry.py     # registry YAML must validate
```

Green looks like `856 passed`. CI (`ci.yml`) runs the same two commands on
Python 3.10, 3.11, 3.12 and 3.13. `uv run pytest` alone will fail with
`Failed to spawn: pytest` if you skipped `--extra dev` — that is a missing
dependency, not a broken checkout.

Four workflows: `ci.yml` (PRs and main), `release.yml` (tags only),
`board.yml` (main, path-filtered), `action.yml` (the Marketplace action).

## 3. Traps

Each of these was a real defect, not a hypothetical.

**PEP 701 changed how f-strings tokenize, and it fails silently.** On Python
3.12+, an f-string is no longer one `STRING` token — it is
`FSTRING_START` / `FSTRING_MIDDLE` / `FSTRING_END`. Any pass that detects
string spans by looking for `STRING` therefore sees a multiline f-string as
containing **no string data at all**, which is indistinguishable from a file
that simply has no strings. A comment-out fixer is then free to insert a `#`
*inside the literal*, silently changing its value. Measured on 3.14: lines
seen as string data went from `[]` to `[1, 2, 3, 4]` once handled. Fixed in
0.7.1 (`fixers/_textedit.py`). **If you touch tokenization, test on 3.11 and
3.12+ — the bug does not exist below 3.12.** Related open issue: #105.

**A fixer must never leave a file unparseable, and "comment out the line" can.**
If the targeted line is the sole statement in a function body, commenting it
out produces a syntax error. The tool refuses the whole file rather than
corrupting it (`sole_function_body_lines()`), which is correct — but the
refusal means *no* fix is applied to that file, so #245 was really about
adding a `pass`. Refusing is the safe failure; make sure it stays the failure
mode when you add fixers.

**`rules/base.py::finding()` has a wide keyword signature** (`evidence`,
`evidence_line`, `feature`, …) that has grown over time. Conflicts in that
signature **cannot be resolved by concatenating both sides** — that produces
duplicate parameters that still import cleanly and then misbehave at call
sites. Resolve it by hand, deliberately.

**`board.yml` path filters hide their own failures.** Watching `registry/**`
alone was wrong in a way that left no trace: change a grade colour or a row
format and the workflow never fires, so the committed board and all 16 badge
endpoints keep serving the *old* rendering — no diff, no failure, nothing to
notice. The filter now also watches the render scripts. Add a path when you add
anything that affects output.

**Fork-PR CI approval was deliberately loosened, and it was audited.** The
setting is `first_time_contributors_new_to_github` (changed 2026-08-03 with the
owner's authorisation), so anyone with GitHub history gets CI immediately
instead of sitting in `action_required` while nobody notices. Verified still
working: @Charlie-Wang-03's fork PR #279 ran all four legs with no
intervention.

This is safe *because* of specific facts, and it stops being safe if they
change: `ci.yml` is the only workflow a fork PR can reach; it uses
`pull_request`, **not** `pull_request_target`, so fork code runs with a
read-only token and no secrets; there are no custom secrets in it; repo default
workflow permission is `read`; `release.yml` is tags-only and `board.yml` is
push-to-main-only, so neither is reachable from a fork. **Re-audit if anyone
adds `pull_request_target` or a custom secret.** Do not "fix" this back to
requiring approval without reading the above — it was a considered change.

**Registry grades carry the version that produced them.** When you re-grade a
server, bump `checked_with:` in its YAML. A grade with a stale `checked_with`
is a claim nobody can reproduce — which is exactly what #259 is about.

**Some version pins are guarded by tests** (`rev: v*` in `README.md` and
`docs/GETTING_STARTED.md`). They fail loudly on release, which is the point.

**`gh issue edit --add-assignee` says `'<user>' not found` for every outside
contributor, and that message is a lie.** The CLI validates the login against
`repos/.../assignees`, which lists only collaborators — on this repo, exactly
one person. The user exists and the assignment is perfectly legal. Use REST:

```bash
gh api -X POST repos/dheerajjha/mcp-migrate/issues/<n>/assignees \
  -f 'assignees[]=<login>'
```

This cost a wrong conclusion on 2026-09-17: `not found` read as "the account is
gone, so the claim on #252 is stale", when @wdwd200's account was fine and the
claim stood. **Suspect the identifier and the tool before you conclude the thing
is dead** — the same rule the registry work runs on. Assigning matters here: a
verbal "yes, it's yours" that is never recorded leaves the issue looking
unclaimed to everyone else, which is how two people end up on one fix.

## 4. Releasing

Standing instruction from the owner: **if `main` is ahead of the published
version, cut the release.** A merge that never ships is an unfinished merge.

```bash
git log v$(curl -s https://pypi.org/pypi/mcp-migrate/json | python3 -c 'import json,sys;print(json.load(sys.stdin)["info"]["version"])')..main --oneline
```

This matters more here than in a normal project: **the Marketplace Action
installs from PyPI**, so an unreleased fix is invisible to every Action user.
0.5.0 once sat on PyPI for a day while `main` carried a SARIF fix without which
no server could upload the tool's output at all — and the listing served the
broken one the whole time.

Publishing is PyPI Trusted Publishing (OIDC) on a `v*` tag. **There is no API
token in this repository and there must not be one.** The pending publisher is
registered as `owner: dheerajjha, repo: mcp-migrate, workflow: release.yml,
environment: pypi` — all four must keep matching or the upload is rejected, so
renaming that workflow file is a breaking change.

**Ahead is necessary, not sufficient.** Before tagging, confirm CI is green on
`main` *for the commit you are about to tag* — `gh run list --branch main
--limit 1` will happily report `in_progress` with an empty conclusion, and an
empty conclusion is not a pass. The sibling repo was one commit ahead and red
on 2026-09-17; applying "release when ahead" literally would have published a
red tree over OIDC, which needs no human at the keyboard to stop it. Docs-only
and test-only commits are not a reason to publish at all.

The release is: changelog, version bump, PR, merge, tag, push tag, then the
GitHub release from that version's changelog section (`gh release create
vX.Y.Z --verify-tag --latest --notes-file …`). `release.yml` publishes to PyPI
and nothing else. 0.8.0, 0.8.1 and 0.9.0 shipped without a release page, and
for eleven days the Releases page called 0.7.1 the latest; they were
backfilled on 2026-09-28. Then verify by installing from PyPI fresh — not by
reading the green tick.

Bump **minor** when a published grade moves or a documented field changes
shape; **patch** otherwise. Docs-only and test-only commits do not need a
release.

## 5. What not to do

- **Do not ship modelled, estimated or extrapolated numbers** as if they were
  measured. Grades and findings are reproducible claims; that is the whole
  value of the board.
- **Do not create a PyPI token.** See §4.
- **Do not merge on a description or a diff read.** Reproduce the bug first,
  or say plainly that you could not. A false positive costs more than a missed
  finding here, because contributors are working from these issues.
- **Do not merge before CI checks have registered.** `gh pr checks` reports
  success against an empty set; gate on a non-empty pass list.
- **Do not publish `HANDOFF.md` or `ACTION-PLAN.md`.** See §7.
- **Do not post to the owner's community accounts** without his explicit
  go-ahead on the specific text — those go out in his voice, from his account.
  PR #254 is already flagged 🤖 by the r/mcp moderator; that is the cost of
  getting this wrong.

## 6. Open work, in priority order

1. **#305**: R001's fixer writes broken TypeScript when a header read closes
   a bracket. There is no parse guard for TypeScript, so this one corrupts
   rather than refuses. Check the other comment-out fixers for the same
   exposure before fixing it in R001 alone. The Python side is done: #245
   shipped in 0.10.1 and its mirror image, #304, in 0.11.0.
2. **#105** — fixers insert comments inside string literals. The PEP 701 half
   is fixed (§3); the general case is not.
3. **#310**: R013 and R011 miss removed methods registered through the SDK
   itself (`@app.subscribe_resource()` in 1.x, `on_subscribe_resource=` and
   `on_ping=` in 2.x). A 1.x server doing that grades A/100, which is a false
   clean bill of health, the worst output this tool can produce. **#255**
   (SDK 2.x) is mostly done: detection shipped in 0.11.0, 0.11.1 made it see a
   black-formatted `Server(` call, and `tests/fixtures/sdk2_server` pins both.
   What's left is per-rule. Use `server_call_keywords` for constructor
   arguments rather than a line regex. #313 (R013's half of #310) is
   switching to it.
4. **#252** — R017's check matches from column 0 regardless of indentation,
   so it still fires on indented and trailing comments. The fixer half (#269)
   shipped in 0.10.0 and now skips every comment-only line, which makes
   `check` the side that over-reports. Two fixer tests pin the shapes, so a
   #252 fix cannot quietly bring the rewrite back.
5. **#89** — R003, R006 and R011 decide "is this MCP?" too loosely and fire
   on unrelated code. R005 and R020 are fixed (#234, #296). Upstream of a lot
   of false-positive reports.
6. **#259** — nothing verifies that published board grades still reproduce, so
   a rule change can move a grade silently. Pairs with the `checked_with` trap.
7. **#172** — TypeScript is at 21 of 21 but the tool still says
   "partial — 21 of 21". A one-line honesty bug with a stale premise behind it.

**Rejected, do not re-investigate:** re-requiring fork-PR approval (§3) — the
loosening was deliberate and audited.

## 7. Local-only history, and why it stays local

`HANDOFF.md` (~2,400 lines) and `ACTION-PLAN.md` are **untracked**. They are a
chronological maintainer journal, not instructions, and a fresh clone does not
get them — they exist only on the owner's machine.

Leave them untracked. They contain candid working assessments of named external
contributors, written for an audience of one. Publishing them would be a
genuine unkindness to people who volunteered work on this project. If you want
the history, read it there; if you want to record something durable, put it in
this file instead.

A cached clone-and-grade harness also lives outside the repo, at
`~/.oss-sweep/`. Do not re-implement it by hand.

## 8. Honest state

11 stars, 33 forks, and a real contributor base — multiple external
contributors have merged pull requests, most recently @Charlie-Wang-03 (#279,
their first, shipped in 0.7.1). Unlike a lot of projects at this size, the
issue tracker is genuinely the on-ramp: the `mentored` and `good first issue`
labels are honest, and people have converted from them.

The failure mode to watch is not neglect, it is **drift** — a rule change that
moves a published grade with nobody noticing (#259), or an issue whose
diagnosis rots while its `good first issue` label keeps attracting people to a
stale map. Re-verify a diagnosis before you re-advertise it.
