"""`check --rule`/`--severity`/`--fail-on` -- see #178.

`--rule` restricts which rules run at all and, because a grade computed
from part of the rule set isn't a grade, suppresses `grade`/`score`.
`--severity` only ever changes what's displayed -- the grade and exit code
must always come from the full finding set. `--fail-on` replaces the
previously-hardcoded "fail only on breaking" exit logic, and `2` ("could
not check it") must stay outside of it no matter the setting.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from mcp_migrate.cli import main

PYPROJECT = '[project]\nname = "my_mcp_server"\nversion = "1.0.0"\n'

# R001 (breaking) + R006 (deprecated), nothing else.
MIXED_SEVERITY_SOURCE = (
    'mcp_session_id = None\n'
    'mcp.run(transport="sse")\n'
)

# R006 (deprecated) only.
DEPRECATED_ONLY_SOURCE = 'mcp.run(transport="sse")\n'


@pytest.fixture
def mixed_severity_tree(tmp_path: Path) -> Path:
    (tmp_path / "pyproject.toml").write_text(PYPROJECT, encoding="utf-8")
    (tmp_path / "server.py").write_text(MIXED_SEVERITY_SOURCE, encoding="utf-8")
    return tmp_path


@pytest.fixture
def deprecated_only_tree(tmp_path: Path) -> Path:
    (tmp_path / "pyproject.toml").write_text(PYPROJECT, encoding="utf-8")
    (tmp_path / "server.py").write_text(DEPRECATED_ONLY_SOURCE, encoding="utf-8")
    return tmp_path


# --- check --rule --------------------------------------------------------

def test_check_rule_restricts_findings_and_suppresses_grade(mixed_severity_tree, capsys):
    exit_code = main(["check", str(mixed_severity_tree), "--json", "--rule", "R006"])
    data = json.loads(capsys.readouterr().out)

    assert exit_code == 0  # R006 is deprecated, default --fail-on is breaking
    assert data["rule_filtered"] is True
    assert data["filters"] == {"rule": ["R006"], "severity": []}
    assert {f["rule"] for f in data["findings"]} == {"R006"}
    assert data["grade"] is None
    assert data["score"] is None


def test_check_rule_is_repeatable(mixed_severity_tree, capsys):
    exit_code = main([
        "check", str(mixed_severity_tree), "--json",
        "--rule", "R001", "--rule", "R006",
    ])
    data = json.loads(capsys.readouterr().out)

    assert exit_code == 1  # R001 is breaking
    assert data["filters"]["rule"] == ["R001", "R006"]
    assert {f["rule"] for f in data["findings"]} == {"R001", "R006"}


def test_check_unknown_rule_id_is_a_usage_error(mixed_severity_tree, capsys):
    with pytest.raises(SystemExit) as excinfo:
        main(["check", str(mixed_severity_tree), "--rule", "R999"])
    assert excinfo.value.code == 2


def test_check_without_rule_still_reports_a_grade(mixed_severity_tree, capsys):
    exit_code = main(["check", str(mixed_severity_tree), "--json"])
    data = json.loads(capsys.readouterr().out)

    assert exit_code == 1
    assert data["rule_filtered"] is False
    assert data["grade"] is not None
    assert data["score"] is not None


# --- check --severity ------------------------------------------------------

def test_check_severity_narrows_findings_but_not_grade(mixed_severity_tree, capsys):
    unfiltered_exit = main(["check", str(mixed_severity_tree), "--json"])
    unfiltered = json.loads(capsys.readouterr().out)

    filtered_exit = main([
        "check", str(mixed_severity_tree), "--json", "--severity", "deprecated",
    ])
    filtered = json.loads(capsys.readouterr().out)

    assert filtered["filters"] == {"rule": [], "severity": ["deprecated"]}
    assert {f["rule"] for f in filtered["findings"]} == {"R006"}
    # Same grade, same score, same exit code -- filtering display never
    # changes the answer to "does this pass".
    assert filtered["grade"] == unfiltered["grade"]
    assert filtered["score"] == unfiltered["score"]
    assert filtered_exit == unfiltered_exit


def test_check_severity_composes_with_rule(mixed_severity_tree, capsys):
    main([
        "check", str(mixed_severity_tree), "--json",
        "--rule", "R001", "--rule", "R006", "--severity", "deprecated",
    ])
    data = json.loads(capsys.readouterr().out)

    assert data["filters"] == {"rule": ["R001", "R006"], "severity": ["deprecated"]}
    assert {f["rule"] for f in data["findings"]} == {"R006"}


def test_check_severity_text_output_says_what_it_filtered(mixed_severity_tree, capsys):
    main(["check", str(mixed_severity_tree), "--severity", "deprecated"])
    out = capsys.readouterr().out
    assert "1 of 2 finding(s) shown" in out


# --- check --fail-on -------------------------------------------------------

def test_check_fail_on_defaults_to_breaking(deprecated_only_tree, capsys):
    exit_code = main(["check", str(deprecated_only_tree)])
    capsys.readouterr()
    assert exit_code == 0  # only a deprecated finding, default threshold is breaking


def test_check_fail_on_deprecated_fails_a_deprecated_only_project(deprecated_only_tree, capsys):
    exit_code = main(["check", str(deprecated_only_tree), "--fail-on", "deprecated"])
    capsys.readouterr()
    assert exit_code == 1


def test_check_fail_on_never_never_fails_on_findings(mixed_severity_tree, capsys):
    exit_code = main(["check", str(mixed_severity_tree), "--fail-on", "never"])
    capsys.readouterr()
    assert exit_code == 0


def test_check_fail_on_never_still_exits_2_for_an_unreadable_tree(tmp_path, capsys):
    empty = tmp_path / "empty"
    empty.mkdir()
    for fail_on in ("breaking", "deprecated", "advisory", "never"):
        exit_code = main(["check", str(empty), "--fail-on", fail_on])
        capsys.readouterr()
        assert exit_code == 2, f"--fail-on {fail_on} must not suppress exit 2"


def test_check_json_echoes_fail_on(mixed_severity_tree, capsys):
    main(["check", str(mixed_severity_tree), "--json", "--fail-on", "deprecated"])
    data = json.loads(capsys.readouterr().out)
    assert data["fail_on"] == "deprecated"
