"""Run mcp-migrate against its own source tree.

This is the "does it survive contact with a real, moderately-sized Python
project" test. It deliberately does not assert a particular grade or an
empty finding list: mcp-migrate's rule modules necessarily contain the very
strings they search for (e.g. r001_session_id_removed.py mentions "Mcp-Session-Id"
in its own pattern and docstring), so self-scanning is expected to produce
some findings. What matters is that scanning a real tree never raises.
"""
from __future__ import annotations

import json
from pathlib import Path

from mcp_migrate.cli import main, run_check

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "src"


def test_selfcheck_does_not_crash():
    project, rules, findings, value, grade = run_check(SRC)
    assert project.files, "expected to find at least one .py file under src/"
    assert isinstance(findings, list)
    assert 0 <= value <= 100
    assert grade in "ABCDF"
    for f in findings:
        assert f.rule_id in rules, f"finding references unknown rule {f.rule_id!r}"


def test_selfcheck_cli_json_does_not_crash(capsys):
    exit_code = main(["check", str(SRC), "--json"])
    data = json.loads(capsys.readouterr().out)
    assert data["files_scanned"] > 0
    assert exit_code in (0, 1)


def test_selfcheck_cli_human_output_does_not_crash(capsys):
    exit_code = main(["check", str(SRC)])
    out = capsys.readouterr().out
    assert "mcp-migrate" in out
    assert exit_code in (0, 1)


def test_selfcheck_whole_repo_root_does_not_crash():
    # Includes tests/, scripts/, registry/ -- a messier, more realistic tree
    # than just src/, and a good crash test for rules that walk imports or
    # asts across a wider variety of files (including this very test file).
    project, rules, findings, value, grade = run_check(ROOT)
    assert project.files
    assert isinstance(findings, list)
    assert grade in "ABCDF"
