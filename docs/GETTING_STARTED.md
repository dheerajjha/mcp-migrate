# Getting Started

`mcp-migrate` finds and fixes what the MCP 2026-07-28 spec revision breaks in
your server. It is the only tool that edits your server's code for you: the
official Python SDK ships no codemod for the protocol changes, and the
TypeScript codemod only handles the v1→v2 package rename.

## Install

`mcp-migrate` is a Python CLI published on PyPI. The fastest way to run it
without installing anything into your project is `uvx`:

```bash
uvx mcp-migrate --help
```

Alternatively, install it into your environment:

```bash
pip install mcp-migrate
# or
uv tool install mcp-migrate
```

## Check a server

Point the tool at the root of your server project:

```bash
uvx mcp-migrate check .
```

The report lists every finding with its rule id, severity (`breaking`,
`deprecated`, `advisory`), file, and line, then prints a letter grade and a
score out of 100. A clean tree prints `Grade A` and a ready-to-paste badge.

Useful report flags:

- `--json` — machine-readable output with the full, uncapped finding list
  (the terminal table caps each rule at 5 rows).
- `--format sarif` — SARIF 2.1.0 for GitHub code scanning.
- `--rule R001` — run only specific rules (repeatable). The grade is
  suppressed when a subset of rules runs, because a partial grade is not a
  grade.
- `--severity breaking` — only change what is *displayed*; the grade and
  exit code are still computed from every finding.
- `--fail-on {breaking,deprecated,advisory,never}` — the minimum severity
  that fails the run (default `breaking`).
- `--include-tests` — scan tests, fixtures, and examples (skipped by
  default: backward-compat tests are evidence of good testing, not of a
  broken server).

### Exit codes

| code | meaning |
| ---- | ------- |
| `0`  | checked it, nothing `breaking` |
| `1`  | checked it, found something `breaking` |
| `2`  | **could not check it** — no readable source in a supported language |

Exit `2` means "we did not read your code", not "your code is fine". An
empty finding set is only meaningful when the tool actually scanned the tree.

## Fix a server

`fix` runs in **dry-run mode by default** — it prints the exact unified diff
and writes nothing:

```bash
uvx mcp-migrate fix .            # preview only
uvx mcp-migrate fix . --write    # apply the changes
```

Every change is tagged in the diff output:

- **`safe`** — the transformation cannot change behavior. Apply with
  confidence.
- **`review`** — the fixer did the mechanical part it is sure of and left a
  `# TODO(mcp-migrate): ...` where a human must finish the job.

Other fix flags:

- `--safe-only` — apply only `safe` fixers.
- `--rule R006` — restrict to specific rules (repeatable, same as `check`).
- `--include-tests` — also fix test/fixture paths.

Fixers are deliberately conservative: when a fixer cannot be certain a
transformation is correct, it leaves the source untouched rather than guess.
A wrong fix that silently corrupts your server is worse than reporting the
finding and doing nothing.

## Configure it

Everything that is a flag can live in config so a team and CI share it.
Put it in `[tool.mcp-migrate]` in `pyproject.toml`:

```toml
[tool.mcp-migrate]
skip = ["vendor/", "generated/"]
include-tests = false

[tool.mcp-migrate.rules]
R008 = "off"                                          # no reason recorded
R016 = "off -- ttl is enforced by the gateway in front of this"
```

No `pyproject.toml`? Use a standalone `.mcp-migrate.toml` at the project
root instead (most TypeScript projects fall here).

Rules:

- **A flag beats config, config beats the built-in default.**
- **A disabled rule never runs** — it costs nothing against the grade and
  `check` reports how many rules config switched off in every run.
- **Malformed config** (bad TOML, unknown rule id, invalid rule value) does
  not fail the run — it falls back to defaults and reports what it could
  not understand (`config_warnings` in `--json`).

## Suppress a false positive

When a finding is wrong, or the code is deliberate and not changing, silence
that one line rather than the whole rule:

```python
mcp_session_id = req.headers["X-Sid"]  # mcp-migrate: ignore[R001] -- proxy shim, not MCP session state
```

The rule id is required and a reason after `--` is expected. Suppressed
findings **don't count against the grade**. `--show-suppressions` lists every
one; stale suppressions that matched nothing are reported as
`unused_suppressions`, so they don't accumulate silently in CI.

**Caveat:** `R005`, `R015`, and `R016` report at most one finding per file,
so suppressing their line silences the rule for the whole file.

## Integrate with CI and pre-commit

Pre-commit hook (a `breaking` finding fails the hook):

```yaml
# .pre-commit-config.yaml
repos:
  - repo: https://github.com/dheerajjha/mcp-migrate
    rev: v0.2.0
    hooks:
      - id: mcp-migrate
```

The hook maps exit `2` ("could not check it") to `0` so a repo the tool
cannot read does not block every commit.

GitHub code scanning via SARIF:

```yaml
- run: mcp-migrate check . --format sarif > mcp-migrate.sarif
- uses: github/codeql-action/upload-sarif@v3
  with:
    sarif_file: mcp-migrate.sarif
```

Severities map to SARIF levels: `breaking` -> `error`, `deprecated` ->
`warning`, `advisory` -> `note`.

## Understand the language support

- **Python is graded.** TypeScript is scanned — every rule reads TypeScript —
  but a letter grade is withheld pending the decision tracked in
  [dheerajjha/mcp-migrate#172](https://github.com/dheerajjha/mcp-migrate/issues/172).
- The exit code works on TypeScript regardless: a `breaking` finding exits
  `1` with or without a grade, so TypeScript CI gates work today.

## Next steps

- See the full rule reference in [RULES_REFERENCE.md](RULES_REFERENCE.md).
- Add your server to the board with `mcp-migrate entry --repo owner/name`.