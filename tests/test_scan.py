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
