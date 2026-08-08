"""Shared constants used across the CLI and the badge renderer.

The grade→color map must agree everywhere it is used, or the badge
undermines the thing it is reporting: a C rendered in green teaches the
reader that the colour means nothing, and then the next badge is not
trusted either.
"""

# Five-step traffic-light: each grade has a distinct color.
# This is the canonical map; both cli.py (badge_url) and
# scripts/render_badges.py import from here.
GRADE_COLOR = {
    "A": "brightgreen",
    "B": "green",
    "C": "yellow",
    "D": "orange",
    "F": "red",
}

UNKNOWN_COLOR = "lightgrey"
