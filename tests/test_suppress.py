"""Inline suppression.

The property that matters most here is not that suppression works -- it
is that it cannot be used quietly. A suppressed finding stops costing the
grade, which makes this the one feature in the tool that can improve a
score without improving the code. Every test below that asserts on
*visibility* is guarding that, not being thorough for its own sake.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from mcp_migrate.cli import main, run_check_detailed
from mcp_migrate.suppress import apply, parse_file, unused

PY_TRIGGER = "mcp_session_id = request.headers.get('X-Sid')"
TS_TRIGGER = 'const mcpSessionId = req.headers["x-sid"];'


def project(tmp_path, name, body):
    tmp_path.mkdir(parents=True, exist_ok=True)
    (tmp_path / name).write_text(body, encoding="utf-8")
    return tmp_path


# --- parsing -------------------------------------------------------------

def test_parses_a_well_formed_directive():
    s, problems = parse_file(Path("a.py"), f"{PY_TRIGGER}  # mcp-migrate: ignore[R001] -- deliberate\n")
    assert not problems
    assert s[0].rule_ids == ("R001",)
    assert s[0].reason == "deliberate"
    assert s[0].line == 1


def test_parses_the_typescript_comment_syntax():
    s, problems = parse_file(Path("a.ts"), f"{TS_TRIGGER}  // mcp-migrate: ignore[R001] -- deliberate\n")
    assert not problems
    assert s[0].rule_ids == ("R001",)


def test_parses_several_rule_ids():
    s, _ = parse_file(Path("a.py"), "x = 1  # mcp-migrate: ignore[R001, R006] -- both\n")
    assert s[0].rule_ids == ("R001", "R006")


@pytest.mark.parametrize("sep", ["--", ":"])
def test_either_reason_separator_works(sep):
    s, _ = parse_file(Path("a.py"), f"x = 1  # mcp-migrate: ignore[R001] {sep} why\n")
    assert s[0].reason == "why"


def test_rule_ids_are_case_insensitive():
    s, _ = parse_file(Path("a.py"), "x = 1  # mcp-migrate: ignore[r001] -- why\n")
    assert s[0].rule_ids == ("R001",)


# --- what is deliberately refused ---------------------------------------

def test_a_blanket_ignore_is_refused_and_reported():
    # Not silently dropped: someone wrote this believing it worked, and
    # the finding it was meant to silence is about to appear anyway.
    s, problems = parse_file(Path("a.py"), "x = 1  # mcp-migrate: ignore\n")
    assert s == []
    assert problems
    assert "rule id" in problems[0].message


def test_a_bad_rule_id_is_reported():
    _s, problems = parse_file(Path("a.py"), "x = 1  # mcp-migrate: ignore[nonsense] -- why\n")
    assert problems
    assert "not a rule id" in problems[0].message


def test_a_missing_reason_is_reported_but_still_suppresses():
    # Reported, because an unexplained suppression is unreviewable later.
    # Still honoured, because failing closed here would mean a malformed
    # comment silently reintroduces a finding someone thought was handled.
    s, problems = parse_file(Path("a.py"), "x = 1  # mcp-migrate: ignore[R001]\n")
    assert s and s[0].rule_ids == ("R001",)
    assert problems and "no reason" in problems[0].message


def test_an_unrelated_comment_is_not_a_directive():
    s, problems = parse_file(Path("a.py"), "x = 1  # we should ignore R001 here one day\n")
    assert not s and not problems


# --- application ---------------------------------------------------------

def test_a_suppressed_finding_is_removed_and_the_rest_survive(tmp_path):
    body = (
        "import httpx\n"
        f"{PY_TRIGGER}  # mcp-migrate: ignore[R001] -- deliberate\n"
        f"other_{PY_TRIGGER}\n"
    )
    result = run_check_detailed(project(tmp_path, "server.py", body))

    assert len(result.suppressed) == 1
    assert result.suppressed[0].line == 2
    assert all(f.line != 2 for f in result.findings)
    assert any(f.rule_id == "R001" for f in result.findings), "line 3 still fires"


def test_suppression_is_rule_scoped(tmp_path):
    # ignore[R006] must not silence an R001 finding on the same line.
    body = "import httpx\n" + f"{PY_TRIGGER}  # mcp-migrate: ignore[R006] -- wrong rule\n"
    result = run_check_detailed(project(tmp_path, "server.py", body))
    assert result.suppressed == []
    assert any(f.rule_id == "R001" for f in result.findings)


def test_suppression_is_line_scoped(tmp_path):
    body = (
        "import httpx\n"
        "# mcp-migrate: ignore[R001] -- on its own line, applies to nothing\n"
        f"{PY_TRIGGER}\n"
    )
    result = run_check_detailed(project(tmp_path, "server.py", body))
    assert result.suppressed == []


def test_a_project_level_finding_cannot_be_suppressed():
    # No line to attach a comment to. Allowing one from an arbitrary line
    # elsewhere would be a blanket ignore in disguise.
    class F:
        rule_id, path, line = "R010", None, None

    kept, suppressed = apply([F()], [])
    assert kept and not suppressed


def test_unused_suppressions_are_detected():
    s, _ = parse_file(Path("a.py"), "x = 1  # mcp-migrate: ignore[R001] -- stale\n")
    assert unused(s) == s
    apply([], s)
    assert unused(s) == s, "nothing matched, so it stays unused"


# --- the grade, and keeping it honest ------------------------------------

def test_a_suppressed_finding_does_not_cost_the_grade(tmp_path):
    trigger = f"{PY_TRIGGER}\n"
    dirty = run_check_detailed(project(tmp_path / "a", "server.py", "import httpx\n" + trigger))
    clean = run_check_detailed(project(
        tmp_path / "b", "server.py",
        "import httpx\n" + f"{PY_TRIGGER}  # mcp-migrate: ignore[R001] -- deliberate\n",
    ))
    assert clean.value > dirty.value, (
        "a suppression that still costs the grade is not a suppression -- "
        "the user's only remaining move would be to stop running the tool"
    )


def test_the_suppression_count_is_printed_without_a_flag(tmp_path, capsys):
    # Not behind --show-suppressions. The count is part of reading the
    # grade honestly, and hiding it would make this a quiet way to improve
    # a score.
    body = "import httpx\n" + f"{PY_TRIGGER}  # mcp-migrate: ignore[R001] -- deliberate\n"
    main(["check", str(project(tmp_path, "server.py", body))])
    out = capsys.readouterr().out
    assert "suppressed" in out


def test_show_suppressions_lists_each_one_with_its_reason(tmp_path, capsys):
    body = "import httpx\n" + f"{PY_TRIGGER}  # mcp-migrate: ignore[R001] -- proxy shim\n"
    main(["check", str(project(tmp_path, "server.py", body)), "--show-suppressions"])
    out = capsys.readouterr().out
    assert "proxy shim" in out
    assert "R001" in out


def test_malformed_directives_are_surfaced_on_the_console(tmp_path, capsys):
    body = "import httpx\nx = 1  # mcp-migrate: ignore\n"
    main(["check", str(project(tmp_path, "server.py", body))])
    assert "suppression ignored" in capsys.readouterr().out


def test_unused_suppressions_are_surfaced_on_the_console(tmp_path, capsys):
    body = "import httpx\nx = 1  # mcp-migrate: ignore[R001] -- stale\n"
    main(["check", str(project(tmp_path, "server.py", body))])
    assert "unused suppression" in capsys.readouterr().out


# --- machine-readable ----------------------------------------------------

def test_json_carries_the_suppressions_and_their_reasons(tmp_path, capsys):
    body = "import httpx\n" + f"{PY_TRIGGER}  # mcp-migrate: ignore[R001] -- proxy shim\n"
    main(["check", str(project(tmp_path, "server.py", body)), "--json"])
    payload = json.loads(capsys.readouterr().out)

    assert len(payload["suppressed"]) == 1
    assert payload["suppressed"][0]["rule"] == "R001"
    assert payload["suppressed"][0]["reason"] == "proxy shim"
    assert payload["suppressed"][0]["line"] == 2


def test_suppressed_is_always_present_even_when_empty(tmp_path, capsys):
    main(["check", str(project(tmp_path, "server.py", "import httpx\n")), "--json"])
    assert json.loads(capsys.readouterr().out)["suppressed"] == []


def test_suppressed_findings_are_not_in_findings_or_counts(tmp_path, capsys):
    body = "import httpx\n" + f"{PY_TRIGGER}  # mcp-migrate: ignore[R001] -- deliberate\n"
    main(["check", str(project(tmp_path, "server.py", body)), "--json"])
    payload = json.loads(capsys.readouterr().out)

    assert all(f["line"] != 2 for f in payload["findings"])
    assert sum(payload["counts"].values()) == len(payload["findings"])


def test_unused_suppressions_reach_json_not_just_the_console(tmp_path, capsys):
    # The audit story has to work for the consumer that cannot read the
    # console. Stale suppressions accumulate in CI, and CI reads --json.
    body = "import httpx\nx = 1  # mcp-migrate: ignore[R001] -- stale\n"
    main(["check", str(project(tmp_path, "server.py", body)), "--json"])
    payload = json.loads(capsys.readouterr().out)

    assert len(payload["unused_suppressions"]) == 1
    entry = payload["unused_suppressions"][0]
    assert entry["rule"] == "R001"
    assert entry["line"] == 2
    assert entry["reason"] == "stale"
    assert entry["path"].endswith("server.py")


def test_unused_suppressions_is_always_present_even_when_empty(tmp_path, capsys):
    # Required, like `suppressed`. An empty array is the common case, which
    # is exactly the one worth making visible -- a key that appears only
    # when non-empty forces every consumer to write the same `.get()`.
    main(["check", str(project(tmp_path, "server.py", "import httpx\n")), "--json"])
    assert json.loads(capsys.readouterr().out)["unused_suppressions"] == []


def test_a_suppression_that_matched_is_not_reported_as_unused(tmp_path, capsys):
    body = "import httpx\n" + f"{PY_TRIGGER}  # mcp-migrate: ignore[R001] -- deliberate\n"
    main(["check", str(project(tmp_path, "server.py", body)), "--json"])
    payload = json.loads(capsys.readouterr().out)

    assert payload["suppressed"], "it did match"
    assert payload["unused_suppressions"] == []


def test_a_stale_directive_naming_two_rules_reports_both(tmp_path, capsys):
    # One entry per rule id, so the shape matches `suppressed`. Nothing is
    # lost by expanding: if the directive matched nothing, every rule in it
    # is stale.
    body = "import httpx\nx = 1  # mcp-migrate: ignore[R001, R006] -- stale\n"
    main(["check", str(project(tmp_path, "server.py", body)), "--json"])
    payload = json.loads(capsys.readouterr().out)

    assert sorted(e["rule"] for e in payload["unused_suppressions"]) == ["R001", "R006"]
    assert {e["line"] for e in payload["unused_suppressions"]} == {2}


def test_a_suppressed_breaking_finding_changes_the_exit_code(tmp_path, capsys):
    # The consequence of the grade decision, stated as a test: this is
    # what makes the feature usable in CI, and also what makes the
    # visibility guarantees above load-bearing.
    body = "import httpx\n" + PY_TRIGGER + "\n"
    assert main(["check", str(project(tmp_path / "a", "server.py", body))]) == 1
    capsys.readouterr()

    suppressed = "import httpx\n" + f"{PY_TRIGGER}  # mcp-migrate: ignore[R001] -- deliberate\n"
    assert main(["check", str(project(tmp_path / "b", "server.py", suppressed))]) == 0
    capsys.readouterr()
