import importlib.util
import json
from pathlib import Path
import subprocess

import pytest


spec = importlib.util.spec_from_file_location(
    "report_board_drift", Path(__file__).resolve().parents[1] / "scripts" / "report_board_drift.py"
)
reporter = importlib.util.module_from_spec(spec)
spec.loader.exec_module(reporter)


@pytest.fixture
def run_report(tmp_path, monkeypatch):
    calls = []
    pages = []
    monkeypatch.setenv("GITHUB_REPOSITORY", "owner/repo")

    def fake_run(args, **kwargs):
        calls.append((args, kwargs.get("input")))
        return subprocess.CompletedProcess(args, 0, json.dumps(pages), "")

    monkeypatch.setattr(reporter.subprocess, "run", fake_run)

    def run(data, status):
        path = tmp_path / "regrade.json"
        path.write_text(json.dumps(data), encoding="utf-8")
        return reporter.report(path, status)

    return run, calls, pages


def test_clean_result_does_not_write(run_report):
    run, calls, _ = run_report
    assert run({"drifts": [], "problems": []}, 0) == 0
    assert calls == []


def test_drift_opens_issue_with_values_and_safe_data(run_report):
    run, calls, _ = run_report
    drift = {"entry": {"name": "example", "recorded_grade": "A"}, "actual": {"grade": "B"}}
    assert run({"drifts": [drift], "problems": []}, 1) == 1
    assert len(calls) == 2
    payload = json.loads(calls[1][1])
    assert '"recorded_grade": "A"' in payload["body"]
    assert '"grade": "B"' in payload["body"]
    assert all(line.startswith("    ") for line in payload["body"].splitlines()[3:])


def test_existing_bot_report_prevents_duplicate_across_pages(run_report):
    run, calls, pages = run_report
    pages.extend([[], [{"user": {"login": "github-actions[bot]"}, "body": reporter.MARKER}]])
    assert run({"drifts": [{}], "problems": []}, 1) == 1
    assert len(calls) == 1


def test_operational_problem_does_not_create_drift_issue(run_report, capsys):
    run, calls, _ = run_report
    assert run({"drifts": [], "problems": ["fetch failed"]}, 1) == 1
    assert "fetch failed" in capsys.readouterr().err
    assert calls == []


def test_drift_and_operational_problems_are_both_reported(run_report, capsys):
    run, calls, _ = run_report
    assert run({"drifts": [{}], "problems": ["fetch failed"]}, 1) == 1
    assert len(calls) == 2
    assert "fetch failed" in capsys.readouterr().err


@pytest.mark.parametrize("status,data", [(2, {}), (1, {"drifts": [], "problems": []})])
def test_invalid_or_failed_run_never_creates_issue(run_report, status, data):
    run, calls, _ = run_report
    assert run(data, status) == 2
    assert calls == []


def test_api_failure_is_not_hidden(run_report, monkeypatch):
    run, _, _ = run_report

    def fail(*args, **kwargs):
        raise subprocess.CalledProcessError(1, "gh")

    monkeypatch.setattr(reporter.subprocess, "run", fail)
    with pytest.raises(subprocess.CalledProcessError):
        run({"drifts": [{}], "problems": []}, 1)
