"""A trivial, fully clean server -- exists only so this fixture project has
some non-test source to scan. Nothing here should trip any rule."""
from __future__ import annotations


def ping() -> str:
    return "pong"
