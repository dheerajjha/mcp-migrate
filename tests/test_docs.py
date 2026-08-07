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

        m = re.match(r"(R\d+)\s+\((\w+)", fixer_cell)
        assert m, f"row {num}: unparseable fixer cell {fixer_cell!r}"
        fixer_rule, confidence = m.group(1), m.group(2)
        assert fixer_rule in row_rules, (
            f"row {num}: fixer cell names {fixer_rule}, not among {row_rules}"
        )
        fixer = fixer_by_rule.get(fixer_rule)
        assert fixer is not None, f"row {num}: {fixer_rule} has no fixer in all_fixers()"
        assert fixer.confidence == confidence, (
            f"row {num}: cookbook says {confidence!r}, fixer confidence is {fixer.confidence!r}"
        )
        claimed.append(fixer_rule)

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
