"""Tests for scripts/validate_registry.py and scripts/render_board.py.

These are standalone scripts (no __init__.py), made importable by
tests/conftest.py adding scripts/ to sys.path.
"""
from __future__ import annotations

from pathlib import Path

import pytest

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


@pytest.mark.parametrize("suppressed", [0, 2])
def test_non_negative_suppression_count_passes(tmp_path, suppressed):
    content = VALID_ENTRY.replace(
        "score: 97", f"score: 97\nsuppressed: {suppressed}"
    )
    path = _write(tmp_path, "acme-notes.yaml", content)
    assert vr.validate(path) == []


@pytest.mark.parametrize("value", ["-1", "1.5", '"2"', "true"])
def test_invalid_suppression_count_is_an_error(tmp_path, value):
    content = VALID_ENTRY.replace("score: 97", f"score: 97\nsuppressed: {value}")
    path = _write(tmp_path, "acme-notes.yaml", content)
    errs = vr.validate(path)
    assert any("`suppressed` must be a non-negative int" in e for e in errs)


@pytest.mark.parametrize("sha", ["a1b2c3d", "0123456789abcdef0123456789abcdef01234567"])
def test_valid_sha_passes(tmp_path, sha):
    content = VALID_ENTRY.replace("score: 97", f"score: 97\nsha: {sha}")
    path = _write(tmp_path, "acme-notes.yaml", content)
    assert vr.validate(path) == []


@pytest.mark.parametrize("sha", ["abc123", "not-hex-at-all", "0123456789abcdef0123456789abcdef012345678"])
def test_invalid_sha_is_an_error(tmp_path, sha):
    content = VALID_ENTRY.replace("score: 97", f"score: 97\nsha: {sha}")
    path = _write(tmp_path, "acme-notes.yaml", content)
    errs = vr.validate(path)
    assert any("`sha` must be a 7-40 character hex commit SHA" in e for e in errs)


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


# --- the declared language must exist in the repo ------------------------
#
# The CLI is not the only way an entry gets created: the YAML is nine lines
# and anyone can hand-write it. Since the board's promise is that a schema
# pass equals a merge, a `language: python` entry for a repo with no Python
# has to be caught here too, or the CLI's refusal is just a speed bump.

def _entry(**overrides) -> dict:
    data = {
        "name": "acme-notes", "repo": "acme/notes-mcp", "language": "python",
        "grade": "A", "score": 97, "checked_with": "mcp-migrate 0.1.1",
        "spec": "2026-07-28", "status": "ready", "notes": "A server.",
    }
    data.update(overrides)
    return data


def test_declared_language_present_in_repo_passes(tmp_path, monkeypatch):
    monkeypatch.setattr(vr, "repo_languages", lambda repo: {"Python", "Shell"})
    assert vr.validate_language(tmp_path / "acme-notes.yaml", _entry()) == []


def test_declared_language_absent_from_repo_is_an_error(tmp_path, monkeypatch):
    monkeypatch.setattr(vr, "repo_languages", lambda repo: {"TypeScript", "JavaScript"})
    errs = vr.validate_language(tmp_path / "acme-notes.yaml", _entry())
    assert len(errs) == 1
    assert "contains no Python" in errs[0]
    assert "TypeScript" in errs[0], "say what the repo actually is, not just what it isn't"


def test_repo_that_does_not_exist_is_an_error(tmp_path, monkeypatch):
    monkeypatch.setattr(vr, "repo_languages", lambda repo: set())
    errs = vr.validate_language(tmp_path / "acme-notes.yaml", _entry())
    assert any("no such repo" in e for e in errs)


def test_unreachable_github_skips_rather_than_convicts(tmp_path, monkeypatch, capsys):
    def boom(repo):
        raise vr.Unreachable("timed out")

    monkeypatch.setattr(vr, "repo_languages", boom)
    errs = vr.validate_language(tmp_path / "acme-notes.yaml", _entry())
    assert errs == [], "a network blip must never fail an honest entry"
    assert "skipped the language check" in capsys.readouterr().out


def test_language_other_claims_nothing_so_asks_nothing(tmp_path, monkeypatch):
    def boom(repo):
        raise AssertionError("should not have called the network")

    monkeypatch.setattr(vr, "repo_languages", boom)
    assert vr.validate_language(tmp_path / "acme-notes.yaml", _entry(language="other")) == []


def test_malformed_repo_is_left_to_the_schema_check(tmp_path, monkeypatch):
    def boom(repo):
        raise AssertionError("should not have called the network")

    monkeypatch.setattr(vr, "repo_languages", boom)
    assert vr.validate_language(tmp_path / "acme-notes.yaml", _entry(repo="nonsense")) == []


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


def test_render_board_marks_only_entries_with_suppressions(tmp_path, monkeypatch):
    servers_dir = tmp_path / "servers"
    servers_dir.mkdir()
    (servers_dir / "acme-notes.yaml").write_text(
        VALID_ENTRY.replace("score: 97", "score: 97\nsuppressed: 2")
    )
    (servers_dir / "plain.yaml").write_text(
        VALID_ENTRY.replace("name: acme-notes", "name: plain")
    )

    readme = tmp_path / "README.md"
    readme.write_text("<!-- BOARD:START -->\n<!-- BOARD:END -->\n")
    monkeypatch.setattr(rb, "SERVERS", servers_dir)
    monkeypatch.setattr(rb, "README", readme)

    assert rb.main() == 0
    text = readme.read_text()
    acme_row = next(line for line in text.splitlines() if "acme-notes" in line)
    plain_row = next(line for line in text.splitlines() if "plain" in line)
    assert "**A** (2 suppressed)" in acme_row
    assert "suppressed" not in plain_row


def test_render_board_fails_cleanly_without_markers(tmp_path, monkeypatch):
    servers_dir = tmp_path / "servers"
    servers_dir.mkdir()
    readme = tmp_path / "README.md"
    readme.write_text("# no markers in this file\n")
    monkeypatch.setattr(rb, "SERVERS", servers_dir)
    monkeypatch.setattr(rb, "README", readme)
    assert rb.main() == 1


def test_render_board_survives_a_suppressed_key_with_no_value(tmp_path, monkeypatch):
    """`suppressed:` written with no value parses as None, and `None > 0`
    raises. validate_registry rejects such an entry, but render_board runs
    independently of it -- a traceback is a worse answer than a board.
    """
    servers_dir = tmp_path / "servers"
    servers_dir.mkdir()
    (servers_dir / "acme-notes.yaml").write_text(
        VALID_ENTRY.replace("score: 97", "score: 97\nsuppressed:"), encoding="utf-8"
    )
    monkeypatch.setattr(rb, "SERVERS", servers_dir)
    monkeypatch.setattr(rb, "README", tmp_path / "README.md")
    (tmp_path / "README.md").write_text(
        "<!-- BOARD:START -->\n<!-- BOARD:END -->\n", encoding="utf-8"
    )
    assert rb.main() == 0
    text = (tmp_path / "README.md").read_text(encoding="utf-8")
    assert "acme-notes" in text
    assert "suppressed)" not in text


# --- disabled_rules: recorded, validated, and visible on the board --------
#
# A suppression silences one finding; a disabled rule silences a whole class
# of them, and the grade is still published as though the full set had run.
# So the disclosure has to survive all the way to the rendered board -- a
# field recorded in YAML that nobody renders is disclosure nobody reads, and
# the question a board exists to answer is whether two A grades mean the
# same thing.


def test_render_board_shows_which_rules_an_entry_switched_off(tmp_path, monkeypatch):
    servers_dir = tmp_path / "servers"
    servers_dir.mkdir()
    (servers_dir / "acme-notes.yaml").write_text(
        VALID_ENTRY.replace("score: 97", "score: 97\ndisabled_rules: [R001, R008]")
    )
    (servers_dir / "plain.yaml").write_text(
        VALID_ENTRY.replace("name: acme-notes", "name: plain")
    )

    readme = tmp_path / "README.md"
    readme.write_text("<!-- BOARD:START -->\n<!-- BOARD:END -->\n")
    monkeypatch.setattr(rb, "SERVERS", servers_dir)
    monkeypatch.setattr(rb, "README", readme)

    assert rb.main() == 0
    text = readme.read_text()
    acme_row = next(line for line in text.splitlines() if "acme-notes" in line)
    plain_row = next(line for line in text.splitlines() if "plain" in line)
    assert "**A** (2 rules off: R001, R008)" in acme_row
    assert "off" not in plain_row


def test_render_board_survives_a_disabled_rules_key_with_no_value(tmp_path, monkeypatch):
    """`disabled_rules:` with nothing after it parses as None, not [].

    validate_registry rejects that entry, but this script runs independently
    of it and a traceback is a worse answer than a rendered board -- the same
    reasoning as the `suppressed:` case above.
    """
    servers_dir = tmp_path / "servers"
    servers_dir.mkdir()
    (servers_dir / "acme-notes.yaml").write_text(
        VALID_ENTRY.replace("score: 97", "score: 97\ndisabled_rules:")
    )
    readme = tmp_path / "README.md"
    readme.write_text("<!-- BOARD:START -->\n<!-- BOARD:END -->\n")
    monkeypatch.setattr(rb, "SERVERS", servers_dir)
    monkeypatch.setattr(rb, "README", readme)

    assert rb.main() == 0
    assert "off" not in readme.read_text()


@pytest.mark.parametrize(
    "value,expected",
    [
        ('disabled_rules: "R001"', "must be a list of rule id strings"),
        ("disabled_rules: [R1]", "malformed rule id"),
        ("disabled_rules: [R001, R001]", "duplicates"),
    ],
    ids=["bare-string", "malformed-id", "duplicate"],
)
def test_validate_rejects_a_disabled_rules_value_it_cannot_read(
    tmp_path, monkeypatch, value, expected
):
    servers_dir = tmp_path / "servers"
    servers_dir.mkdir()
    (servers_dir / "acme-notes.yaml").write_text(f"{VALID_ENTRY}\n{value}\n")
    monkeypatch.setattr(vr, "SERVERS", servers_dir)

    errs = vr.validate(servers_dir / "acme-notes.yaml")
    assert any(expected in e for e in errs), errs


def test_validate_accepts_a_well_formed_disabled_rules_list(tmp_path, monkeypatch):
    servers_dir = tmp_path / "servers"
    servers_dir.mkdir()
    (servers_dir / "acme-notes.yaml").write_text(
        f"{VALID_ENTRY}\ndisabled_rules: [R001, R008]\n"
    )
    monkeypatch.setattr(vr, "SERVERS", servers_dir)

    errs = vr.validate(servers_dir / "acme-notes.yaml")
    assert not [e for e in errs if "disabled_rules" in e], errs
