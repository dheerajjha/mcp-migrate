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


# Most rules are exercised by legacy_server. R015 cannot be: legacy_server
# imports the official SDK, and the SDK stamps `resultType` on every result it
# serializes, so the rule deliberately stays silent there. Its finding is only
# real for a server that owns its own JSON-RPC envelope, which is what
# handrolled_jsonrpc_server is for. Every rule still has a fixture that fires
# it -- the fixture just isn't the same one for all of them.
RULE_FIXTURES = {"R015": FIXTURES / "handrolled_jsonrpc_server"}


@pytest.mark.parametrize("rule_id", ALL_RULE_IDS)
def test_rule_fires_on_its_fixture(rule_id):
    fixture = RULE_FIXTURES.get(rule_id, LEGACY)
    by_rule = _findings_by_rule(fixture)
    assert rule_id in by_rule, (
        f"{rule_id} should fire on {fixture.name} but produced no findings"
    )


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
    assert data["counts"] == {"breaking": 0, "deprecated": 0, "advisory": 0}
    assert data["files_scanned"] == 2
    assert data["spec"] == "2026-07-28"
    assert data["tool"] == "mcp-migrate"
    assert exit_code == 0, "no breaking findings -> exit code should be 0"


def test_cli_check_json_shape_legacy(capsys):
    exit_code = main(["check", str(LEGACY), "--json"])
    data = json.loads(capsys.readouterr().out)
    assert data["grade"] in ("D", "F")
    assert data["findings"], "expected findings for legacy_server"
    assert sum(data["counts"].values()) == len(data["findings"])
    for finding in data["findings"]:
        assert {"rule", "severity", "path", "line", "message"} <= set(finding)
        assert finding["severity"] in ("breaking", "deprecated", "advisory")
        # A finding with no fix text omits the key rather than emitting null.
        assert "fix" not in finding or finding["fix"]
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


def test_unbounded_suffix_bounded_pattern_issue_87(tmp_path):
    """Issue #87: Bounded suffix alternation for R007, R009, R011, R012 type names.

    Unrelated identifiers ending in ...Requester (e.g. PingRequester) must stay silent,
    while valid SDK schema/params names (e.g. PingRequestSchema, PingRequestParams) must fire.
    """
    # 1. Requester forms must stay silent
    silent_code = (
        "class CreateMessageRequester { send() {} }\n"
        "class InitializeRequester { run() {} }\n"
        "class PingRequester { send() {} }\n"
        "class SetLevelRequester { send() {} }\n"
    )
    f_silent = tmp_path / "silent.py"
    f_silent.write_text(silent_code, encoding="utf-8")
    _, _, findings_silent, _, _ = run_check(tmp_path)
    rule_ids_silent = {f.rule_id for f in findings_silent}
    assert "R007" not in rule_ids_silent
    assert "R009" not in rule_ids_silent
    assert "R011" not in rule_ids_silent
    assert "R012" not in rule_ids_silent

    # 2. Schema and Params forms must fire
    f_silent.unlink()
    firing_code = (
        "server.setRequestHandler(PingRequestSchema, async () => ({}));\n"
        "const req: CreateMessageRequestSchema = {};\n"
        "const init: InitializeRequestSchema = {};\n"
        "const lvl: SetLevelRequestParams = {};\n"
    )
    f_fire = tmp_path / "firing.py"
    f_fire.write_text(firing_code, encoding="utf-8")
    _, _, findings_fire, _, _ = run_check(tmp_path)
    rule_ids_fire = {f.rule_id for f in findings_fire}
    assert "R007" in rule_ids_fire
    assert "R009" in rule_ids_fire
    assert "R011" in rule_ids_fire
    assert "R012" in rule_ids_fire


# The four rules carry a TypeScript-only pattern alongside the Python one,
# and those were a separate set of `\w*` sites that #109 predates. Bounding
# only the Python half would have left the same false positive live for
# every TypeScript project, which is most MCP servers.
FP_87 = [
    ("R011", "helper = PingRequester()"),
    ("R011", "x = PingRequesterFactory()"),
    ("R012", "s = SetLevelRequesterFactory()"),
    ("R012", "y = SetLevelRequestBuilder()"),
    ("R009", "helper = InitializeRequesterHelper()"),
    ("R009", "z = InitializeResultParser()"),
    ("R007", "b = CreateMessageRequestBuilder()"),
    ("R007", "c = CreateMessageResultFormatter()"),
]
TP_87 = [
    ("R011", "x = PingRequestSchema"),
    ("R012", "x = SetLevelRequestParams"),
    ("R009", "z = InitializedNotificationSchema"),
    ("R007", "y = CreateMessageResult"),
]


@pytest.mark.parametrize("ext", [".py", ".ts"])
@pytest.mark.parametrize("rule_id,source", FP_87)
def test_issue_87_false_positives_are_silent_in_both_languages(rule_id, source, ext, tmp_path):
    (tmp_path / f"m{ext}").write_text(source + "\n", encoding="utf-8")
    _, _, findings, _, _ = run_check(tmp_path)
    assert rule_id not in {f.rule_id for f in findings}, (
        f"{rule_id} fires on {source!r} in a {ext} file -- that is #87"
    )


@pytest.mark.parametrize("ext", [".py", ".ts"])
@pytest.mark.parametrize("rule_id,source", TP_87)
def test_issue_87_bounding_does_not_cost_the_real_sdk_names(rule_id, source, ext, tmp_path):
    (tmp_path / f"m{ext}").write_text(source + "\n", encoding="utf-8")
    _, _, findings, _, _ = run_check(tmp_path)
    assert rule_id in {f.rule_id for f in findings}, (
        f"{rule_id} no longer catches {source!r} in a {ext} file -- bounding overshot"
    )
