"""The JavaScript extensions, wired into the same span scanner as
TypeScript.

Step 1 of #149: the scanner now opens `.js`/`.jsx`/`.mjs`/`.cjs` files (see
test_scan.py), but that alone is not enough. `search_code`/`search_wire`
decide "is this match inside a comment or a string" by picking a span
scanner keyed off `SourceFile.language` -- `_ts_spans` for `"typescript"`,
the Python `tokenize`-based `_content_spans` for everything else. Without
routing `"javascript"` to `_ts_spans` too, every JS file would fail to
tokenize as Python, `_content_spans` would return `None`, and every rule
would silently fall back to *unfiltered* matching -- exactly the
comment-and-docstring false positive `search_code` exists to prevent.

No rule declares `"javascript"` in `languages` yet (that's step 2), so
these tests exercise `Project.search_code` directly rather than through a
rule.
"""
from __future__ import annotations

from mcp_migrate.rules.base import Project, SourceFile

JS_WITH_COMMENT = """\
// SessionIdHeader used to be required here, no longer is.
const SessionIdHeader = "Mcp-Session-Id";
"""


def _js_project(text: str) -> Project:
    return Project(root=None, files=[
        SourceFile(path="server.js", text=text, language="javascript"),
    ])


def test_search_code_skips_the_comment_in_javascript():
    project = _js_project(JS_WITH_COMMENT)
    matches = list(project.search_code(r"SessionIdHeader"))
    assert len(matches) == 1
    assert matches[0][1] == 2


def test_search_code_does_not_fall_back_to_unfiltered_matching():
    """A regression guard for the specific failure mode: if `"javascript"`
    ever stops routing to `_ts_spans`, `_content_spans` returns `None` for
    non-Python source and `search_code` yields *every* match, comment
    included. That would silently double the match count above."""
    project = _js_project(JS_WITH_COMMENT)
    matches = list(project.search_code(r"SessionIdHeader"))
    assert len(matches) != 2
