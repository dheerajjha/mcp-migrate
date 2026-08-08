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

When both rules in a pair fire at the same (path, line), the more urgent
one (breaking beats deprecated, deprecated beats advisory) wins and absorbs
the other's message, so the reader sees one finding instead of two, and
still gets both pieces of advice.
"""
from __future__ import annotations

from .rules.base import Finding, Rule

SEV_RANK = {"breaking": 0, "deprecated": 1, "advisory": 2}

# (rule_id, rule_id) pairs known to fire on the same underlying SDK symbol.
# Order doesn't matter -- severity decides the winner, not table order.
OVERLAPPING_PAIRS: frozenset[frozenset[str]] = frozenset({
    frozenset({"R007", "R018"}),
})


def dedupe(findings: list[Finding], rules: dict[str, Rule]) -> list[Finding]:
    """Collapse same-location findings from a known-overlapping rule pair.

    Findings that share a (path, line) and whose rule ids form one of
    `OVERLAPPING_PAIRS` are merged into the more severe one; its message
    gets a trailing note carrying the other rule's message so nothing is
    lost, just no longer shown as two separate lines. Everything else --
    including findings that share a location with a rule *not* in a known
    pair -- passes through untouched.
    """
    by_location: dict[tuple[str, int], list[Finding]] = {}
    other: list[Finding] = []
    for f in findings:
        if f.path is None or f.line is None:
            other.append(f)
            continue
        by_location.setdefault((str(f.path), f.line), []).append(f)

    out: list[Finding] = list(other)
    for group in by_location.values():
        out.extend(_merge_group(group, rules))
    return out


def _merge_group(group: list[Finding], rules: dict[str, Rule]) -> list[Finding]:
    if len(group) < 2:
        return group

    merged: list[Finding] = []
    consumed: set[int] = set()
    for i, a in enumerate(group):
        if i in consumed:
            continue
        partner_idx = None
        for j, b in enumerate(group):
            if j == i or j in consumed:
                continue
            if frozenset({a.rule_id, b.rule_id}) in OVERLAPPING_PAIRS:
                partner_idx = j
                break
        if partner_idx is None:
            merged.append(a)
            continue

        b = group[partner_idx]
        consumed.add(i)
        consumed.add(partner_idx)
        winner, loser = _rank(a, rules), _rank(b, rules)
        winner, loser = (a, b) if winner <= loser else (b, a)
        merged.append(Finding(
            rule_id=winner.rule_id,
            message=f"{winner.message} Also flagged by {loser.rule_id}: {loser.message}",
            path=winner.path,
            line=winner.line,
            snippet=winner.snippet,
        ))

    return merged


def _rank(f: Finding, rules: dict[str, Rule]) -> int:
    rule = rules.get(f.rule_id)
    severity = rule.severity if rule else "advisory"
    return SEV_RANK.get(severity, 9)
