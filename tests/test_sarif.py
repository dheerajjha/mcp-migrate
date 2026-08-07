"""SARIF 2.1.0 output, validated against the vendored official schema.

The schema is checked in rather than fetched. A test that pulls a schema
over the network is a flake waiting to happen, and this one runs on four
Python versions per push.
"""
from __future__ import annotations

import json
from pathlib import Path

import jsonschema
import pytest

from mcp_migrate import __version__
from mcp_migrate.cli import main
from mcp_migrate.rules import all_rules
from mcp_migrate.sarif import LEVEL, _spec_uri

ROOT = Path(__file__).resolve().parent.parent
SCHEMA = json.loads(
    (ROOT / "schemas" / "sarif-2.1.0.schema.json").read_text(encoding="utf-8")
)
FIXTURES = ROOT / "tests" / "fixtures"


def run_sarif(capsys, root: Path, *extra) -> tuple[dict, int]:
    exit_code = main(["check", str(root), "--format", "sarif", *extra])
    doc = json.loads(capsys.readouterr().out)
    jsonschema.validate(doc, SCHEMA)
    return doc, exit_code


def only_run(doc: dict) -> dict:
    assert len(doc["runs"]) == 1
    return doc["runs"][0]


# --- the schema contract -------------------------------------------------

@pytest.mark.parametrize("fixture", ["clean_server", "legacy_server"])
def test_output_validates_against_the_official_schema(capsys, fixture):
    doc, _ = run_sarif(capsys, FIXTURES / fixture)
    assert doc["version"] == "2.1.0"


def test_an_empty_run_is_still_emitted(capsys):
    # Code scanning needs a run even when nothing was found, or it cannot
    # tell "checked, clean" from "never ran" -- and then it leaves already
    # resolved alerts open forever.
    doc, exit_code = run_sarif(capsys, FIXTURES / "clean_server")
    run = only_run(doc)
    assert run["results"] == []
    assert run["tool"]["driver"]["rules"], "the driver must still declare its rules"
    assert exit_code == 0


def test_the_driver_declares_every_rule_not_just_the_ones_that_fired(capsys):
    doc, _ = run_sarif(capsys, FIXTURES / "legacy_server")
    declared = {r["id"] for r in only_run(doc)["tool"]["driver"]["rules"]}
    assert declared == {r.id for r in all_rules()}


def test_driver_metadata(capsys):
    driver = only_run(run_sarif(capsys, FIXTURES / "legacy_server")[0])["tool"]["driver"]
    assert driver["name"] == "mcp-migrate"
    assert driver["version"] == __version__
    assert driver["informationUri"].startswith("https://")


# --- severity mapping ----------------------------------------------------

@pytest.mark.parametrize("severity,level", [
    ("breaking", "error"),
    ("deprecated", "warning"),
    ("advisory", "note"),
])
def test_severity_maps_to_the_documented_level(severity, level):
    assert LEVEL[severity] == level


def test_deprecated_does_not_block_a_pull_request_by_default(capsys):
    # Code scanning's default gate fails on `error` alone. The spec gives
    # deprecated features 12+ months, so mapping them to `error` would
    # make every server using Roots or Sampling unmergeable today over a
    # change that does not break until next year.
    doc, _ = run_sarif(capsys, FIXTURES / "legacy_server")
    run = only_run(doc)
    by_id = {r["id"]: r for r in run["tool"]["driver"]["rules"]}

    for result in run["results"]:
        rule = by_id[result["ruleId"]]
        severity = rule["properties"]["mcp-migrate.severity"]
        if severity == "deprecated":
            assert result["level"] == "warning"


def test_every_result_level_matches_its_rule_severity(capsys):
    doc, _ = run_sarif(capsys, FIXTURES / "legacy_server")
    run = only_run(doc)
    rules = {r.id: r for r in all_rules()}
    for result in run["results"]:
        assert result["level"] == LEVEL[rules[result["ruleId"]].severity]


def test_rule_index_points_at_the_right_descriptor(capsys):
    # ruleIndex is an offset into the driver's rules array. Off by one and
    # every finding is attributed to the wrong rule, with no error.
    doc, _ = run_sarif(capsys, FIXTURES / "legacy_server")
    run = only_run(doc)
    declared = run["tool"]["driver"]["rules"]
    for result in run["results"]:
        assert declared[result["ruleIndex"]]["id"] == result["ruleId"]


# --- locations -----------------------------------------------------------

def test_paths_are_relative_to_the_scanned_root(capsys):
    # Code scanning matches results to the diff by path. An absolute path
    # from the scanning machine matches nothing, and the annotations
    # silently never appear.
    doc, _ = run_sarif(capsys, FIXTURES / "legacy_server")
    for result in only_run(doc)["results"]:
        for loc in result["locations"]:
            uri = loc["physicalLocation"]["artifactLocation"]["uri"]
            assert not uri.startswith("/"), uri
            assert ".." not in uri, uri
            assert "\\" not in uri, "URIs are forward-slashed on every platform"


def test_line_numbers_survive(capsys):
    doc, _ = run_sarif(capsys, FIXTURES / "legacy_server")
    regions = [
        loc["physicalLocation"].get("region")
        for result in only_run(doc)["results"]
        for loc in result["locations"]
    ]
    assert any(r and r["startLine"] > 0 for r in regions)


def test_a_project_level_finding_still_produces_a_result(capsys):
    # R010 asks a question about the whole tree and has no file. Dropping
    # such findings would silently lose them; SARIF allows an empty
    # locations array.
    doc, _ = run_sarif(capsys, FIXTURES / "legacy_server")
    run = only_run(doc)
    assert all("locations" in r for r in run["results"])


# --- helpUri -------------------------------------------------------------

def test_spec_refs_that_are_urls_become_help_uris(capsys):
    doc, _ = run_sarif(capsys, FIXTURES / "legacy_server")
    declared = only_run(doc)["tool"]["driver"]["rules"]
    assert any("helpUri" in r for r in declared)
    for rule in declared:
        if "helpUri" in rule:
            assert rule["helpUri"].startswith("http")


def test_a_prose_spec_ref_does_not_become_an_invalid_help_uri():
    # "Roots, Sampling and Logging deprecated" is not a URI; emitting it
    # as one makes consumers reject the whole document.
    assert _spec_uri("Roots, Sampling and Logging deprecated") == ""
    assert _spec_uri("SEP-2567 https://github.com/x/y/pull/1") == "https://github.com/x/y/pull/1"


# --- CLI surface ---------------------------------------------------------

def test_json_remains_an_alias_and_does_not_emit_sarif(capsys):
    # --json predates --format and is depended on; it must keep working
    # and must keep its own shape.
    main(["check", str(FIXTURES / "legacy_server"), "--json"])
    payload = json.loads(capsys.readouterr().out)
    assert payload["tool"] == "mcp-migrate"
    assert "runs" not in payload


def test_format_json_matches_the_json_flag(capsys):
    main(["check", str(FIXTURES / "legacy_server"), "--json"])
    from_flag = capsys.readouterr().out
    main(["check", str(FIXTURES / "legacy_server"), "--format", "json"])
    from_format = capsys.readouterr().out
    assert from_flag == from_format


def test_exit_codes_are_unchanged_by_the_format(capsys):
    # The format decides what is printed, never what is returned.
    for fixture, expected in (("clean_server", 0), ("legacy_server", 1)):
        sarif_code = main(["check", str(FIXTURES / fixture), "--format", "sarif"])
        capsys.readouterr()
        json_code = main(["check", str(FIXTURES / fixture), "--json"])
        capsys.readouterr()
        assert sarif_code == json_code == expected, fixture


def test_an_unreadable_tree_still_emits_a_valid_document(capsys, tmp_path):
    doc, exit_code = run_sarif(capsys, tmp_path)
    assert only_run(doc)["results"] == []
    assert exit_code == 2



# --- suppression and SARIF, which landed as two independent PRs -----------
#
# #182 and #180 were written against separate branches and each passed on
# its own. Nothing exercised the pair until they were merged, and the
# failure mode is quiet in the worst way: a finding a maintainer had
# deliberately silenced would still open a code-scanning alert on their
# pull request, which is precisely the thing suppression exists to stop.

SUPPRESSED_AND_LIVE = """\
import mcp
mcp_session_id = None  # mcp-migrate: ignore[R001] -- handle is a tool arg now
other = mcp_session_id
value = 1  # mcp-migrate: ignore[R004] -- this one matches nothing
"""


def test_a_suppressed_finding_does_not_become_a_code_scanning_alert(capsys, tmp_path):
    (tmp_path / "s.py").write_text(SUPPRESSED_AND_LIVE)
    doc, _ = run_sarif(capsys, tmp_path)
    hits = [
        (r["ruleId"], r["locations"][0]["physicalLocation"]["region"]["startLine"])
        for r in only_run(doc)["results"]
        if r.get("locations")
    ]
    # Line 2 carries the directive; line 3 trips the same rule and does not.
    assert hits == [("R001", 3)], hits


def test_every_format_agrees_on_what_suppression_removed(capsys, tmp_path):
    (tmp_path / "s.py").write_text(SUPPRESSED_AND_LIVE)

    doc, sarif_exit = run_sarif(capsys, tmp_path)
    sarif_hits = {
        (r["ruleId"], r["locations"][0]["physicalLocation"]["region"]["startLine"])
        for r in only_run(doc)["results"]
        if r.get("locations")
    }

    json_exit = main(["check", str(tmp_path), "--format", "json"])
    payload = json.loads(capsys.readouterr().out)
    json_hits = {(f["rule"], f["line"]) for f in payload["findings"]}

    assert sarif_hits == json_hits
    assert sarif_exit == json_exit
    # And the suppressed one is accounted for rather than simply gone.
    assert [(s["rule"], s["line"]) for s in payload["suppressed"]] == [("R001", 2)]
    assert [(u["rule"], u["line"]) for u in payload["unused_suppressions"]] == [
        ("R004", 4)
    ]
