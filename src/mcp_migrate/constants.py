"""Shared constants used across the CLI and the badge renderer.

The grade→color map must agree everywhere it is used, or the badge
undermines the thing it is reporting: a C rendered in green teaches the
reader that the colour means nothing, and then the next badge is not
trusted either.
"""

# Five-step traffic-light: each grade has a distinct color.
# This is the canonical map; both cli.py (badge_url) and
# scripts/render_badges.py import from here.
#
# These five values are not a preference, which is why the duplicate map
# that disagreed with them (B as brightgreen, D as red) was the wrong side
# of the fix rather than an equally valid one: README's own grade table
# already documented exactly this scheme, so the renderer was contradicting
# the project's published documentation, not just another module.
# Observation due to @waterlemonnn in #229; the consolidation itself is
# @Jah-yee's in #226.
#
# If these change, README's "Score | Grade | Badge color" table has to
# change with them -- test_docs.py now fails on that drift -- and every
# endpoint under docs/badge/ has to be regenerated, which test_badges.py
# enforces against the committed files.
GRADE_COLOR = {
    "A": "brightgreen",
    "B": "green",
    "C": "yellow",
    "D": "orange",
    "F": "red",
}

UNKNOWN_COLOR = "lightgrey"
