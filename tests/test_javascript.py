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

Step 2 of #149 is porting the rules themselves. R006, R017, and R021 are
the first three -- each has patterns that are spelled identically in
JavaScript and TypeScript (a class name, a wire string, a URL/date
literal), so `"javascript"` reaching the same branch as `"typescript"` was
the entire port. The other eighteen rules key off `TS_*` patterns built
around `import`/type-annotation idioms JavaScript doesn't have, and stay
TypeScript-only until each is checked and ported individually.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from mcp_migrate.rules.base import Project, SourceFile
from mcp_migrate.rules.r006_sse_transport_deprecated import DeprecatedSSETransport
from mcp_migrate.rules.r017_resource_not_found_code_changed import (
    ResourceNotFoundCodeChanged,
)
from mcp_migrate.rules.r021_json_schema_2020_12_required import OldJSONSchemaDialect
from mcp_migrate.scan import load_project

JS_WITH_COMMENT = """\
// SessionIdHeader used to be required here, no longer is.
const SessionIdHeader = "Mcp-Session-Id";
"""

# CommonJS on purpose, not `import`: the issue's own warning is that a
# pattern anchored on `import ... from` misses a `require()`-based server
# entirely, and R006's pattern isn't anchored on either -- it keys off the
# SDK class name and the route literal, both of which show up the same way
# regardless of module system.
LEGACY_JS = """\
const { SSEServerTransport } = require("@modelcontextprotocol/sdk/server/sse.js");

function mountSse(app) {
  app.get("/sse", async (req, res) => {
    const transport = new SSEServerTransport("/messages", res);
    await server.connect(transport);
  });
}

module.exports = { mountSse };
"""

CLEAN_JS = """\
const { StreamableHTTPServerTransport } = require("@modelcontextprotocol/sdk/server/streamableHttp.js");

// We dropped the SSE route in the 2026-07-28 migration; handles are
// ordinary tool arguments now.
async function handle(req, res) {
  const transport = new StreamableHTTPServerTransport();
  await server.connect(transport);
}

module.exports = { handle };
"""


def _js_project(text: str) -> Project:
    return Project(root=Path("."), files=[
        SourceFile(path=Path("server.js"), text=text, language="javascript"),
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


# --- the three ported rules -------------------------------------------

def test_r006_finds_sse_in_a_commonjs_server():
    project = _js_project(LEGACY_JS)
    findings = DeprecatedSSETransport().check(project)
    # The require()'d class name, the route literal, and the constructor.
    assert len(findings) >= 2


def test_r006_stays_silent_on_migrated_javascript_server():
    project = _js_project(CLEAN_JS)
    assert DeprecatedSSETransport().check(project) == []


def test_r017_finds_the_old_resource_not_found_code_in_javascript():
    code = (
        'function notFound() {\n'
        '  return { code: -32002, message: "resource not found" };\n'
        '}\n'
    )
    project = _js_project(code)
    findings = ResourceNotFoundCodeChanged().check(project)
    assert len(findings) == 1
    assert findings[0].line == 2


def test_r017_stays_silent_without_the_resource_not_found_context():
    project = _js_project('const port = -32002;\n')
    assert ResourceNotFoundCodeChanged().check(project) == []


def test_r021_finds_an_old_json_schema_dialect_in_javascript():
    code = 'const schema = { $schema: "http://json-schema.org/draft-07/schema#" };\n'
    project = _js_project(code)
    findings = OldJSONSchemaDialect().check(project)
    assert len(findings) == 1


def test_r021_stays_silent_without_an_explicit_dialect_pin():
    project = _js_project('const schema = { type: "object" };\n')
    assert OldJSONSchemaDialect().check(project) == []


# --- colocated JavaScript test files are skipped like their TS peers ------
#
# `TEST_FILE_PATTERNS` already excluded `*.test.ts`/`*.spec.ts`/
# `*.examples.ts` beside the module they cover, but had no JavaScript
# spellings. That went unnoticed while no rule read JavaScript at all --
# now that R006/R017/R021 do, a colocated `server.test.js` fixture (e.g.
# a backward-compat test deliberately exercising the old -32002 code) is
# scanned as production code and reported as a real `breaking` finding,
# exactly what this exclusion list exists to prevent (see scan.py).

@pytest.mark.parametrize("rel", [
    "src/server.test.js",
    "src/server.spec.js",
    "src/server.test.jsx",
    "src/server.examples.js",
    "src/server.test.mjs",
    "src/server.spec.cjs",
])
def test_colocated_javascript_test_files_are_skipped_by_default(tmp_path, rel):
    path = tmp_path / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(LEGACY_JS)
    assert load_project(tmp_path).files == [], f"{rel} is test code, not the server"


def test_colocated_javascript_test_files_are_scanned_with_include_tests(tmp_path):
    path = tmp_path / "src" / "server.test.js"
    path.parent.mkdir(parents=True)
    path.write_text(LEGACY_JS)
    assert load_project(tmp_path, include_tests=True).files != []
