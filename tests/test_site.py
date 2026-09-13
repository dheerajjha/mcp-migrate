"""The GitHub Pages landing page.

This page is the first thing a stranger sees, and the failure it is most
prone to is the silent one: the tool ships a new version, a rule changes
wording, a server's grade moves -- and the page goes on confidently
describing the release before it. Nobody notices, because a stale page
looks exactly like a fresh one.

So the committed docs/index.html is checked the way the badges are: it
must be byte-identical to what the generator produces from the current
registry and the current rule set. If you changed a rule or an entry,
run `python scripts/render_site.py` and commit the result.
"""
from __future__ import annotations

import html
import re
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

from render_site import OUT, load_entries, main, split_ref  # noqa: E402

from mcp_migrate import __version__  # noqa: E402
from mcp_migrate.rules import all_rules  # noqa: E402


@pytest.fixture(scope="module")
def page() -> str:
    assert OUT.exists(), "docs/index.html is missing; run scripts/render_site.py"
    return OUT.read_text()


def test_committed_page_is_what_the_generator_produces(page):
    """The whole point: no hand-edits, no drift."""
    before = page
    main()
    after = OUT.read_text()
    if before != after:
        OUT.write_text(before)  # leave the tree as we found it on failure
        pytest.fail(
            "docs/index.html is stale. Run `python scripts/render_site.py` and commit."
        )


def test_pages_is_served_from_this_file():
    """GitHub Pages serves main:/docs, so the entry point has to be here.

    Pages was enabled on this repo with nothing to serve, which answered
    404 at the public URL while reporting "built" in settings. An empty
    docs/ is therefore not a neutral state -- it is a live 404.
    """
    assert OUT.name == "index.html"
    assert OUT.parent.name == "docs"


def test_every_rule_appears_with_its_id_and_title(page):
    """The rule list is the reason search traffic ever arrives.

    Someone whose server broke searches the symptom, not the tool name.
    A rule missing from this page is a door that does not exist.
    """
    for rule in all_rules():
        assert f'id="{rule.id.lower()}"' in page, f"{rule.id} has no anchor on the page"
        assert html.escape(rule.title, quote=True) in page, f"{rule.id} title missing"
        assert html.escape(rule.fix, quote=True) in page, f"{rule.id} fix text missing"


def test_severity_counts_match_the_rule_set(page):
    rules = all_rules()
    counts = {
        sev: sum(1 for r in rules if r.severity == sev)
        for sev in ("breaking", "deprecated", "advisory")
    }
    assert (
        f"{counts['breaking']} breaking &middot; {counts['deprecated']} deprecated "
        f"&middot; {counts['advisory']} advisory" in page
    )
    assert f"<li>{len(rules)} rules</li>" in page


def test_every_board_entry_appears(page):
    for entry in load_entries():
        assert html.escape(entry["repo"], quote=True) in page, f"{entry['repo']} missing"


def test_version_on_the_page_is_the_current_version(page):
    assert f"v{__version__}" in page
    # and no *other* version string is left lying around
    stale = {v for v in re.findall(r"\bv(\d+\.\d+\.\d+)\b", page) if v != __version__}
    assert not stale, f"page mentions other versions: {sorted(stale)}"


def test_board_does_not_claim_adoption(page):
    """The tool refuses to overclaim about a codebase; the site does not
    get to overclaim about the tool. Every entry was scanned by us."""
    assert "survey, not a list of adopters" in page
    assert "nobody below has endorsed" in page


def test_grade_colours_match_the_badge_palette(page):
    """A grade rendered one colour here and another in the badge teaches
    the reader that the colour means nothing. Same failure as #226."""
    from mcp_migrate.constants import GRADE_COLOR

    from render_site import HEX

    for grade in GRADE_COLOR:
        assert GRADE_COLOR[grade] in HEX, f"no hex for grade {grade}"


def test_social_card_metadata_is_present(page):
    """A link posted anywhere renders a card or it renders nothing."""
    for prop in ("og:title", "og:description", "og:image", "og:url", "twitter:card"):
        assert f'"{prop}"' in page, f"{prop} missing"


def test_no_unresolved_template_braces(page):
    """The generator is one big f-string; a doubled brace that got away
    ships as literal text on the page."""
    body = page.split("</style>", 1)[1]
    assert "{{" not in body and "}}" not in body


@pytest.mark.parametrize(
    "ref,expected",
    [
        ("SEP-2567 https://example.com/x", ("SEP-2567", "https://example.com/x")),
        ("https://example.com/y", ("spec", "https://example.com/y")),
        ("Deterministic tool ordering (SHOULD)", ("Deterministic tool ordering (SHOULD)", "")),
        ("", ("", "")),
    ],
)
def test_split_ref(ref, expected):
    assert split_ref(ref) == expected
