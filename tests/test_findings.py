"""The published ecosystem report.

This page states measurements about thousands of other people's
repositories. A stale number in it is a false claim about them, so no
figure on it is typed: every one is interpolated from
data/ecosystem-scan.json, and this file fails if the committed HTML is not
byte-identical to what the generator produces from that data.

The prose is written by hand and is meant to be. It is only the numbers
that must not be.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

from render_findings import DATA, OUT, PRIOR, main  # noqa: E402

from mcp_migrate.rules import all_rules  # noqa: E402


@pytest.fixture(scope="module")
def page() -> str:
    assert OUT.exists(), "docs/findings.html is missing; run scripts/render_findings.py"
    return OUT.read_text()


@pytest.fixture(scope="module")
def data() -> dict:
    return json.loads(DATA.read_text())


def test_committed_page_is_what_the_generator_produces(page):
    before = page
    main()
    after = OUT.read_text()
    if before != after:
        OUT.write_text(before)
        pytest.fail(
            "docs/findings.html is stale. Run `python scripts/render_findings.py` "
            "and commit."
        )


def test_the_headline_number_is_the_one_in_the_data(page, data):
    """The standfirst carries the claim the whole page rests on."""
    r001 = data["rule_prevalence"].get("R001", {"pct": 0.0})["pct"]

    assert f"<strong>{r001:.1f}%</strong> of them." in page


def test_registry_figures_match_the_data(page, data):
    reg = data["registry"]

    assert f"{reg['unique_github_repos']:,}</strong>\nunique GitHub repositories" in page
    assert f"<strong>{reg['dead_link_pct']}% of them 404.</strong>" in page
    assert f"{reg['dead_links']} pointed at repositories" in page


def test_every_rule_with_findings_is_listed(page, data):
    """The ranked table is the whole result; a rule missing from it is a
    measurement quietly dropped."""
    known = {r.id for r in all_rules()}

    for rid in data["rule_prevalence"]:
        if rid in known:
            assert f'index.html#{rid.lower()}' in page, f"{rid} missing from the page"


def test_the_A_grade_caveat_is_present(page):
    """#255 means an A is 'we found nothing', not 'there is nothing'. The
    page does not get to print a grade distribution without saying so."""
    assert "we cannot fully stand behind it" in page
    assert "not the same\nclaim" in page or "not the same claim" in page
    assert "issues/255" in page


def test_the_correction_section_survives(page):
    """The most load-bearing section on the page: the headline we nearly
    published was wrong, and saying so is what makes the rest credible."""
    assert "What we got wrong, and how we know" in page
    assert "17 of 18" in page and "14 of 18" in page
    assert "measuring where a string appears" in page


def test_the_prior_claim_is_read_from_the_frozen_run_not_typed(page):
    """The number that was wrong is exactly the one nobody should retype."""
    prior = json.loads(PRIOR.read_text())
    was = prior["rule_prevalence"]["R010"]["pct"]

    assert f"<em>{was}% of servers do not implement" in page


def test_it_does_not_publish_per_server_grades(page, data):
    """The board is where per-server claims go, and every entry on it was
    read by a human first (#186). This page is aggregates on purpose."""
    assert "aggregates on purpose" in page
    # A per-repo table would carry slugs; the page should carry none.
    assert not re.search(r'github\.com/[\w.-]+/[\w.-]+"[^>]*>[\w.-]+/[\w.-]+</a>', page)


def test_social_card_metadata_is_present(page):
    for prop in ("og:title", "og:description", "og:image", "og:url", "twitter:card"):
        assert f'"{prop}"' in page


def test_no_unresolved_template_braces(page):
    body = page.split("</style>", 1)[1]
    assert "{{" not in body and "}}" not in body


def test_no_placeholder_values_leaked(page):
    """A missing key rendering as `None` is how a page ends up asserting
    something nobody measured."""
    body = page.split("</style>", 1)[1]
    assert ">None<" not in body
    assert "n/a" not in body
