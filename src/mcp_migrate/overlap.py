"""Cross-rule dedup for findings that describe the same code twice.

R007 and R018 were written independently, months apart, and both ended up
matching the SDK's `CreateMessageResult(Schema)?` / `ListRootsResult(Schema)?`
names: R007 because Sampling and Roots are deprecated core features, R018
because server-initiated `sampling/createMessage` and `roots/list` were
separately replaced by SEP-2322's Multi Round-Trip Requests. Both findings
are true. A file that only imports those names still gets two contradicting
severities on the same line, which is confusing to read and (see #214)
questionable to double-charge in the grade.

This module resolves the *reading* problem without touching the *scoring*
calibration one (that's #214 -- whether the WEIGHT/RULE_CAP numbers
themselves are right is a separate decision from whether one real-world
fact should produce one finding or two). The fix is deliberately narrow: a
lookup table of rule pairs that are *known* to describe the same symbol,
not a generic "same line, so merge it" rule. Two unrelated rules that
happen to both fire on one busy line are not this case, and should keep
reporting independently.

What the merge keys on is the *feature*, not the line (see #221). Both
rules classify every match into a named feature -- R007 calls it
"Sampling", R018 calls it "Server-initiated sampling/createMessage" -- and
`FEATURE_CANONICAL` maps the two spellings onto one key. Findings from a
known pair that share a (path, feature) describe the same underlying fact
whether they landed on the same line or not: R007 firing on
`RootsCapability` on line 12 and R018 firing on `ListRootsResult` on line
11 are the same "this project uses Roots" fact, and mcp-server-git was
reporting it as four findings at two severities. When both rules in a pair
fire for the same feature in a file, the more urgent one (breaking beats
deprecated, deprecated beats advisory) wins and absorbs the other's
message, so the reader sees one finding instead of two, and still gets
both pieces of advice.

No symbol resolution is involved: the claim being merged is "same feature",
which the rules decided when they matched, not "same symbol", which would
need an import-aware pass. The line key remains as a fallback for findings
that carry no feature.
"""
from __future__ import annotations

from .rules.base import Finding, Rule

SEV_RANK = {"breaking": 0, "deprecated": 1, "advisory": 2}

# (rule_id, rule_id) pairs known to fire on the same underlying SDK symbol.
# Order doesn't matter -- severity decides the winner, not table order.
OVERLAPPING_PAIRS: frozenset[frozenset[str]] = frozenset({
    frozenset({"R007", "R018"}),
})

# Feature labels as emitted by each rule, canonicalized to one key per
# underlying fact. The two rules describe the same feature with different
# names ("Roots" vs "Server-initiated roots/list"), and the canonical key is
# what dedupe groups on so the pair merges across lines and symbols. R018's
# elicitation labels have no R007 counterpart; they are listed so the table
# is complete, but findings that share only an elicitation key never merge
# because no known pair spans them.
FEATURE_CANONICAL: dict[str, str] = {
    "Roots": "roots",
    "Server-initiated roots/list": "roots",
    "Sampling": "sampling",
    "Server-initiated sampling/createMessage": "sampling",
    "Logging": "logging",
    "Server-initiated elicitation/create": "elicitation",
    "notifications/elicitation/complete": "elicitation",
    "elicitationId": "elicitation",
}


def dedupe(findings: list[Finding], rules: dict[str, Rule]) -> list[Finding]:
    """Collapse findings from a known-overlapping rule pair that describe
    the same underlying fact.

    Findings that share a (path, canonical feature) and whose rule ids form
    one of `OVERLAPPING_PAIRS` are merged into the more severe one; its
    message gets a trailing note carrying the other rule's message so
    nothing is lost, just no longer shown as separate findings. Findings
    without a feature classification group by (path, line) instead -- the
    old behavior, preserved so rules that do not classify their matches
    still get the same-line merge and nothing else changes. Everything else
    passes through untouched.
    """
    by_key: dict[tuple[str, str], list[Finding]] = {}
    other: list[Finding] = []
    for f in findings:
        if f.path is None:
            other.append(f)
            continue
        by_key.setdefault((str(f.path), _group_key(f)), []).append(f)

    out: list[Finding] = list(other)
    for group in by_key.values():
        out.extend(_merge_group(group, rules))
    return out


def _group_key(f: Finding) -> str:
    """The identity two findings must share to be considered the same fact.

    A canonical feature when the rule attached one, else the line number
    (the pre-feature behavior). A finding with neither is alone in its group
    and passes through unchanged.
    """
    if f.feature:
        return f"feature:{FEATURE_CANONICAL.get(f.feature, f.feature)}"
    if f.line is not None:
        return f"line:{f.line}"
    return f"id:{id(f)}"


def _merge_group(group: list[Finding], rules: dict[str, Rule]) -> list[Finding]:
    """Merge the known-overlapping pair inside one group into a single finding.

    `group` holds findings that share a (path, feature) -- or, for findings
    without a feature, a (path, line). For every known pair that has both
    rules present in the group, ALL of that pair's findings collapse into one
    finding owned by the most severe rule, located at that rule's earliest
    line in the group, with the other rules' messages appended. Findings that
    belong to no fully-present pair (including a whole group from one rule
    firing many times) pass through untouched.
    """
    if len(group) < 2:
        return group

    out: list[Finding] = []
    consumed: set[int] = set()
    for pair in OVERLAPPING_PAIRS:
        present = {f.rule_id for f in group if id(f) not in consumed}
        if not pair <= present:
            continue
        members = [f for f in group if f.rule_id in pair and id(f) not in consumed]
        consumed.update(id(f) for f in members)
        out.append(_merge_participants(members, rules))
    out.extend(f for f in group if id(f) not in consumed)
    return out


def _merge_participants(members: list[Finding], rules: dict[str, Rule]) -> Finding:
    """Collapse all pair participants into one finding.

    The winner is the most severe rule; among equal severities, the earliest
    line; the deterministic tiebreak is rule id. Its location is kept (the
    reader still gets a real place to start), and every other participant's
    message is appended so both pieces of advice survive.
    """
    ordered = sorted(
        members, key=lambda f: (_rank(f, rules), f.line if f.line is not None else 0, f.rule_id)
    )
    winner = ordered[0]
    appended = "".join(
        f" Also flagged by {f.rule_id}: {f.message}" for f in ordered[1:]
    )
    return Finding(
        rule_id=winner.rule_id,
        message=winner.message + appended,
        path=winner.path,
        line=winner.line,
        snippet=winner.snippet,
        feature=winner.feature,
    )


def _rank(f: Finding, rules: dict[str, Rule]) -> int:
    rule = rules.get(f.rule_id)
    severity = rule.severity if rule else "advisory"
    return SEV_RANK.get(severity, 9)
