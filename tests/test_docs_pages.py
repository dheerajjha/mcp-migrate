"""The two published docs pages make factual claims about the code.

`docs/RULES_REFERENCE.md` and `docs/GETTING_STARTED.md` arrived in #241 as
hand-written tables, and they arrived with the cap column already wrong --
25/12/6 instead of 25/8/3. Not through carelessness: those were the real
caps until #214 derived them from WEIGHT, so the page was copied from a
README that had been correct when it was read. That is what drift looks
like from the inside, and it is why the numbers were caught by a human
reading closely rather than by CI.

Both files also sit under `docs/`, which is the GitHub Pages source, so a
wrong number here is published rather than merely committed.

`tests/test_docs.py` already does this for README.md and the cookbook.
This is the same treatment for the two pages that did not have it.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

import pytest

from mcp_migrate import __version__
from mcp_migrate.fixers import all_fixers
from mcp_migrate.grade import CAP_MULTIPLE, WEIGHT, letter
from mcp_migrate.rules import all_rules

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tests"))

from test_docs import _table_after  # noqa: E402

RULES_REFERENCE = ROOT / "docs" / "RULES_REFERENCE.md"
GETTING_STARTED = ROOT / "docs" / "GETTING_STARTED.md"


@pytest.fixture(scope="module")
def reference() -> str:
    return RULES_REFERENCE.read_text(encoding="utf-8")


def _rule_rows(text: str) -> list[list[str]]:
    _header, rows = _table_after(text, "| Rule | Severity | What breaks | Fixer |")
    return rows


# --- the rule table ------------------------------------------------------

def test_every_rule_has_exactly_one_row(reference):
    listed = [re.search(r"\[(R\d+)\]", row[0]).group(1) for row in _rule_rows(reference)]
    actual = [r.id for r in all_rules()]

    assert listed == sorted(listed), "rule rows are not in rule-id order"
    assert set(listed) == set(actual), (
        f"missing from the page: {sorted(set(actual) - set(listed))}; "
        f"not real rules: {sorted(set(listed) - set(actual))}"
    )
    assert len(listed) == len(set(listed)), "a rule is listed twice"


def test_severity_column_matches_the_rules(reference):
    by_id = {r.id: r for r in all_rules()}

    for row in _rule_rows(reference):
        rid = re.search(r"\[(R\d+)\]", row[0]).group(1)
        assert row[1] == by_id[rid].severity, (
            f"{rid}: page says {row[1]!r}, rule says {by_id[rid].severity!r}"
        )


def test_fixer_column_matches_the_fixers(reference):
    """`yes (safe)` / `yes (review)` / `no`, against all_fixers()."""
    fixer_by_rule = {f.rule_id: f for f in all_fixers()}

    for row in _rule_rows(reference):
        rid = re.search(r"\[(R\d+)\]", row[0]).group(1)
        cell = row[3]
        fixer = fixer_by_rule.get(rid)

        if cell == "no":
            assert fixer is None, f"{rid}: page says no fixer, all_fixers() has one"
            continue

        match = re.fullmatch(r"yes \(`?(\w+)`?\)", cell)
        assert match, f"{rid}: unparseable fixer cell {cell!r}"
        assert fixer is not None, f"{rid}: page claims a fixer, all_fixers() has none"
        assert fixer.confidence == match.group(1), (
            f"{rid}: page says {match.group(1)!r}, fixer is {fixer.confidence!r}"
        )


def test_the_fixer_count_sentence_is_true(reference):
    """The prose states a count; the count has to come from the code."""
    with_fixers = {f.rule_id for f in all_fixers()}
    without = sorted({r.id for r in all_rules()} - with_fixers)

    claim = (
        f"Only {len(with_fixers)} of the {len(all_rules())} rules ship a fixer "
        f"({' and '.join(without)} do not)."
    )
    assert claim in reference, f"the page should say: {claim}"


# --- the grading tables --------------------------------------------------

def test_cost_and_cap_columns_match_grade_py(reference):
    """The column that was wrong on arrival, pinned to its source.

    Cap is WEIGHT x CAP_MULTIPLE and is not independently chosen -- #214
    made that so precisely because the two had drifted apart before.
    """
    _header, rows = _table_after(reference, "| Severity     | Cost per finding | Cap per rule |")

    seen = {}
    for severity_cell, cost_cell, cap_cell in rows:
        severity = severity_cell.strip("`")
        cost = int(cost_cell.lstrip("-"))
        cap = int(cap_cell.lstrip("-"))

        assert severity in WEIGHT, f"unknown severity {severity!r}"
        assert cost == WEIGHT[severity], (
            f"{severity}: page says cost -{cost}, WEIGHT says -{WEIGHT[severity]}"
        )
        assert cap == WEIGHT[severity] * CAP_MULTIPLE, (
            f"{severity}: page says cap -{cap}, "
            f"WEIGHT x CAP_MULTIPLE is -{WEIGHT[severity] * CAP_MULTIPLE}"
        )
        seen[severity] = True

    assert set(seen) == set(WEIGHT), f"page is missing severities: {set(WEIGHT) - set(seen)}"


def test_score_bands_match_letter(reference):
    _header, rows = _table_after(reference, "| Score  | Grade |")

    covered = set()
    for score_cell, grade_cell in rows:
        low, high = (int(n) for n in score_cell.split("-"))
        assert low <= high, f"band {score_cell!r} is inverted"
        for score in (low, high, (low + high) // 2):
            assert letter(score) == grade_cell, (
                f"score {score} is in the page's {grade_cell} band, "
                f"but letter() says {letter(score)}"
            )
        covered.update(range(low, high + 1))

    assert covered == set(range(0, 101)), (
        f"the bands do not cover every score: missing {sorted(set(range(0, 101)) - covered)[:5]}"
    )


# --- the getting-started page --------------------------------------------

def test_precommit_rev_is_the_current_version():
    """Same guard README already has: a pinned rev that names a release
    nobody can install is a copy-paste that fails for the reader, not for us.
    """
    revs = re.findall(r"rev:\s*v(\d+\.\d+\.\d+)", GETTING_STARTED.read_text(encoding="utf-8"))

    assert revs, "the getting-started page no longer pins a pre-commit rev"
    assert set(revs) == {__version__}, f"page pins {sorted(set(revs))}, current is {__version__}"
