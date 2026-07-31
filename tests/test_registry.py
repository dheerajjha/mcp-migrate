"""Tests for scripts/validate_registry.py and scripts/render_board.py.

These are standalone scripts (no __init__.py), made importable by
tests/conftest.py adding scripts/ to sys.path.
"""
from __future__ import annotations

from pathlib import Path

import render_board as rb
import validate_registry as vr

VALID_ENTRY = """\
name: acme-notes
repo: acme/notes-mcp
language: python
grade: A
score: 97
checked_with: mcp-migrate 0.1.0
spec: "2026-07-28"
status: ready
notes: A stateless notes server for the acme workspace.
"""


def _write(tmp_path: Path, filename: str, content: str) -> Path:
    path = tmp_path / filename
    path.write_text(content)
    return path


# --- validate_registry.py -----------------------------------------------

def test_valid_entry_passes(tmp_path):
    path = _write(tmp_path, "acme-notes.yaml", VALID_ENTRY)
    assert vr.validate(path) == []


def test_missing_field_is_an_error(tmp_path):
    content = VALID_ENTRY.replace("checked_with: mcp-migrate 0.1.0\n", "")
    path = _write(tmp_path, "acme-notes.yaml", content)
    errs = vr.validate(path)
    assert any("missing required field `checked_with`" in e for e in errs)


def test_bad_enum_is_an_error(tmp_path):
    content = VALID_ENTRY.replace("language: python", "language: cobol")
    path = _write(tmp_path, "acme-notes.yaml", content)
    errs = vr.validate(path)
    assert any("`language` must be one of" in e for e in errs)


def test_filename_name_mismatch_is_an_error(tmp_path):
    path = _write(tmp_path, "some-other-name.yaml", VALID_ENTRY)
    errs = vr.validate(path)
    assert any("must match the filename" in e for e in errs)


def test_out_of_range_score_is_an_error(tmp_path):
    content = VALID_ENTRY.replace("score: 97", "score: 150")
    path = _write(tmp_path, "acme-notes.yaml", content)
    errs = vr.validate(path)
    assert any("`score` must be an int 0-100" in e for e in errs)


def test_non_integer_score_is_an_error(tmp_path):
    content = VALID_ENTRY.replace("score: 97", 'score: "high"')
    path = _write(tmp_path, "acme-notes.yaml", content)
    errs = vr.validate(path)
    assert any("`score` must be an int 0-100" in e for e in errs)


def test_malformed_repo_string_is_an_error(tmp_path):
    content = VALID_ENTRY.replace("repo: acme/notes-mcp", "repo: not-a-valid-repo-string")
    path = _write(tmp_path, "acme-notes.yaml", content)
    errs = vr.validate(path)
    assert any("must look like owner/name" in e for e in errs)


def test_multiple_problems_all_reported(tmp_path):
    content = (
        VALID_ENTRY
        .replace("language: python", "language: cobol")
        .replace("score: 97", "score: 999")
    )
    path = _write(tmp_path, "acme-notes.yaml", content)
    errs = vr.validate(path)
    assert len(errs) >= 2


# --- render_board.py -----------------------------------------------------

def test_render_board_rewrites_only_the_marked_region(tmp_path, monkeypatch):
    servers_dir = tmp_path / "servers"
    servers_dir.mkdir()
    (servers_dir / "acme-notes.yaml").write_text(VALID_ENTRY)

    readme = tmp_path / "README.md"
    readme.write_text(
        "# Some project\n\n"
        "Intro text that must survive the rewrite.\n\n"
        "<!-- BOARD:START -->\nstale old table\n<!-- BOARD:END -->\n\n"
        "Footer text that must survive the rewrite.\n"
    )

    monkeypatch.setattr(rb, "SERVERS", servers_dir)
    monkeypatch.setattr(rb, "README", readme)

    exit_code = rb.main()
    assert exit_code == 0

    text = readme.read_text()
    assert "Intro text that must survive the rewrite." in text
    assert "Footer text that must survive the rewrite." in text
    assert "stale old table" not in text
    assert "acme-notes" in text
    assert "1 servers checked" in text
    assert "1x A" in text
    assert text.count("<!-- BOARD:START -->") == 1
    assert text.count("<!-- BOARD:END -->") == 1


def test_render_board_sorts_by_grade_then_score(tmp_path, monkeypatch):
    servers_dir = tmp_path / "servers"
    servers_dir.mkdir()
    (servers_dir / "low-grade.yaml").write_text(
        VALID_ENTRY.replace("name: acme-notes", "name: low-grade").replace("grade: A", "grade: F").replace("score: 97", "score: 10")
    )
    (servers_dir / "acme-notes.yaml").write_text(VALID_ENTRY)

    readme = tmp_path / "README.md"
    readme.write_text("<!-- BOARD:START -->\n<!-- BOARD:END -->\n")
    monkeypatch.setattr(rb, "SERVERS", servers_dir)
    monkeypatch.setattr(rb, "README", readme)

    assert rb.main() == 0
    text = readme.read_text()
    assert text.index("acme-notes") < text.index("low-grade")


def test_render_board_fails_cleanly_without_markers(tmp_path, monkeypatch):
    servers_dir = tmp_path / "servers"
    servers_dir.mkdir()
    readme = tmp_path / "README.md"
    readme.write_text("# no markers in this file\n")
    monkeypatch.setattr(rb, "SERVERS", servers_dir)
    monkeypatch.setattr(rb, "README", readme)
    assert rb.main() == 1
