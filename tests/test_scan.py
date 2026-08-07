"""Tests for `scan.load_project` -- which files get read at all.

Everything downstream is a claim about the files this module decided to
open, so a mistake here is invisible in every other test: rules pass,
fixers pass, and the tool reports confidently on a set of files that is
quietly wrong.
"""
from __future__ import annotations

from mcp_migrate.scan import load_project


def test_generated_declarations_are_skipped_for_every_module_form(tmp_path):
    """`.d.ts` was excluded as build output; `.d.mts` and `.d.cts` were not,
    so a project on "type": "module" got its generated declarations scanned
    and graded. Those files are dense with SDK type re-exports, which is the
    shape several rules match on -- so it added findings, not just noise."""
    body = 'export declare const x: string;\nconst s = req.headers["Mcp-Session-Id"];\n'
    for name in ("a.d.ts", "b.d.mts", "c.d.cts"):
        (tmp_path / name).write_text(body)
    for name in ("impl.ts", "impl.mts", "impl.cts"):
        (tmp_path / name).write_text(body)

    project = load_project(tmp_path)
    scanned = {f.path.name for f in project.files}
    assert scanned == {"impl.ts", "impl.mts", "impl.cts"}
def test_load_project_reads_javascript_and_skips_declaration_output(tmp_path):
    (tmp_path / "server.js").write_text("const answer = 42;\n")
    (tmp_path / "component.jsx").write_text("export default () => null;\n")
    (tmp_path / "module.mjs").write_text("export const answer = 42;\n")
    (tmp_path / "common.cjs").write_text("module.exports = {};\n")
    (tmp_path / "types.d.ts").write_text("export declare const answer: number;\n")

    project = load_project(tmp_path)

    assert [(file.path.name, file.language) for file in project.files] == [
        ("common.cjs", "javascript"),
        ("component.jsx", "javascript"),
        ("module.mjs", "javascript"),
        ("server.js", "javascript"),
    ]


def test_javascript_uses_the_typescript_comment_and_string_spans(tmp_path):
    """Loading `.js` is only half the job. If `javascript` did not reach the
    TypeScript span branch it would fall through to the Python one, and `//`
    would stop being recognised as a comment -- so a rule would read
    commented-out code as live. That is #113's failure, one language over,
    and the extension map alone does not catch it."""
    (tmp_path / "a.js").write_text(
        '// const sessionId = req.headers["Mcp-Session-Id"];\n'
        'const real = 1;\n'
    )
    project = load_project(tmp_path)
    assert list(project.search_code(r"Mcp-Session-Id")) == [], (
        "a // comment must not read as code on a .js file"
    )
