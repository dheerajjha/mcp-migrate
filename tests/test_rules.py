"""End-to-end rule and CLI tests, run against two realistic fixture servers:

- fixtures/legacy_server: written for the pre-2026-07-28 spec, should trip
  every rule (R001-R021).
- fixtures/clean_server: stateless, streamable-HTTP, extensions-declared,
  sorted tools -- should trip nothing and grade A.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from mcp_migrate.cli import main, run_check
from mcp_migrate.rules import all_rules

FIXTURES = Path(__file__).parent / "fixtures"
LEGACY = FIXTURES / "legacy_server"
CLEAN = FIXTURES / "clean_server"

ALL_RULE_IDS = [r.id for r in all_rules()]


def _findings_by_rule(root: Path) -> dict[str, list]:
    _, _, findings, _, _ = run_check(root)
    by_rule: dict[str, list] = {}
    for f in findings:
        by_rule.setdefault(f.rule_id, []).append(f)
    return by_rule


def test_all_rules_are_registered():
    assert ALL_RULE_IDS == [f"R{i:03d}" for i in range(1, 22)]


@pytest.mark.parametrize("rule_id", ALL_RULE_IDS)
def test_rule_fires_on_legacy_server(rule_id):
    by_rule = _findings_by_rule(LEGACY)
    assert rule_id in by_rule, f"{rule_id} should fire on legacy_server but produced no findings"


@pytest.mark.parametrize("rule_id", ALL_RULE_IDS)
def test_rule_does_not_fire_on_clean_server(rule_id):
    by_rule = _findings_by_rule(CLEAN)
    assert rule_id not in by_rule, f"{rule_id} fired on clean_server: {by_rule[rule_id]}"


def test_clean_server_has_zero_findings_and_grades_a():
    _, _, findings, value, grade = run_check(CLEAN)
    assert findings == []
    assert value == 100
    assert grade == "A"


def test_legacy_server_grades_d_or_f():
    _, _, findings, value, grade = run_check(LEGACY)
    assert findings, "legacy_server should have findings"
    assert grade in ("D", "F"), f"expected D or F, got {grade} (score={value})"


def test_legacy_server_has_breaking_findings():
    by_rule = _findings_by_rule(LEGACY)
    rules = {r.id: r for r in all_rules()}
    breaking = [rid for rid in by_rule if rules[rid].severity == "breaking"]
    assert breaking, "legacy_server should trip at least one breaking rule"


# --- CLI end to end -----------------------------------------------------

def test_cli_check_json_shape_clean(capsys):
    exit_code = main(["check", str(CLEAN), "--json"])
    data = json.loads(capsys.readouterr().out)
    assert data["grade"] == "A"
    assert data["score"] == 100
    assert data["findings"] == []
    assert data["files_scanned"] == 2
    assert data["spec"] == "2026-07-28"
    assert exit_code == 0, "no breaking findings -> exit code should be 0"


def test_cli_check_json_shape_legacy(capsys):
    exit_code = main(["check", str(LEGACY), "--json"])
    data = json.loads(capsys.readouterr().out)
    assert data["grade"] in ("D", "F")
    assert data["findings"], "expected findings for legacy_server"
    for finding in data["findings"]:
        assert set(finding) == {"rule", "severity", "message", "location"}
        assert finding["severity"] in ("breaking", "deprecated", "advisory")
    assert any(f["rule"] == rid for rid in ALL_RULE_IDS for f in data["findings"])
    assert exit_code == 1, "breaking findings present -> exit code should be 1"


def test_cli_check_human_output_does_not_crash(capsys):
    exit_code = main(["check", str(LEGACY)])
    out = capsys.readouterr().out
    assert "Grade" in out
    assert exit_code == 1

    exit_code = main(["check", str(CLEAN)])
    out = capsys.readouterr().out
    assert "Grade A" in out
    assert exit_code == 0


def test_cli_rules_command_lists_all_rules(capsys):
    exit_code = main(["rules"])
    out = capsys.readouterr().out
    assert exit_code == 0
    for rule_id in ALL_RULE_IDS:
        assert rule_id in out


def test_cli_entry_command_prints_registry_yaml(capsys):
    exit_code = main(["entry", str(CLEAN), "--repo", "acme/notes-mcp"])
    out = capsys.readouterr().out
    assert exit_code == 0
    assert "name: notes-mcp" in out
    assert "repo: acme/notes-mcp" in out
    assert "grade: A" in out
