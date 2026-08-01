"""A tree we could not read must not receive a grade.

The bug these cover: `check` turned an empty finding set into Grade A
without ever asking whether it had read a file, and `entry` stamped
`language: python` on whatever it was pointed at. Together that meant a
TypeScript server -- and most MCP servers are TypeScript -- following the
documented "run `entry`, open a PR" instructions would submit a truthful-
looking A/100 for a repo the tool had never opened, and CI would merge it,
because the board's promise is that a schema pass equals a merge.

The failure is quiet and it is self-inflicted, which is the dangerous
combination: nobody involved does anything wrong and the board fills with
unearned A's anyway.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from mcp_migrate.cli import main
from mcp_migrate.languages import describe, primary, survey

TS_SOURCE = "export const server = { name: 'demo' };\n"
PY_SOURCE = "import httpx\n\n\ndef fetch(url):\n    return httpx.get(url)\n"


@pytest.fixture
def empty_tree(tmp_path: Path) -> Path:
    d = tmp_path / "empty"
    d.mkdir()
    return d


@pytest.fixture
def ts_tree(tmp_path: Path) -> Path:
    d = tmp_path / "ts-only"
    (d / "src").mkdir(parents=True)
    for name in ("index.ts", "tools.ts", "transport.ts"):
        (d / "src" / name).write_text(TS_SOURCE)
    (d / "package.json").write_text('{"name": "demo"}\n')
    return d


@pytest.fixture
def mixed_tree(tmp_path: Path) -> Path:
    """Mostly TypeScript, with one Python helper script hanging off it."""
    d = tmp_path / "mixed"
    (d / "src").mkdir(parents=True)
    for i in range(6):
        (d / "src" / f"mod{i}.ts").write_text(TS_SOURCE)
    (d / "release.py").write_text(PY_SOURCE)
    return d


@pytest.fixture
def python_tree(tmp_path: Path) -> Path:
    """Mostly Python, with a little TypeScript alongside -- still gradable."""
    d = tmp_path / "py-major"
    (d / "src").mkdir(parents=True)
    for i in range(6):
        (d / "src" / f"mod{i}.py").write_text(PY_SOURCE)
    (d / "web.ts").write_text(TS_SOURCE)
    return d


# --- check refuses ------------------------------------------------------

@pytest.mark.parametrize("fixture", ["empty_tree", "ts_tree"])
def test_check_refuses_and_offers_no_grade(fixture, request, capsys):
    root = request.getfixturevalue(fixture)
    exit_code = main(["check", str(root)])
    out = capsys.readouterr().out

    assert exit_code == 2, "an unreadable tree is neither a pass (0) nor findings (1)"
    assert "Nothing scannable" in out
    assert "Grade" not in out, f"refused to scan but still emitted a grade: {out}"
    assert "img.shields.io" not in out, "refused to scan but still offered a badge"


def test_check_names_the_language_it_found_but_cannot_read(ts_tree, capsys):
    main(["check", str(ts_tree)])
    out = capsys.readouterr().out
    assert "TypeScript" in out, "should say what it found, not just that it gave up"


@pytest.mark.parametrize("fixture", ["empty_tree", "ts_tree"])
def test_check_json_reports_no_grade(fixture, request, capsys):
    root = request.getfixturevalue(fixture)
    exit_code = main(["check", str(root), "--json"])
    data = json.loads(capsys.readouterr().out)

    assert exit_code == 2
    assert data["scannable"] is False
    assert data["grade"] is None, "a null grade is the only honest machine answer here"
    assert data["score"] is None
    assert data["files_scanned"] == 0
    assert data["reason"]


def test_check_json_on_ts_tree_lists_the_languages(ts_tree, capsys):
    main(["check", str(ts_tree), "--json"])
    data = json.loads(capsys.readouterr().out)
    assert data["languages"] == {"typescript": 3}


def test_check_refuses_a_path_that_does_not_exist(tmp_path, capsys):
    # rglob over a missing directory yields nothing, so a typo'd path used
    # to score a clean A.
    exit_code = main(["check", str(tmp_path / "no-such-dir")])
    out = capsys.readouterr().out
    assert exit_code == 2
    assert "No such path" in out
    assert "Grade" not in out


def test_check_still_grades_a_real_python_project(python_tree, capsys):
    exit_code = main(["check", str(python_tree), "--json"])
    data = json.loads(capsys.readouterr().out)
    assert exit_code == 0
    assert data["scannable"] is True
    assert data["grade"] == "A"
    assert data["files_scanned"] == 6


def test_check_on_a_mixed_tree_says_what_it_did_not_read(mixed_tree, capsys):
    # We *can* grade the Python here, so this is not a refusal -- but a
    # grade derived from 1 of 7 files needs to say so out loud.
    exit_code = main(["check", str(mixed_tree)])
    out = capsys.readouterr().out
    assert exit_code == 0
    assert "TypeScript" in out
    assert "not read" in out


def test_check_explains_when_the_only_python_is_test_code(tmp_path, capsys):
    d = tmp_path / "tests-only"
    d.mkdir()
    (d / "test_server.py").write_text(PY_SOURCE)

    exit_code = main(["check", str(d)])
    out = capsys.readouterr().out
    assert exit_code == 2
    assert "Grade" not in out
    assert "--include-tests" in out, "the fix should be in the message"

    # ...and taking that advice makes it scannable.
    assert main(["check", str(d), "--include-tests"]) == 0
    assert "Grade A" in capsys.readouterr().out


# --- entry refuses ------------------------------------------------------

@pytest.mark.parametrize("fixture", ["empty_tree", "ts_tree", "mixed_tree"])
def test_entry_refuses_rather_than_emitting_yaml(fixture, request, capsys):
    root = request.getfixturevalue(fixture)
    exit_code = main(["entry", str(root), "--repo", "acme/demo"])
    captured = capsys.readouterr()

    assert exit_code == 2
    assert captured.out.strip() == "", (
        "stdout is redirected into registry/servers/*.yaml -- a refusal must "
        f"never land in that file, got: {captured.out!r}"
    )
    assert "Refusing" in captured.err


def test_entry_still_works_for_a_python_project(python_tree, capsys):
    exit_code = main(["entry", str(python_tree), "--repo", "acme/demo"])
    out = capsys.readouterr().out
    assert exit_code == 0
    assert "language: python" in out
    assert "grade: A" in out


def test_entry_reports_a_detected_language_not_a_hardcoded_one(python_tree):
    # Guards the specific regression: `language: python` used to be a
    # literal in the f-string, true only by coincidence.
    from mcp_migrate import cli

    source = Path(cli.__file__).read_text()
    assert "language: python" not in source, (
        "`entry` must interpolate a detected language, not hardcode one"
    )


# --- the language survey itself -----------------------------------------

def test_survey_counts_by_language(mixed_tree):
    assert survey(mixed_tree) == {"typescript": 6, "python": 1}


def test_survey_ignores_vendored_directories(tmp_path):
    d = tmp_path / "vendored"
    (d / "node_modules" / "left-pad").mkdir(parents=True)
    (d / "node_modules" / "left-pad" / "index.js").write_text(TS_SOURCE)
    (d / "server.py").write_text(PY_SOURCE)
    # A dependency tree is not the project, and node_modules would swamp
    # the count if it were included.
    assert survey(d) == {"python": 1}


def test_primary_is_none_for_a_tree_with_no_source(empty_tree):
    assert primary(survey(empty_tree)) is None


def test_primary_breaks_ties_toward_a_language_we_can_read(tmp_path):
    d = tmp_path / "tied"
    d.mkdir()
    (d / "a.py").write_text(PY_SOURCE)
    (d / "b.ts").write_text(TS_SOURCE)
    assert primary(survey(d)) == "python"


def test_describe_uses_the_names_people_write(mixed_tree):
    # "6 typescript" reads like a bug report about the tool.
    assert describe(survey(mixed_tree)) == "6 TypeScript, 1 Python"
