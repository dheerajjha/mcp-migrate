"""Three documents make factual claims about the code; nothing else checks them.

`cookbook/README.md`'s index, `README.md`'s rule table, and every
TODO-annotation fixer's `COOKBOOK`/`SPEC_URL` pointers all drift silently --
CI has no opinion about markdown, so a merged fixer or a renamed recipe
leaves a stale row behind until someone reads closely enough to notice.
"""
from __future__ import annotations

import re
import sys
from collections import Counter
from pathlib import Path
from urllib.parse import urlparse

from mcp_migrate.fixers import all_fixers
from mcp_migrate.rules import all_rules

ROOT = Path(__file__).resolve().parent.parent
COOKBOOK_DIR = ROOT / "cookbook"

_SPEC_HOSTS = {"modelcontextprotocol.io", "github.com"}


def _table_after(text: str, header: str) -> tuple[list[str], list[list[str]]]:
    """Split a markdown table into (header cells, body rows).

    Assumes the standard header / `---` / row shape and that `header` is the
    literal text of the header line -- fine for these three tables, which
    follow a fixed shape on purpose (see the module docstring).
    """
    lines = text.splitlines()
    start = next(i for i, line in enumerate(lines) if line.strip() == header.strip())
    raw_rows = []
    for line in lines[start:]:
        line = line.strip()
        if not line.startswith("|"):
            break
        raw_rows.append([cell.strip() for cell in line.strip("|").split("|")])
    header_cells, _separator, *body = raw_rows
    return header_cells, body


def _markdown_link_target(cell: str) -> str:
    m = re.match(r"\[[^\]]+\]\(([^)]+)\)", cell)
    assert m, f"not a markdown link: {cell!r}"
    return m.group(1)


# --- cookbook/README.md's index ------------------------------------------

def test_cookbook_index_matches_rules_and_fixers():
    text = (COOKBOOK_DIR / "README.md").read_text(encoding="utf-8")
    _header, rows = _table_after(text, "| # | Recipe | Rule(s) | Fixer |")

    rule_ids = {r.id for r in all_rules()}
    fixer_by_rule = {f.rule_id: f for f in all_fixers()}
    claimed: list[str] = []
    numbers: list[int] = []

    for num, recipe_cell, rules_cell, fixer_cell in rows:
        numbers.append(int(num))

        recipe_path = COOKBOOK_DIR / _markdown_link_target(recipe_cell)
        assert recipe_path.is_file(), f"row {num}: {recipe_path} does not exist"

        row_rules = [r.strip() for r in rules_cell.split(",")]
        for rid in row_rules:
            assert rid in rule_ids, f"row {num}: {rid} is not a known rule id"

        if fixer_cell == "none":
            for rid in row_rules:
                assert rid not in fixer_by_rule, (
                    f"row {num}: says 'none' but {rid} has a fixer"
                )
            continue

        # A recipe can cover several rules and more than one of them can
        # ship a fixer -- recipe 01 covers R001 and R002 and both do. Parsing
        # only the first entry silently dropped the rest, which showed up as
        # "R002's fixer is claimed by 0 cookbook rows" rather than as a
        # parse error.
        #
        # Matched rather than split on ",": a cell may carry a parenthetical
        # that itself contains a comma, e.g. "R004 (safe, list-literal shape
        # only)". Only the first word inside the parens is the confidence;
        # the rest is prose about the fixer's scope.
        entries = re.findall(r"(R\d+)\s+\((\w+)[^)]*\)", fixer_cell)
        assert entries, f"row {num}: unparseable fixer cell {fixer_cell!r}"
        for fixer_rule, confidence in entries:
            assert fixer_rule in row_rules, (
                f"row {num}: fixer cell names {fixer_rule}, not among {row_rules}"
            )
            fixer = fixer_by_rule.get(fixer_rule)
            assert fixer is not None, f"row {num}: {fixer_rule} has no fixer in all_fixers()"
            assert fixer.confidence == confidence, (
                f"row {num}: cookbook says {confidence!r}, fixer confidence is "
                f"{fixer.confidence!r}"
            )
            claimed.append(fixer_rule)

        # Every rule in this row that ships a fixer must be listed, not just
        # one of them -- otherwise a row reads as "R002 has no fixer" by
        # omission, which is the drift this test exists to catch.
        for rid in row_rules:
            if rid in fixer_by_rule:
                assert rid in claimed, (
                    f"row {num}: {rid} ships a fixer but the row does not list it"
                )

    assert numbers == sorted(numbers), "cookbook rows are out of order"
    assert len(numbers) == len(set(numbers)), "a cookbook row number repeats"

    counts = Counter(claimed)
    for rid in fixer_by_rule:
        assert counts[rid] == 1, (
            f"{rid}'s fixer is claimed by {counts[rid]} cookbook rows, want exactly one"
        )


# --- README.md's "Every rule" table ---------------------------------------

def test_readme_rule_table_matches_rules_and_fixers():
    text = (ROOT / "README.md").read_text(encoding="utf-8")
    _header, rows = _table_after(text, "| Rule | Severity | What breaks | Fixer |")

    rules_by_id = {r.id: r for r in all_rules()}
    fixer_by_rule = {f.rule_id: f for f in all_fixers()}
    seen: list[str] = []

    for rule_cell, severity_cell, _what_breaks, fixer_cell in rows:
        rule_id = re.match(r"\[(R\d+)\]", rule_cell).group(1)
        seen.append(rule_id)

        rule = rules_by_id.get(rule_id)
        assert rule is not None, f"README lists {rule_id}, which all_rules() does not know"
        assert severity_cell == rule.severity, (
            f"{rule_id}: README says severity {severity_cell!r}, rule says {rule.severity!r}"
        )

        source_link = _markdown_link_target(rule_cell)
        assert (ROOT / source_link).is_file(), (
            f"{rule_id}: source link {source_link} does not exist"
        )

        fixer = fixer_by_rule.get(rule_id)
        if fixer is None:
            assert fixer_cell == "no", f"{rule_id}: README says {fixer_cell!r} but there is no fixer"
        else:
            assert fixer_cell == f"yes (`{fixer.confidence}`)", (
                f"{rule_id}: README says {fixer_cell!r}, fixer confidence is {fixer.confidence!r}"
            )

    assert set(seen) == set(rules_by_id), (
        "README table and all_rules() disagree: "
        f"missing={set(rules_by_id) - set(seen)} extra={set(seen) - set(rules_by_id)}"
    )
    assert len(seen) == len(set(seen)), "README lists a rule more than once"


# --- fixer COOKBOOK / SPEC_URL pointers -----------------------------------

def test_fixer_pointers_resolve():
    cookbook_text = (COOKBOOK_DIR / "README.md").read_text(encoding="utf-8")
    _header, cookbook_rows = _table_after(cookbook_text, "| # | Recipe | Rule(s) | Fixer |")
    rules_by_recipe = {
        _markdown_link_target(recipe_cell): [r.strip() for r in rules_cell.split(",")]
        for _num, recipe_cell, rules_cell, _fixer_cell in cookbook_rows
    }

    checked_any = False
    for fixer in all_fixers():
        module = sys.modules[type(fixer).__module__]

        spec_url = getattr(module, "SPEC_URL", None)
        if spec_url is not None:
            checked_any = True
            parsed = urlparse(spec_url)
            assert parsed.scheme in ("http", "https") and parsed.netloc, (
                f"{fixer.rule_id}: SPEC_URL is not a URL: {spec_url!r}"
            )
            # Not a network call on purpose: a test that hits the real
            # network in CI is a flake generator, not a doc check.
            assert parsed.netloc in _SPEC_HOSTS, (
                f"{fixer.rule_id}: SPEC_URL points somewhere unexpected: {spec_url!r}"
            )
            if parsed.netloc == "github.com":
                assert parsed.path.startswith("/modelcontextprotocol/modelcontextprotocol"), (
                    f"{fixer.rule_id}: SPEC_URL is a github.com link but not the spec repo: {spec_url!r}"
                )

        cookbook_path = getattr(module, "COOKBOOK", None)
        if cookbook_path is None:
            continue
        checked_any = True
        assert (ROOT / cookbook_path).is_file(), (
            f"{fixer.rule_id}: COOKBOOK points at {cookbook_path}, which does not exist"
        )
        recipe_file = cookbook_path.removeprefix("cookbook/")
        claimed_rules = rules_by_recipe.get(recipe_file)
        assert claimed_rules is not None, (
            f"{fixer.rule_id}: COOKBOOK points at {recipe_file}, which is not in the cookbook index"
        )
        assert fixer.rule_id in claimed_rules, (
            f"{fixer.rule_id}: COOKBOOK points at {recipe_file}, which names {claimed_rules}, not {fixer.rule_id}"
        )

    assert checked_any, "no fixer defines COOKBOOK or SPEC_URL -- test would pass vacuously"


# The tables above are checked row by row, but both files also state the
# fixer count in prose, and a sentence drifts exactly as easily as a row.
# Both of these were stale within an hour of the R002 and R016 fixers
# landing: the README said "Only 16 of the 21", the cookbook said "for
# sixteen rules", while `all_fixers()` returned 18.
WORDS = {
    10: "ten", 11: "eleven", 12: "twelve", 13: "thirteen", 14: "fourteen",
    15: "fifteen", 16: "sixteen", 17: "seventeen", 18: "eighteen",
    19: "nineteen", 20: "twenty", 21: "twenty-one",
}


def test_prose_fixer_counts_match_all_fixers():
    n_fixers = len({fx.rule_id for fx in all_fixers()})
    n_rules = len(list(all_rules()))

    readme = (ROOT / "README.md").read_text()
    expected = f"Only {n_fixers} of the {n_rules} rules ship a fixer at all"
    assert expected in readme, (
        f"README's prose fixer count is stale: expected {expected!r}. "
        f"all_fixers() covers {n_fixers} of {n_rules} rules."
    )

    cookbook = (COOKBOOK_DIR / "README.md").read_text()
    word = WORDS.get(n_fixers)
    assert word, f"no word spelling for {n_fixers} -- extend WORDS"
    expected = f"for {word} rules, fix the mechanical part automatically"
    assert expected in cookbook, (
        f"cookbook README's prose fixer count is stale: expected {expected!r}. "
        f"all_fixers() covers {n_fixers} rules."
    )


# --- README.md's grade table ---------------------------------------------

def test_readme_grade_table_matches_the_code():
    """README's `Score | Grade | Badge color` table is the fourth document
    that makes factual claims about the code, and until now nothing checked
    it.

    That gap is not hypothetical -- it is how #224 happened. Two colour maps
    disagreed for long enough to ship, and the tie-break turned out to be
    that README had documented the right answer the whole time while one of
    the maps quietly contradicted it. A table nobody verifies is not
    documentation, it is a second source of truth.

    Both columns are checked: the colour against `GRADE_COLOR`, and the
    score bands against `letter()` itself rather than a copy of its
    thresholds -- asserting the boundary and the value just below it, so a
    band edited in one place and not the other fails here.
    """
    from mcp_migrate.constants import GRADE_COLOR
    from mcp_migrate.grade import letter

    readme = (ROOT / "README.md").read_text()
    _header, rows = _table_after(readme, "| Score  | Grade | Badge color   |")

    documented = {grade: colour for _score, grade, colour in rows}
    assert documented == GRADE_COLOR, (
        "README's grade table disagrees with GRADE_COLOR in "
        "src/mcp_migrate/constants.py -- one of them is lying to a "
        f"maintainer about what their badge looks like.\n"
        f"  README:    {documented}\n"
        f"  constants: {GRADE_COLOR}"
    )

    for score_range, grade, _colour in rows:
        low, high = (int(n) for n in score_range.split("-"))
        assert letter(low) == grade, (
            f"README says {low} is a {grade}, letter() says {letter(low)}"
        )
        assert letter(high) == grade, (
            f"README says {high} is a {grade}, letter() says {letter(high)}"
        )
        if low > 0:
            assert letter(low - 1) != grade, (
                f"README puts the {grade} band's floor at {low}, but "
                f"letter({low - 1}) is also {grade} -- the band starts lower "
                "than the table claims"
            )
