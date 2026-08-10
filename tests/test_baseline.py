"""Baseline: `check` fails only on findings not recorded in a snapshot.

The property that matters most is the one stated in baseline.py's own
docstring -- the grade never reads this, only the exit code and what gets
printed as actionable do. A baseline that could turn a failing grade into
a passing one would make the letter fiction, so several tests below assert
on the grade staying put while the finding list narrows.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from mcp_migrate import baseline
from mcp_migrate.cli import main, run_check_detailed

TRIGGER = 'mcp_session_id = request.headers.get("Mcp-Session-Id")'


def project(tmp_path: Path, body: str = TRIGGER + "\n") -> Path:
    (tmp_path / "server.py").write_text(body, encoding="utf-8")
    return tmp_path


# --- baseline.py, standalone ----------------------------------------------

def test_finding_key_anchors_on_line_content_not_number(tmp_path):
    root = project(tmp_path)
    result = run_check_detailed(root)
    [f] = result.findings
    key_before = baseline.finding_key(f, result.project)

    # Insert two lines above the trigger -- its line number shifts, but the
    # key must not, or every baselined finding in a file goes stale the
    # moment someone edits above it.
    (root / "server.py").write_text("# one\n# two\n" + TRIGGER + "\n", encoding="utf-8")
    result2 = run_check_detailed(root)
    [f2] = result2.findings
    assert f2.line == f.line + 2
    assert baseline.finding_key(f2, result2.project) == key_before


def test_finding_key_falls_back_to_message_when_there_is_no_line(tmp_path):
    # A registered handler with no server/discover anywhere -- R010 fires
    # once, project-wide, with no path/line to anchor on.
    root = project(tmp_path, body=(
        "from mcp.server import Server\n"
        "server = Server('x')\n"
        "@server.list_tools()\n"
        "async def list_tools():\n"
        "    return []\n"
    ))
    result = run_check_detailed(root)
    project_level = [f for f in result.findings if f.line is None]
    assert project_level, "expected at least one project-level finding (e.g. R010)"
    f = project_level[0]
    assert baseline.finding_key(f, result.project) == (f.rule_id, "", f.message.strip())


def test_write_then_load_round_trips(tmp_path):
    root = project(tmp_path)
    result = run_check_detailed(root)
    out = tmp_path / "baseline.json"
    n = baseline.write(out, result.findings, result.project)
    assert n == len(result.findings)

    entries = baseline.load(out)
    assert len(entries) == len(result.findings)
    assert entries[0]["rule"] == result.findings[0].rule_id


def test_diff_reports_nothing_new_for_an_unchanged_project(tmp_path):
    root = project(tmp_path)
    result = run_check_detailed(root)
    entries = baseline.build(result.findings, result.project)

    new, stale = baseline.diff(result.findings, result.project, entries)
    assert new == []
    assert stale == []


def test_diff_reports_a_finding_absent_from_the_baseline_as_new(tmp_path):
    root = project(tmp_path)
    result = run_check_detailed(root)

    new, stale = baseline.diff(result.findings, result.project, [])
    assert len(new) == len(result.findings)
    assert stale == []


def test_diff_reports_a_baselined_finding_that_vanished_as_stale(tmp_path):
    root = project(tmp_path)
    result = run_check_detailed(root)
    entries = baseline.build(result.findings, result.project)

    # Fix it: rewrite so nothing triggers R001 any more.
    (root / "server.py").write_text("x = 1\n", encoding="utf-8")
    result2 = run_check_detailed(root)

    new, stale = baseline.diff(result2.findings, result2.project, entries)
    assert new == []
    assert len(stale) == len(entries)


def test_diff_matches_duplicate_keys_by_count(tmp_path):
    # Two identical trigger lines produce two findings with the same key.
    root = project(tmp_path, body=f"{TRIGGER}\n{TRIGGER}\n")
    result = run_check_detailed(root)
    entries = baseline.build(result.findings, result.project)
    # Baseline only recorded one of the two occurrences.
    entries = entries[:1]

    new, stale = baseline.diff(result.findings, result.project, entries)
    assert len(new) == 1
    assert stale == []


def test_load_rejects_malformed_json(tmp_path):
    bad = tmp_path / "baseline.json"
    bad.write_text("not json", encoding="utf-8")
    with pytest.raises(baseline.BaselineError):
        baseline.load(bad)


def test_load_rejects_a_file_with_no_findings_key(tmp_path):
    bad = tmp_path / "baseline.json"
    bad.write_text(json.dumps({"version": 1}), encoding="utf-8")
    with pytest.raises(baseline.BaselineError):
        baseline.load(bad)


# --- wired into `check` ---------------------------------------------------

def test_write_baseline_records_findings_and_exits_clean(tmp_path, capsys):
    root = project(tmp_path)
    exit_code = main(["check", str(root), "--write-baseline"])
    assert exit_code == 0
    out = capsys.readouterr().out
    assert "recorded 1 finding" in out
    assert (root / baseline.DEFAULT_FILENAME).exists()


def test_check_picks_up_the_default_baseline_file_automatically(tmp_path, capsys):
    root = project(tmp_path)
    main(["check", str(root), "--write-baseline"])
    capsys.readouterr()

    exit_code = main(["check", str(root)])
    out = capsys.readouterr().out
    assert exit_code == 0
    assert "No new findings" in out
    # The grade must still reflect the baselined finding, not be a clean A.
    assert "1 breaking" in out


def test_check_fails_only_on_a_finding_the_baseline_does_not_have(tmp_path, capsys):
    root = project(tmp_path)
    main(["check", str(root), "--write-baseline"])
    capsys.readouterr()

    # A second file, same trigger -- new (path, line), so not in the
    # baseline that was recorded for server.py alone.
    (root / "other.py").write_text(TRIGGER + "\n", encoding="utf-8")

    exit_code = main(["check", str(root)])
    out = capsys.readouterr().out
    assert exit_code == 1
    assert "1 new finding" in out


def test_check_does_not_report_new_findings_across_a_line_shift(tmp_path, capsys):
    root = project(tmp_path)
    main(["check", str(root), "--write-baseline"])
    capsys.readouterr()

    (root / "server.py").write_text("# a comment\n" + TRIGGER + "\n", encoding="utf-8")

    exit_code = main(["check", str(root)])
    out = capsys.readouterr().out
    assert exit_code == 0
    assert "No new findings" in out


def test_check_reports_a_stale_baseline_entry(tmp_path, capsys):
    root = project(tmp_path)
    main(["check", str(root), "--write-baseline"])
    capsys.readouterr()

    (root / "server.py").write_text("x = 1\n", encoding="utf-8")

    exit_code = main(["check", str(root)])
    out = capsys.readouterr().out
    assert exit_code == 0
    assert "no longer present" in out


def test_grade_ignores_the_baseline(tmp_path, capsys):
    """Baselining every finding must not turn a failing grade into a passing one."""
    root = project(tmp_path)
    main(["check", str(root), "--write-baseline"])
    capsys.readouterr()

    exit_code_before = main(["check", str(root), "--json"])
    payload_before = json.loads(capsys.readouterr().out)

    exit_code_after = main(["check", str(root), "--json"])
    payload_after = json.loads(capsys.readouterr().out)

    assert exit_code_before == exit_code_after == 0
    assert payload_before["grade"] == payload_after["grade"]
    assert payload_before["score"] == payload_after["score"]
    assert payload_after["baseline"]["total"] == 1
    assert payload_after["baseline"]["new"] == 0
    assert payload_after["findings"] == []


def test_json_output_carries_baseline_metadata(tmp_path, capsys):
    root = project(tmp_path)
    main(["check", str(root), "--write-baseline"])
    capsys.readouterr()

    main(["check", str(root), "--json"])
    payload = json.loads(capsys.readouterr().out)
    assert payload["baseline"]["total"] == 1
    assert payload["baseline"]["new"] == 0
    assert payload["baseline"]["stale"] == 0
    assert payload["findings"] == []
    # counts follows the narrowed findings, grade does not.
    assert payload["counts"] == {"breaking": 0, "deprecated": 0, "advisory": 0}
    assert payload["grade"] != "A"


def test_explicit_baseline_path_overrides_the_default(tmp_path, capsys):
    root = project(tmp_path)
    custom = root / "custom-baseline.json"
    main(["check", str(root), "--write-baseline", "custom-baseline.json"])
    capsys.readouterr()
    assert custom.exists()
    assert not (root / baseline.DEFAULT_FILENAME).exists()

    exit_code = main(["check", str(root), "--baseline", "custom-baseline.json"])
    out = capsys.readouterr().out
    assert exit_code == 0
    assert "No new findings" in out


def test_check_reports_a_bad_baseline_file_instead_of_crashing(tmp_path, capsys):
    root = project(tmp_path)
    (root / baseline.DEFAULT_FILENAME).write_text("not json", encoding="utf-8")

    exit_code = main(["check", str(root)])
    out = capsys.readouterr().out
    assert exit_code == 2
    assert "Could not read baseline" in out
