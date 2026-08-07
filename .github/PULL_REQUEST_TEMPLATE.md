## What kind of PR is this?

- [ ] Cookbook recipe -- adds/fills in a file in `cookbook/`
- [ ] Rule -- adds/changes a rule in `src/mcp_migrate/rules/`
- [ ] Fixer -- adds/changes a fixer in `src/mcp_migrate/fixers/`
- [ ] Board entry -- adds/updates a `registry/servers/*.yaml` file
- [ ] Something else

## Cookbook recipe

- [ ] Follows `cookbook/_TEMPLATE.md` (Rule/Fixer/Severity/Spec, What broke,
      Before, After, Gotchas, Spec link)
- [ ] Row added to (or moved out of "Stubs" in) `cookbook/README.md`

## Rule

- [ ] `severity` is `breaking`, `deprecated`, or `advisory`
- [ ] `spec_ref` names the spec section or SEP the rule enforces
- [ ] Fixtures added under `tests/fixtures/<rule-id>/`
- [ ] At least one test added and passing (`pytest`)
- [ ] `mcp-migrate rules` lists the new rule

## Fixer

- [ ] `rule_id` matches an existing rule's `id`
- [ ] `confidence` is `safe` only if the transformation cannot change
      behavior beyond what the rule flags -- otherwise `review`
- [ ] Ambiguous shapes are left unchanged (`self.unchanged(source)`), not
      guessed at -- ideally with a fixture proving the backoff
- [ ] A round-trip/idempotency test: running the fixer twice changes
      nothing the second time
- [ ] `mcp-migrate fixers` lists the new fixer

## Board entry

- [ ] Generated with `mcp-migrate entry --repo owner/name`
- [ ] `notes:` edited to a real, one-sentence description
- [ ] `name` matches the filename

## Anything else reviewers should know?

<!--
AI-assisted contributions are welcome and don't need disclosing -- plenty of
work here is, review included. The one thing that isn't optional: a human has
read this and can stand behind it. Expect the review to run the change rather
than read the diff, and expect questions.
-->

