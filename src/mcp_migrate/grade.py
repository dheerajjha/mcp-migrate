"""Turn findings into a single letter you can put in a README badge."""
from __future__ import annotations

from .rules.base import Finding, Rule

WEIGHT = {"breaking": 25, "deprecated": 8, "advisory": 3}

# The most a single rule is allowed to cost, no matter how many times it
# fires. Without this, one rule with a systemic false-positive pattern (or
# even a real but repetitive problem, like the same header missing on 19
# call sites) can single-handedly zero a project's score. Real evidence:
# mcp-atlassian's R003 hit 19 times before it was tightened, for 475 raw
# penalty points -- more than 4x over from one rule alone.
#
# The cap is derived from WEIGHT, not hand-picked: CAP_MULTIPLE is how many
# firings of a rule it takes before the cap kicks in, and that multiple is
# the same for every severity. Picking RULE_CAP independently of WEIGHT (as
# a previous version of this file did) let the two disagree on how quickly
# repetition should stop mattering -- breaking findings capped out after 1
# firing while advisory ones got 2, which is backwards from what anyone
# actually wants. See #214.
CAP_MULTIPLE = 2
RULE_CAP = {severity: weight * CAP_MULTIPLE for severity, weight in WEIGHT.items()}

BADGE_COLOR = {"A": "brightgreen", "B": "green", "C": "yellow", "D": "orange", "F": "red"}


def score(findings: list[Finding], rules: dict[str, Rule]) -> int:
    per_rule_penalty: dict[str, int] = {}
    per_rule_severity: dict[str, str] = {}
    for f in findings:
        rule = rules.get(f.rule_id)
        severity = rule.severity if rule else "advisory"
        per_rule_penalty[f.rule_id] = per_rule_penalty.get(f.rule_id, 0) + WEIGHT.get(severity, 3)
        per_rule_severity[f.rule_id] = severity

    penalty = 0
    for rule_id, raw_penalty in per_rule_penalty.items():
        cap = RULE_CAP.get(per_rule_severity[rule_id], 6)
        penalty += min(raw_penalty, cap)
    return max(0, 100 - penalty)


def letter(value: int) -> str:
    if value >= 95:
        return "A"
    if value >= 80:
        return "B"
    if value >= 60:
        return "C"
    if value >= 40:
        return "D"
    return "F"


def badge_url(grade: str) -> str:
    color = BADGE_COLOR.get(grade, "lightgrey")
    return f"https://img.shields.io/badge/MCP%202026--07--28-{grade}-{color}"
