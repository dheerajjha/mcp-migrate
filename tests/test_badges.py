"""The live badge endpoints.

The badge `check` prints is frozen at the moment it was printed -- it goes
on saying A after the project regresses. These endpoints move the grade
out of the image URL and into a document we regenerate, so the claim can
stop being true in public rather than quietly.

Which makes correctness here load-bearing in an unusual way: these files
render on other people's READMEs, and a wrong one is a wrong claim about
somebody else's project, displayed to their users.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

from render_badges import (  # noqa: E402
    GRADE_COLOR,
    UNKNOWN,
    badge_for,
    badge_for_repo,
    load_entries,
    render,
    slug,
)


def entry(**kw):
    base = {
        "name": "demo", "repo": "acme/demo", "grade": "A", "score": 100,
        "checked_with": "mcp-migrate 0.1.3", "spec": "2026-07-28",
        "status": "ready", "notes": "demo",
    }
    return {**base, **kw}


# --- the shields contract ------------------------------------------------

@pytest.mark.parametrize("grade", list("ABCDF"))
def test_every_grade_renders_a_valid_endpoint_document(grade):
    doc = badge_for(entry(grade=grade))
    assert doc["schemaVersion"] == 1
    assert doc["message"] == grade
    assert doc["color"] == GRADE_COLOR[grade]
    assert isinstance(doc["label"], str) and doc["label"]


@pytest.mark.parametrize("grade,color", [
    ("A", "brightgreen"), ("B", "brightgreen"),
    ("C", "yellow"), ("D", "red"), ("F", "red"),
])
def test_colours_match_the_grades(grade, color):
    # A C rendered in green teaches the reader that the colour means
    # nothing, and then the next badge is not trusted either.
    assert badge_for(entry(grade=grade))["color"] == color


def test_an_unlisted_repo_renders_rather_than_404s(tmp_path):
    # A 404 shows a broken image on a stranger's README. Anyone can point
    # an endpoint URL at us, including at a repo we never scanned.
    render([entry()], tmp_path)
    doc = json.loads((tmp_path / "unknown.json").read_text())
    assert doc["message"] == "not listed"
    assert doc["color"] == "lightgrey"
    assert doc["schemaVersion"] == 1


def test_a_grade_outside_a_to_f_says_unknown_rather_than_inventing_a_colour():
    doc = badge_for(entry(grade="Z"))
    assert doc["message"] == "unknown"
    assert doc["color"] == UNKNOWN["color"]


def test_the_scan_version_is_in_the_label():
    # A badge that renders live but reflects an old scan is only slightly
    # better than a frozen one.
    assert "0.1.3" in badge_for(entry())["label"]


def test_a_missing_version_still_produces_a_clean_label():
    label = badge_for(entry(checked_with=""))["label"]
    assert label == "MCP 2026-07-28"
    assert "()" not in label


# --- monorepos: the case that silently overwrites -----------------------

def test_a_multi_server_repo_reports_its_worst_grade():
    # Three registry entries share `modelcontextprotocol/servers` and
    # three share `awslabs/mcp`. Keyed by repo alone, the last written
    # wins and the badge shows an arbitrary one of the grades.
    group = [entry(name="a", grade="A"), entry(name="b", grade="D"), entry(name="c", grade="B")]
    doc = badge_for_repo(group)
    assert doc["message"] == "D", "a repo containing a D must not advertise an A"
    assert doc["color"] == "red"
    assert "3 servers" in doc["label"]


def test_a_single_server_repo_is_not_labelled_as_a_group():
    doc = badge_for_repo([entry(grade="B")])
    assert doc["message"] == "B"
    assert "servers" not in doc["label"]


def test_each_server_in_a_monorepo_keeps_its_own_endpoint(tmp_path):
    # The aggregate is for the repo README; a server inside a monorepo
    # still needs an address that reports only itself.
    render([
        entry(name="server-git", repo="modelcontextprotocol/servers", grade="A"),
        entry(name="server-fetch", repo="modelcontextprotocol/servers", grade="F"),
    ], tmp_path)

    assert json.loads((tmp_path / "server-git.json").read_text())["message"] == "A"
    assert json.loads((tmp_path / "server-fetch.json").read_text())["message"] == "F"
    assert json.loads(
        (tmp_path / "modelcontextprotocol" / "servers.json").read_text()
    )["message"] == "F"


# --- path handling -------------------------------------------------------

@pytest.mark.parametrize("repo", [
    "", "no-slash", "too/many/parts", "owner/", "/name",
    "../escape/x", "owner/na%me", "owner/na?me",
])
def test_a_repo_that_is_not_plain_owner_name_is_refused(repo):
    # Refused rather than escaped: a malformed `repo` is a registry error
    # worth surfacing, and writing outside docs/badge/ would be worse.
    assert slug(repo) == ""


def test_a_malformed_entry_does_not_stop_the_others(tmp_path):
    # A stale badge is the bug being fixed, so one bad entry must not
    # block every other badge from regenerating.
    written, problems = render([
        entry(name="good", repo="acme/good"),
        entry(name="bad", repo="not-a-repo"),
    ], tmp_path)

    assert (tmp_path / "acme" / "good.json").exists()
    assert problems, "the bad entry should be reported, not silently dropped"
    assert written >= 2


def test_output_stays_inside_the_badge_directory(tmp_path):
    render([entry(name="../escape", repo="../../etc/passwd")], tmp_path)
    for path in tmp_path.rglob("*.json"):
        assert tmp_path in path.resolve().parents or path.parent == tmp_path


# --- against the real registry ------------------------------------------

def test_the_shipped_registry_generates_cleanly(tmp_path):
    entries = load_entries()
    assert entries, "the registry should not be empty"

    written, problems = render(entries, tmp_path)
    assert not problems, f"the shipped registry produced warnings: {problems}"
    assert written >= len(entries)


def test_every_generated_document_is_valid_for_shields(tmp_path):
    render(load_entries(), tmp_path)
    for path in tmp_path.rglob("*.json"):
        doc = json.loads(path.read_text())
        assert doc["schemaVersion"] == 1, path
        assert isinstance(doc["message"], str) and doc["message"], path
        assert doc["color"] in set(GRADE_COLOR.values()) | {"lightgrey"}, path


def test_generation_is_deterministic(tmp_path):
    # It runs in CI and commits the result; nondeterminism would produce
    # an endless stream of no-op commits.
    entries = load_entries()
    a, b = tmp_path / "a", tmp_path / "b"
    render(entries, a)
    render(entries, b)

    files_a = sorted(p.relative_to(a) for p in a.rglob("*.json"))
    files_b = sorted(p.relative_to(b) for p in b.rglob("*.json"))
    assert files_a == files_b
    for rel in files_a:
        assert (a / rel).read_text() == (b / rel).read_text()


def test_grades_match_the_registry_yaml(tmp_path):
    # The badge is a transform, not new analysis -- if it ever disagrees
    # with the YAML it is reporting on, it is the badge that is wrong.
    render(load_entries(), tmp_path)
    for path in sorted((ROOT / "registry" / "servers").glob("*.yaml")):
        data = yaml.safe_load(path.read_text())
        doc = json.loads((tmp_path / f"{data['name']}.json").read_text())
        assert doc["message"] == data["grade"], data["name"]
