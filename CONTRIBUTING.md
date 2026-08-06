# Contributing

Three ways in, cheapest first: a cookbook recipe, a rule, a fixer. There's
also a fourth, separate path if you just want your own server listed on the
board.

**The standing principle behind everything below: a false positive is worse
than a missed finding.** A wrong `breaking` verdict costs a project its
badge and its maintainer's trust; a missed `advisory` costs a little
visibility, nothing more. When a detection can't be made precise, it ships
as `advisory` rather than `breaking`, or it doesn't ship at all. This is
also why fixers are conservative by design: a fixer that can't be sure a
transformation is correct returns the source unchanged rather than guess. A
wrong fix that silently corrupts someone's server is worse than reporting
the finding and doing nothing. See `RULE_CAP` in
[`grade.py`](src/mcp_migrate/grade.py) and the real mcp-atlassian/R003
false-positive story in [`r003_routing_headers.py`](src/mcp_migrate/rules/r003_routing_headers.py)
for what this looks like when it's gotten wrong before.

**Review promise:** every PR gets a first review within 48 hours. A rule or
fixer merges as soon as it has one passing test -- we're not going to
bikeshed your regex or ask for a second fixture you don't think you need. A
cookbook recipe merges as soon as it follows the template.

## Add a cookbook recipe (5 minutes)

[`cookbook/`](cookbook/README.md) is one markdown file per breaking or
deprecated change -- no Python, no tests, no fixtures. This is the cheapest
way to contribute.

```bash
cp cookbook/_TEMPLATE.md cookbook/NN-your-slug.md
```

Fill in what broke, a before/after code example, gotchas, and the spec link.
[`cookbook/README.md`](cookbook/README.md#stubs----open-slots) lists open
slots -- recipes with the rule and spec link already filled in, just missing
the worked example -- and [`.github/GOOD_FIRST_ISSUES.md`](.github/GOOD_FIRST_ISSUES.md)
has a ready-to-file issue for each one. Add a row to the appropriate table in
`cookbook/README.md`, open a PR.

## Add a rule (15 minutes)

A rule is a `Rule` subclass in `src/mcp_migrate/rules/`. Drop the file in
that package and `all_rules()` (`src/mcp_migrate/rules/__init__.py`) picks
it up automatically -- nothing to register.

### The API you have

`Rule` (`src/mcp_migrate/rules/base.py`):

```python
class Rule:
    id: str = ""            # "R0NN", next free number
    title: str = ""         # one line, shows in `mcp-migrate rules`
    severity: str = "advisory"   # breaking | deprecated | advisory
    spec_ref: str = ""      # spec section or SEP this rule enforces
    fix: str = ""           # one or two sentences, imperative, actionable

    def check(self, project: Project) -> list[Finding]: ...
    def finding(self, message, f=None, line=None, snippet=None) -> Finding: ...
```

`Project` gives you the whole scanned tree.

**Quick pick:** identifier or class name → `search_code` · JSON-RPC method
name (or other string-literal wire text) → `search_wire` · prose / comments →
almost certainly neither (and no shipped rule uses raw `search`).

- `project.search_code(pattern, *, flags=0)` -- like `search` below, but
  ignores matches that start inside a comment or a string/docstring
  literal. **Use this by default** for anything matching an identifier,
  class name, or code construct -- a docstring or `--help` string that
  merely *mentions* `Mcp-Session-Id` isn't a real usage of it. See
  `r001_session_id.py`, `r006_sse_transport.py`, `r007_deprecated_features.py`.
- `project.search_wire(pattern, *, flags=0)` -- skips comments and
  triple-quoted strings, but **keeps ordinary string literals**. Use this for
  JSON-RPC method names and other wire text that only appears inside strings
  (e.g. `tools/list`, `resources/subscribe`). Raw `search` over-matches prose
  such as module docstrings describing the handshake; that produced real
  false-positive `breaking` findings. See any of the 17 rules that call
  `search_wire`, and the docstring on `Project.search_wire` in
  `src/mcp_migrate/rules/base.py`.
- `project.search(pattern, *, flags=0)` -- yields `(SourceFile, lineno, stripped_line)`
  for every line matching a regex, including matches inside comments and
  strings. **No shipped rule uses it.** The last one that did was
  `r010_server_discover_missing.py`, as a suppression check, and it was a bug
  (#113): a comment saying `server/discover` is missing convinced the rule
  that it wasn't. That is the characteristic failure -- raw `search` inside a
  "should I stay silent?" gate lets prose switch a real finding off.
  Reach for it only if you have a reason
  neither `search_code` nor `search_wire` fits (for example, matching free-form
  prose you intentionally want). Prefer `search_wire` for method names and
  other string-literal wire content.
- `project.imports()` -- returns the flat `set[str]` of every module name
  imported anywhere in the project (from `ast.Import` / `ast.ImportFrom`).
  Use this to gate a rule on a library actually being in use, the way
  `r008_trace_context.py` only fires when `opentelemetry` is imported.
- `project.files` -- the raw list of `SourceFile(path, text, tree)` if you
  need a real AST walk instead of regex (see `r002_connection_state.py`).

Test code is skipped by default (see `scan.py`'s `TEST_DIR_SEGMENTS` /
`TEST_FILE_PATTERNS`) -- a rule doesn't need to worry about tests/fixtures
tripping it unless the person running `mcp-migrate` passes `--include-tests`.

### A complete example

This rule flags servers still declaring capabilities under the legacy
`experimental` key instead of the 2026-07-28 `extensions` map -- structurally
identical to `r005_extensions.py`, which already ships. `R022` is the next
free rule id as of this writing -- check `src/mcp_migrate/rules/` for the
actual next free number before you start (`R001`-`R021` are all taken).

`src/mcp_migrate/rules/r022_legacy_experimental_capability.py`:

```python
from .base import Finding, Project, Rule


class LegacyExperimentalCapability(Rule):
    id = "R022"
    title = "Declares capabilities under the legacy `experimental` key"
    severity = "advisory"
    spec_ref = "extensions replaces the experimental capabilities key"
    fix = (
        "Move anything under `experimental` to the new `extensions` map. "
        "`experimental` is not read by 2026-07-28 clients."
    )

    def check(self, project: Project) -> list[Finding]:
        out: list[Finding] = []
        for f, line, text in project.search_code(r"[\"']experimental[\"']\s*:"):
            out.append(self.finding(
                "`experimental` capabilities key found; 2026-07-28 clients "
                "look for `extensions` instead.",
                f, line, text,
            ))
        return out
```

### Fixtures and the test

Put one file that should trigger the rule and, ideally, one that shouldn't
under `tests/fixtures/<rule-id>/`, lowercase:

```
tests/fixtures/r022/bad.py      # contains "experimental": {...} as real code
tests/fixtures/r022/good.py     # contains "extensions": {...}, no "experimental"
tests/fixtures/r022/comment.py  # mentions "experimental": only in a comment/docstring — must not match
```

Then a test under `tests/` that loads that fixture directory as a project and
checks it:

`tests/test_r022_legacy_experimental_capability.py`:

```python
from pathlib import Path

from mcp_migrate.rules.r022_legacy_experimental_capability import (
    LegacyExperimentalCapability,
)
from mcp_migrate.scan import load_project

FIXTURES = Path(__file__).parent / "fixtures" / "r022"


def test_flags_experimental_key():
    project = load_project(FIXTURES)
    findings = LegacyExperimentalCapability().check(project)
    flagged = {f.path.name for f in findings}
    assert "bad.py" in flagged
    assert "good.py" not in flagged
```

Run it:

```bash
uv pip install -e ".[dev]"
pytest tests/test_r022_legacy_experimental_capability.py -v
```

Or the whole suite:

```bash
pytest
```

### Checklist

- [ ] `id` is the next free `R0NN`, not reused
- [ ] `severity` is exactly `breaking`, `deprecated`, or `advisory` (these
      drive the `WEIGHT` penalties in `grade.py` -- don't invent a new one)
- [ ] `spec_ref` names the spec section or SEP the rule enforces
- [ ] `fix` is one or two sentences, imperative, tells the reader what to do
      next, not just what's wrong
- [ ] `check()` returns a `list[Finding]`, empty when nothing is found
- [ ] fixtures added under `tests/fixtures/<rule-id>/`
- [ ] at least one test added under `tests/` and it passes locally
- [ ] `mcp-migrate rules` lists your rule when run from a checkout with your
      change (confirms auto-discovery picked it up)

## Add a fixer (45 minutes)

A fixer is a `Fixer` subclass in `src/mcp_migrate/fixers/`, discovered the
same way rules are (`all_fixers()` in `src/mcp_migrate/fixers/__init__.py`
scans the package -- nothing to register). A fixer targets one existing
rule and turns its finding into a text edit. Fixers only make sense for
rules where the fix is genuinely mechanical -- if writing one means
guessing at intent (naming a new argument, deciding what a durable store
looks like), the right contribution is a [cookbook recipe](#add-a-cookbook-recipe-5-minutes)
instead, not a fixer that gets it wrong silently.

### The API you have

`Fixer` (`src/mcp_migrate/fixers/base.py`):

```python
class Fixer:
    rule_id: str = ""           # which rule this repairs, e.g. "R001"
    title: str = ""             # one line, shows in `mcp-migrate fixers`
    confidence: str = "review"  # "safe" (apply with confidence) | "review" (flag for a human)

    def fix(self, source: str, path: Path) -> FixResult: ...

    # convenience for subclasses
    def unchanged(self, source: str) -> FixResult: ...
    def result(self, text: str, changes: list[str]) -> FixResult: ...
```

`FixResult` (`src/mcp_migrate/fixers/base.py`) is `text` (the new source),
`changes` (a list of one-line human-readable descriptions, one per edit),
and `changed` (bool). Return `self.unchanged(source)` when there's nothing
to do -- don't hand back a `FixResult` with `changed=True` and an empty
`changes` list.

Fixers are deliberately **not** built on `ast.unparse`. Round-tripping
through the AST throws away comments, string-quote style, blank lines and
exact formatting, which would turn every fix into an unreviewable, unrelated
diff. Instead a fixer does line/regex-level surgery on the original text, so
the diff a human reviews in `mcp-migrate fix` is exactly the change being
made and nothing else. `src/mcp_migrate/fixers/_textedit.py` has two small
helpers for this (`find_matching_close` to find a bracket's matching close
across possibly-multiple lines, `leading_ws` for indentation) -- use them
instead of writing your own bracket-matching if you need it; they're shared
plumbing, not a fixer themselves, so `all_fixers()` correctly ignores that
module.

**Confidence.** Mark a fixer `safe` only if the transformation cannot change
behavior beyond fixing the exact thing the rule flags -- see
`r017_resource_not_found_code_changed.py` (an exact numeric literal rename,
gated on the same qualifying context the rule itself requires) or
`r005_extensions.py` (adding `extensions={}` where absence already meant the
same thing) for what "safe" looks like in practice. Mark it `review` if a
human still has to make a decision after the fixer runs -- see
`r001_session_id.py`, which comments out the dead header read and leaves a
`# TODO(mcp-migrate): ...` exactly where the human needs to look next,
rather than guessing at the replacement.

### A complete example

Continuing the `R022` example from the rule section above: a fixer that
renames the legacy `"experimental":` capabilities key to `"extensions":`
wherever it's unambiguous -- a single occurrence on the line, not already
renamed. Anything messier (the key appearing twice, spread across a
multi-line dict in a shape we're not sure about) is left alone rather than
guessed at.

`src/mcp_migrate/fixers/r022_legacy_experimental_capability.py`:

```python
"""Fixer for R022 -- capabilities declared under the legacy `experimental`
key instead of `extensions`.

Only rewrites the key itself, and only when the line is unambiguous (one
occurrence, not already fixed). Confidence "safe": once that's true, the
remaining transformation is an exact string rename with no ambiguity about
what value belongs under the new key -- it's the same value that was
already under the old one.
"""
from __future__ import annotations

import re
from pathlib import Path

from .base import Fixer, FixResult

KEY_RX = re.compile(r"([\"'])experimental\1(\s*:)")


class ExperimentalToExtensionsFixer(Fixer):
    rule_id = "R022"
    title = 'Rename the legacy "experimental" capabilities key to "extensions"'
    confidence = "safe"

    def fix(self, source: str, path: Path) -> FixResult:
        lines = source.splitlines(keepends=True)
        changes: list[str] = []

        for i, line in enumerate(lines):
            matches = list(KEY_RX.finditer(line))
            if len(matches) != 1:
                continue  # zero, or more than one -- don't guess which
            m = matches[0]
            quote = m.group(1)
            lines[i] = (
                line[:m.start()] + f"{quote}extensions{quote}{m.group(2)}" + line[m.end():]
            )
            changes.append(f'line {i + 1}: renamed "experimental" key to "extensions"')

        if not changes:
            return self.unchanged(source)
        return self.result("".join(lines), changes)
```

### Fixtures and the test

Mirror the rule's test structure, plus round-trip and idempotency checks
(see `tests/test_fixers.py` for the pattern every shipped fixer follows):

`tests/test_r022_legacy_experimental_capability_fixer.py`:

```python
from pathlib import Path

from mcp_migrate.fixers.r022_legacy_experimental_capability import (
    ExperimentalToExtensionsFixer,
)

FIXER = ExperimentalToExtensionsFixer()


def test_renames_unambiguous_key():
    source = 'capabilities = {"experimental": {}}\n'
    result = FIXER.fix(source, Path("server.py"))
    assert result.changed
    assert '"extensions": {}' in result.text
    assert "experimental" not in result.text


def test_leaves_ambiguous_shape_alone():
    source = 'capabilities = {"experimental": {}, "other": {"experimental": 1}}\n'
    result = FIXER.fix(source, Path("server.py"))
    assert not result.changed  # two occurrences on one line -- don't guess


def test_idempotent():
    source = 'capabilities = {"experimental": {}}\n'
    once = FIXER.fix(source, Path("server.py")).text
    twice = FIXER.fix(once, Path("server.py"))
    assert not twice.changed
```

Run it the same way as a rule test: `pytest tests/test_r022_legacy_experimental_capability_fixer.py -v`.

### Checklist

- [ ] `rule_id` matches an existing rule's `id` exactly
- [ ] `confidence` is exactly `safe` or `review` -- `safe` only if the
      transformation truly cannot change behavior beyond what the rule flags
- [ ] `fix()` returns `self.unchanged(source)` (not a hand-built `FixResult`)
      when there's nothing to do
- [ ] every entry in `changes` describes one real edit, not a vague summary
- [ ] ambiguous shapes are left alone, not guessed at -- when in doubt, add
      a fixture that proves your fixer backs off
- [ ] a round-trip test: running the fixer twice on its own output changes
      nothing the second time
- [ ] `mcp-migrate fixers` lists your fixer when run from a checkout with
      your change

## Add your server to the board (60 seconds)

Separate from the three paths above -- this doesn't touch any code in this
repo, just a YAML file describing your server.

You need a repo that's already on GitHub and a local checkout of *that*
repo (not this one) to run the check against.

```bash
cd /path/to/your-server
uvx mcp-migrate check .                      # see your grade first
uvx mcp-migrate entry --repo owner/name > registry/servers/name.yaml
```

Copy that file into a checkout of this repo, edit the `notes:` line to one
sentence about what your server does, then:

```bash
git checkout -b add-name-to-board
git add registry/servers/name.yaml
git commit -m "registry: add name"
git push -u origin add-name-to-board
gh pr create --title "registry: add name" --fill
```

CI runs `scripts/validate_registry.py` against your file. If it passes and
`repo` points at a real GitHub repository, the PR gets merged -- nobody
reviews the server itself, and nobody is going to argue about your grade.
`scripts/render_board.py` regenerates the table in `README.md` on merge.

Two ways this can legitimately refuse you, both deliberate:

- **`entry` won't generate anything** if your server isn't Python, or if its
  Python is a small minority of a mostly-TypeScript repo. The tool only reads
  Python today ([#30](https://github.com/dheerajjha/mcp-migrate/issues/30) is
  where that gets fixed, and it's up for grabs). It writes nothing to stdout
  when it refuses, so the redirect above won't leave a half-written file.
- **CI rejects a hand-written entry** whose `language` isn't actually present
  in the repo, checked against GitHub. Since a schema pass equals a merge
  here, that check is the only thing standing between the board and a
  confident grade for code nobody read.

`registry/schema.yaml` lists every field. All of them are required:
`name` (must match the filename), `repo` (`owner/name`), `language`, `grade`,
`score`, `checked_with`, `spec`, `status`, `notes` (under 200 characters).
`mcp-migrate entry` fills in everything except `notes`.
