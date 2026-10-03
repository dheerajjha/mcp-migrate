"""Baseline file (#181).

The property that matters most here mirrors test_suppress.py's own framing,
inverted: suppression's risk is a finding disappearing from the grade
quietly. A baseline's risk is the opposite direction -- it must NEVER
change the grade, only what can fail the build. Every test under "the
grade, and keeping it honest" below guards that; the rest guards the
matching key surviving reformatting without becoming so loose it stops
meaning anything (the two properties in tension that make this feature
worth getting right).
"""
from __future__ import annotations

import json
from pathlib import Path

from mcp_migrate.baseline import BaselineEntry, apply, load, write
from mcp_migrate.cli import main, run_check_detailed
from mcp_migrate.rules.base import Finding

PY_TRIGGER = "mcp_session_id = request.headers.get('X-Sid')"


def project(tmp_path, name, body):
    tmp_path.mkdir(parents=True, exist_ok=True)
    (tmp_path / name).write_text(body, encoding="utf-8")
    return tmp_path


def entry(rule="R001", path="a.py", snippet="x = 1"):
    return BaselineEntry(rule_id=rule, path=path, snippet=snippet)


def finding(rule="R001", path="a.py", line=1, snippet="x = 1"):
    return Finding(rule_id=rule, message="m", path=Path(path) if path else None,
                    line=line, snippet=snippet)


# --- load/write round-trip -------------------------------------------------

def test_write_then_load_round_trips(tmp_path):
    path = tmp_path / "baseline.json"
    findings = [
        finding("R001", "server.py", 5, "mcp_session_id = 1"),
        finding("R017", None, None, None),  # project-level
    ]
    write(path, findings, version="9.9.9", spec="2026-07-28")
    loaded = load(path)

    assert loaded.warning is None
    assert {(e.rule_id, e.path, e.snippet) for e in loaded.entries} == {
        ("R001", "server.py", "mcp_session_id = 1"),
        ("R017", None, None),
    }


def test_missing_file_is_empty_not_an_error(tmp_path):
    loaded = load(tmp_path / "does-not-exist.json")
    assert loaded.entries == []
    assert loaded.warning is None


def test_malformed_json_warns_and_falls_back_to_empty(tmp_path):
    path = tmp_path / "baseline.json"
    path.write_text("{not json", encoding="utf-8")
    loaded = load(path)
    assert loaded.entries == []
    assert loaded.warning and "invalid JSON" in loaded.warning


def test_wrong_shape_warns_and_falls_back_to_empty(tmp_path):
    path = tmp_path / "baseline.json"
    path.write_text(json.dumps({"not": "a baseline"}), encoding="utf-8")
    loaded = load(path)
    assert loaded.entries == []
    assert loaded.warning


# --- matching: the property this feature exists for -------------------------

def test_a_matching_finding_is_known_not_new():
    result = apply([finding(snippet="mcp_session_id = 1")], [entry(snippet="mcp_session_id = 1")])
    assert result.known and not result.new and not result.stale


def test_a_finding_absent_from_the_baseline_is_new():
    result = apply([finding(snippet="mcp_session_id = 1")], [])
    assert result.new and not result.known


def test_reformatting_does_not_break_the_match():
    # Moved to a different line and reindented -- the exact bug a
    # path:line key would have reintroduced (see BASELINE_PLAN.md).
    f = finding(path="a.py", line=40, snippet="  mcp_session_id   =   1")
    e = entry(path="a.py", snippet="mcp_session_id = 1")
    result = apply([f], [e])
    assert f in result.known
    assert not result.new


def test_a_genuine_content_change_is_new_and_the_old_entry_goes_stale():
    f = finding(snippet="mcp_session_id = 2")  # different value, real change
    e = entry(snippet="mcp_session_id = 1")
    result = apply([f], [e])
    assert f in result.new
    assert e in result.stale


def test_project_level_findings_match_by_rule_id_alone():
    f = finding(rule="R010", path=None, line=None, snippet=None)
    e = entry(rule="R010", path=None, snippet=None)
    result = apply([f], [e])
    assert f in result.known


def test_multiplicity_more_baseline_entries_than_findings_leaves_one_stale():
    # 3 recorded occurrences of the same pattern, only 2 remain today --
    # exactly one instance was fixed.
    entries = [entry(path="a.py", snippet="x") for _ in range(3)]
    findings = [finding(path="a.py", line=i, snippet="x") for i in (1, 2)]
    result = apply(findings, entries)
    assert len(result.known) == 2
    assert len(result.stale) == 1
    assert not result.new


def test_multiplicity_more_findings_than_baseline_entries_reports_the_extra_as_new():
    entries = [entry(path="a.py", snippet="x") for _ in range(3)]
    findings = [finding(path="a.py", line=i, snippet="x") for i in (1, 2, 3, 4)]
    result = apply(findings, entries)
    assert len(result.known) == 3
    assert len(result.new) == 1
    assert not result.stale


def test_same_snippet_different_rule_does_not_cross_match():
    f = finding(rule="R006", snippet="x = 1")
    e = entry(rule="R001", snippet="x = 1")
    result = apply([f], [e])
    assert f in result.new


def test_same_snippet_different_path_does_not_cross_match():
    f = finding(path="b.py", snippet="x = 1")
    e = entry(path="a.py", snippet="x = 1")
    result = apply([f], [e])
    assert f in result.new


# --- the grade, and keeping it honest ---------------------------------------

def test_the_grade_is_identical_with_or_without_a_baseline(tmp_path):
    body = "import httpx\n" + f"{PY_TRIGGER}\n"
    without = run_check_detailed(project(tmp_path / "a", "server.py", body))

    baseline_path = tmp_path / "baseline.json"
    write(baseline_path, without.findings, version="0", spec="2026-07-28")
    with_baseline = run_check_detailed(
        project(tmp_path / "b", "server.py", body), baseline_path=baseline_path,
    )

    assert with_baseline.value == without.value
    assert with_baseline.grade == without.grade
    assert len(with_baseline.findings) == len(without.findings), (
        "a baseline must never remove anything from `findings` -- that's the "
        "list score() consumes, and it's what distinguishes this from suppression"
    )


def test_a_baselined_breaking_finding_no_longer_fails_the_build(tmp_path, capsys):
    body = "import httpx\n" + f"{PY_TRIGGER}\n"
    root = project(tmp_path, "server.py", body)

    assert main(["check", str(root)]) == 1, "sanity: breaking finding fails without a baseline"

    baseline_path = tmp_path / "baseline.json"
    result = run_check_detailed(root)
    write(baseline_path, result.findings, version="0", spec="2026-07-28")

    assert main(["check", str(root), "--baseline", str(baseline_path)]) == 0


def test_a_new_finding_still_fails_the_build_even_with_a_baseline_active(tmp_path):
    baseline_path = tmp_path / "baseline.json"
    write(baseline_path, [], version="0", spec="2026-07-28")  # nothing known yet

    body = "import httpx\n" + f"{PY_TRIGGER}\n"
    root = project(tmp_path / "proj", "server.py", body)
    assert main(["check", str(root), "--baseline", str(baseline_path)]) == 1


def test_missing_baseline_file_means_everything_is_new(tmp_path):
    body = "import httpx\n" + f"{PY_TRIGGER}\n"
    root = project(tmp_path, "server.py", body)
    assert main(["check", str(root), "--baseline", str(tmp_path / "nope.json")]) == 1


# --- --write-baseline --------------------------------------------------------

def test_write_baseline_records_every_current_finding(tmp_path, capsys):
    body = "import httpx\n" + f"{PY_TRIGGER}\n"
    root = project(tmp_path, "server.py", body)
    baseline_path = tmp_path / "baseline.json"

    main(["check", str(root), "--write-baseline", str(baseline_path)])

    data = json.loads(baseline_path.read_text())
    assert data["findings"]
    assert any(e["rule"] == "R001" for e in data["findings"])


def test_write_baseline_exits_clean_even_with_breaking_findings(tmp_path):
    body = "import httpx\n" + f"{PY_TRIGGER}\n"
    root = project(tmp_path, "server.py", body)
    baseline_path = tmp_path / "baseline.json"

    code = main(["check", str(root), "--write-baseline", str(baseline_path)])
    assert code == 0, (
        "everything just found this run was also just recorded -- nothing "
        "is new by construction, which is what --write-baseline is for"
    )


def test_write_baseline_prunes_a_resolved_finding_on_the_next_write(tmp_path):
    baseline_path = tmp_path / "baseline.json"
    dirty = project(tmp_path / "a", "server.py", "import httpx\n" + f"{PY_TRIGGER}\n")
    main(["check", str(dirty), "--write-baseline", str(baseline_path)])
    assert json.loads(baseline_path.read_text())["findings"]

    clean = project(tmp_path / "b", "server.py", "import httpx\n")
    main(["check", str(clean), "--write-baseline", str(baseline_path)])
    assert json.loads(baseline_path.read_text())["findings"] == []


def test_a_clean_project_records_zero_findings(tmp_path, capsys):
    root = project(tmp_path, "server.py", "import httpx\n")
    baseline_path = tmp_path / "baseline.json"
    main(["check", str(root), "--write-baseline", str(baseline_path)])
    assert "recorded 0 finding(s)" in capsys.readouterr().out


# --- output: never hides a finding, never changes shape unless asked -------

def test_json_has_no_baseline_key_when_not_requested(tmp_path, capsys):
    body = "import httpx\n" + f"{PY_TRIGGER}\n"
    root = project(tmp_path, "server.py", body)
    main(["check", str(root), "--json"])
    payload = json.loads(capsys.readouterr().out)
    assert "baseline" not in payload
    assert all("new" not in f for f in payload["findings"]), (
        "a consumer that never asked for a baseline must see byte-identical "
        "finding dicts to before this feature existed"
    )


def test_json_baseline_object_reports_new_and_known_counts(tmp_path, capsys):
    body = "import httpx\n" + f"{PY_TRIGGER}\n"
    root = project(tmp_path, "server.py", body)
    result = run_check_detailed(root)
    baseline_path = tmp_path / "baseline.json"
    write(baseline_path, result.findings, version="0", spec="2026-07-28")

    main(["check", str(root), "--baseline", str(baseline_path), "--json"])
    payload = json.loads(capsys.readouterr().out)

    assert payload["baseline"]["new"] == 0
    assert payload["baseline"]["known"] == len(result.findings)
    assert payload["grade"] == run_check_detailed(root).grade, "grade is unaffected"
    assert all(f["new"] is False for f in payload["findings"])


def test_stale_baseline_entries_are_reported(tmp_path, capsys):
    baseline_path = tmp_path / "baseline.json"
    write(baseline_path, [finding(rule="R099", path="server.py", line=1, snippet="gone now")],
          version="0", spec="2026-07-28")

    root = project(tmp_path / "proj", "server.py", "import httpx\n")
    main(["check", str(root), "--baseline", str(baseline_path), "--json"])
    payload = json.loads(capsys.readouterr().out)

    assert len(payload["baseline"]["stale"]) == 1
    assert payload["baseline"]["stale"][0]["rule"] == "R099"


# --- config -------------------------------------------------------------

def test_config_baseline_path_is_relative_to_the_config_file_not_the_cwd(tmp_path, monkeypatch):
    body = "import httpx\n" + f"{PY_TRIGGER}\n"
    root = project(tmp_path, "server.py", body)
    result = run_check_detailed(root)
    write(root / ".mcp-migrate-baseline.json", result.findings, version="0", spec="2026-07-28")
    (root / ".mcp-migrate.toml").write_text('baseline = ".mcp-migrate-baseline.json"\n', encoding="utf-8")

    monkeypatch.chdir(tmp_path.parent)  # anywhere other than `root`
    assert main(["check", str(root)]) == 0, (
        "a relative `baseline` in config must resolve against the config "
        "file's directory, the same way `mcp-migrate check src/` still "
        "finds the repo's config regardless of the caller's CWD"
    )


def test_config_baseline_key_is_used_when_no_flag_given(tmp_path):
    body = "import httpx\n" + f"{PY_TRIGGER}\n"
    root = project(tmp_path, "server.py", body)
    baseline_path = tmp_path / "known.json"
    result = run_check_detailed(root)
    write(baseline_path, result.findings, version="0", spec="2026-07-28")

    (root / ".mcp-migrate.toml").write_text(f'baseline = "{baseline_path}"\n', encoding="utf-8")

    assert main(["check", str(root)]) == 0, (
        "a flag beats config, but config should turn baselining on project-wide "
        "when no flag is given, same precedence rule as every other setting"
    )
