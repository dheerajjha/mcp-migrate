"""SARIF 2.1.0 output.

`--json` emits a shape of our own design, which is fine for a script and
useless to everything else. SARIF is what GitHub code scanning speaks, and
speaking it is what turns a finding from a line in a CI log into an
annotation on the diff, an entry in the Security tab, and a thing that
gets tracked across commits rather than re-read every time.

This is a pure output format. No rule sees it, no scanner changes; it is a
projection of the same findings `--json` already carries.

Two decisions worth stating rather than burying, both raised in #182:

**`deprecated` maps to `warning`.** `breaking` -> `error` and `advisory`
-> `note` are forced. `deprecated` could go either way, and the choice
decides whether a deprecation blocks a pull request by default, because
code scanning's default gate fails on `error` alone. The spec gives
deprecated features at least twelve months, so a deprecation is
categorically "you have time, but start" -- exactly `warning`. Mapping it
to `error` would make every server using Roots or Sampling unmergeable
today over a change that does not break until next year, and the
predictable response to that is switching the whole integration off.

**Absolute severity, not the grade.** SARIF carries per-result levels and
no overall score. That is a better fit than it looks: the grade is a
weighted judgement about a project, while a SARIF run is a set of
locations. Nothing here reports A-F, and `check` remains where a grade
comes from.
"""
from __future__ import annotations

from pathlib import Path

SARIF_VERSION = "2.1.0"
SCHEMA = "https://json.schemastore.org/sarif-2.1.0.json"

INFORMATION_URI = "https://github.com/dheerajjha/mcp-migrate"

# severity -> SARIF level. See the module docstring for why `deprecated`
# is `warning` and not `error`.
LEVEL = {
    "breaking": "error",
    "deprecated": "warning",
    "advisory": "note",
}
DEFAULT_LEVEL = "warning"


def _uri(path, root: Path) -> str:
    """A repo-relative, forward-slashed URI for a finding's file.

    Code scanning matches results to the diff by path, so an absolute path
    from the scanning machine matches nothing and the annotations silently
    never appear. Relative-to-repo-root is the only form that works, and
    the separator has to be `/` on every platform.
    """
    if path is None:
        return ""
    p = Path(path)
    try:
        p = p.resolve().relative_to(root.resolve())
    except (ValueError, OSError):
        # Outside the scanned root, or unresolvable. Fall back to whatever
        # we were given rather than dropping the location entirely -- a
        # result with an imperfect path is still a result.
        pass
    return p.as_posix()


def _rule_descriptor(rule) -> dict:
    descriptor = {
        "id": rule.id,
        "name": rule.id,
        "shortDescription": {"text": rule.title},
        "defaultConfiguration": {"level": LEVEL.get(rule.severity, DEFAULT_LEVEL)},
        "properties": {
            # `tags` is what code scanning renders as filters, and the
            # severity is the tag people actually want to filter on.
            "tags": ["mcp", rule.severity],
            "mcp-migrate.severity": rule.severity,
        },
    }
    if rule.fix:
        # fullDescription is the remediation text in the Security tab --
        # `fix` is written as imperative advice, which is exactly right.
        descriptor["fullDescription"] = {"text": rule.fix}
        descriptor["help"] = {"text": rule.fix, "markdown": rule.fix}
    if rule.spec_ref:
        uri = _spec_uri(rule.spec_ref)
        if uri:
            descriptor["helpUri"] = uri
        else:
            # A spec_ref that is prose rather than a link still belongs in
            # the output; helpUri must be a URI or consumers reject the
            # document, so it rides in properties instead.
            descriptor["properties"]["mcp-migrate.spec"] = rule.spec_ref
    return descriptor


def _spec_uri(spec_ref: str) -> str:
    """Pull the URL out of a `spec_ref`, which is sometimes prose plus a link.

    e.g. "SEP-2567 https://github.com/..." -> the URL. Rules whose
    spec_ref is pure prose ("Roots, Sampling and Logging deprecated")
    yield nothing, and the caller keeps the text as a property.
    """
    for token in str(spec_ref).split():
        if token.startswith(("http://", "https://")):
            return token.rstrip(".,)")
    return ""


def build(findings, rules, root: Path, *, version: str, spec: str) -> dict:
    """The SARIF log for one `check` run.

    `rules` is the full rule registry, not just the ones that fired: SARIF
    wants the driver to declare every rule it can report, so a consumer
    can tell "this rule ran and found nothing" from "this rule does not
    exist". That distinction is the whole reason code scanning can close a
    resolved alert instead of leaving it open forever.
    """
    ordered = [rules[rule_id] for rule_id in sorted(rules)]
    index_of = {rule.id: i for i, rule in enumerate(ordered)}

    results = []
    for f in findings:
        rule = rules[f.rule_id]
        result = {
            "ruleId": f.rule_id,
            "ruleIndex": index_of[f.rule_id],
            "level": LEVEL.get(rule.severity, DEFAULT_LEVEL),
            "message": {"text": f.message},
        }

        uri = _uri(f.path, root)
        if uri:
            location = {
                "physicalLocation": {
                    "artifactLocation": {"uri": uri, "uriBaseId": "%SRCROOT%"},
                }
            }
            if f.line:
                # SARIF regions are 1-based, same as our line numbers.
                location["physicalLocation"]["region"] = {"startLine": f.line}
            result["locations"] = [location]
        else:
            # Project-level findings (R010 asks a question about the whole
            # tree) have no file. SARIF allows an empty locations array and
            # consumers render it against the repository root; omitting the
            # key entirely makes some consumers drop the result.
            result["locations"] = []

        results.append(result)

    return {
        "$schema": SCHEMA,
        "version": SARIF_VERSION,
        "runs": [{
            "tool": {
                "driver": {
                    "name": "mcp-migrate",
                    "version": version,
                    "semanticVersion": version,
                    "informationUri": INFORMATION_URI,
                    "rules": [_rule_descriptor(r) for r in ordered],
                    "properties": {"mcp-migrate.spec": spec},
                }
            },
            "originalUriBaseIds": {"%SRCROOT%": {"uri": root.resolve().as_uri() + "/"}},
            "results": results,
            "columnKind": "utf16CodeUnits",
        }],
    }
