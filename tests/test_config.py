"""Project-level config: `[tool.mcp-migrate]` in pyproject.toml, or a
standalone `.mcp-migrate.toml` for projects with none.

The property worth guarding, same as suppress.py: a rule switched off from
config must be *visible*, not just effective. A grade that can be improved
by editing a file nobody reads is not a grade, so every test that asserts
on the disabled-rule report is guarding that, not just checking plumbing.
"""
from __future__ import annotations

import json

from mcp_migrate.cli import main, run_check_detailed
from mcp_migrate.config import load_config

# Trips R001 (removed session-id header), same trigger test_suppress.py uses.
PY_TRIGGER = "mcp_session_id = request.headers.get('X-Sid')\n"


def _write(root, name, body):
    root.mkdir(parents=True, exist_ok=True)
    (root / name).write_text(body, encoding="utf-8")


# --- loading ---------------------------------------------------------------

def test_no_config_file_is_the_empty_config(tmp_path):
    cfg = load_config(tmp_path)
    assert cfg.skip == frozenset()
    assert cfg.include_tests is False
    assert cfg.disabled_rules == {}
    assert cfg.source is None
    assert cfg.warnings == []


def test_reads_tool_table_from_pyproject_toml(tmp_path):
    _write(tmp_path, "pyproject.toml", """
[tool.mcp-migrate]
skip = ["vendor", "generated/"]
include-tests = true

[tool.mcp-migrate.rules]
R008 = "off"
""")
    cfg = load_config(tmp_path)
    assert cfg.skip == frozenset({"vendor", "generated"})
    assert cfg.include_tests is True
    assert cfg.disabled_rules == {"R008": ""}
    assert cfg.source == tmp_path / "pyproject.toml"


def test_pyproject_toml_with_no_tool_table_is_the_empty_config(tmp_path):
    """A pyproject.toml that exists but doesn't configure anything is a
    complete answer ("nothing"), not a reason to also read the standalone
    file -- the two must never silently fight over precedence."""
    _write(tmp_path, "pyproject.toml", '[project]\nname = "whatever"\n')
    _write(tmp_path, ".mcp-migrate.toml", 'skip = ["vendor"]\n')
    cfg = load_config(tmp_path)
    assert cfg.skip == frozenset()
    assert cfg.source is None


def test_falls_back_to_standalone_file_when_no_pyproject_toml(tmp_path):
    _write(tmp_path, ".mcp-migrate.toml", """
skip = ["proto"]

[rules]
R001 = "off -- deliberate, tracked in #123"
""")
    cfg = load_config(tmp_path)
    assert cfg.skip == frozenset({"proto"})
    assert cfg.disabled_rules == {"R001": "deliberate, tracked in #123"}
    assert cfg.source == tmp_path / ".mcp-migrate.toml"


def test_off_reason_accepts_either_separator(tmp_path):
    for sep in ("--", ":"):
        _write(tmp_path, ".mcp-migrate.toml", f'[rules]\nR001 = "off {sep} why"\n')
        cfg = load_config(tmp_path)
        assert cfg.disabled_rules == {"R001": "why"}


def test_rule_value_true_false_also_work(tmp_path):
    _write(tmp_path, ".mcp-migrate.toml", "[rules]\nR001 = false\nR002 = true\n")
    cfg = load_config(tmp_path)
    assert cfg.disabled_rules == {"R001": ""}


def test_malformed_toml_falls_back_to_defaults_with_a_warning(tmp_path):
    _write(tmp_path, ".mcp-migrate.toml", "this is not [ valid toml\n")
    cfg = load_config(tmp_path)
    assert cfg.skip == frozenset()
    assert cfg.disabled_rules == {}
    assert len(cfg.warnings) == 1
    assert "invalid TOML" in cfg.warnings[0]


# --- config discovery walks up from the scan root -------------------------

def test_walks_up_to_repo_root_pyproject(tmp_path):
    """`check src/` must find the repo's config at the repo root."""
    _write(tmp_path, "pyproject.toml", """
[tool.mcp-migrate.rules]
R001 = "off"
""")
    cfg = load_config(tmp_path / "src")
    assert cfg.disabled_rules == {"R001": ""}
    assert cfg.source == tmp_path / "pyproject.toml"


def test_walks_up_past_a_sectionless_inner_pyproject(tmp_path):
    """A monorepo inner pyproject.toml that says nothing about this tool must
    not stop the walk -- `check src/` still finds the repo root's config."""
    _write(tmp_path, "pyproject.toml", """
[tool.mcp-migrate.rules]
R001 = "off"
""")
    _write(tmp_path / "src", "pyproject.toml", '[project]\nname = "inner-pkg"\n')
    cfg = load_config(tmp_path / "src")
    assert cfg.disabled_rules == {"R001": ""}
    assert cfg.source == tmp_path / "pyproject.toml"


def test_walks_up_to_standalone_file_in_parent(tmp_path):
    _write(tmp_path, ".mcp-migrate.toml", 'skip = ["vendor"]\n')
    cfg = load_config(tmp_path / "src")
    assert cfg.skip == frozenset({"vendor"})
    assert cfg.source == tmp_path / ".mcp-migrate.toml"


def test_walk_stops_at_git_ceiling(tmp_path):
    """A stray config above the repo root must never change the grade."""
    _write(tmp_path, ".mcp-migrate.toml", 'skip = ["stray"]\n')
    repo = tmp_path / "repo"
    _write(repo, ".git", "")
    cfg = load_config(repo / "src")
    assert cfg.skip == frozenset()
    assert cfg.source is None


def test_walk_stops_at_filesystem_root_backstop(tmp_path):
    """Even without a .git ceiling, the walk must terminate."""
    _write(tmp_path, "pyproject.toml", '[tool.mcp-migrate]\nskip = ["top"]\n')
    # No .git anywhere; walk from a deep dir up to the filesystem root and
    # the config at tmp_path is between them, so it must still be found.
    cfg = load_config(tmp_path / "a" / "b" / "c")
    assert cfg.skip == frozenset({"top"})


def test_check_text_reports_walked_up_config_source(tmp_path, capsys):
    """The check output must say where the config came from when it was
    found above the scan root, per the issue."""
    _write(tmp_path, "pyproject.toml", """
[tool.mcp-migrate.rules]
R001 = "off"
""")
    _write(tmp_path / "src", "server.py", "x = 1\n")
    rc = main(["check", str(tmp_path / "src")])
    assert rc == 0
    out = capsys.readouterr().out
    # Rich wraps/truncates long paths across lines, so assert the line exists
    # and that it names the walked-up config file rather than the exact path.
    assert "config:" in out
    assert "pyproject.toml" in out


def test_unrecognised_rule_value_is_reported_not_silently_dropped(tmp_path):
    _write(tmp_path, ".mcp-migrate.toml", '[rules]\nR001 = "sometimes"\n')
    cfg = load_config(tmp_path)
    assert cfg.disabled_rules == {}
    assert any("R001" in w for w in cfg.warnings)


def test_non_rule_id_key_in_rules_table_is_reported(tmp_path):
    _write(tmp_path, ".mcp-migrate.toml", '[rules]\nnot-a-rule = "off"\n')
    cfg = load_config(tmp_path)
    assert cfg.disabled_rules == {}
    assert any("not-a-rule" in w for w in cfg.warnings)


# --- check integration -------------------------------------------------

def test_a_disabled_rule_produces_no_finding_and_is_reported(tmp_path):
    _write(tmp_path, "server.py", PY_TRIGGER)
    _write(tmp_path, "pyproject.toml", """
[project]
name = "x"

[tool.mcp-migrate.rules]
R001 = "off -- deliberate"
""")
    result = run_check_detailed(tmp_path)
    assert not any(f.rule_id == "R001" for f in result.findings)
    assert result.disabled_rules == {"R001": "deliberate"}


def test_unknown_rule_id_warns_and_is_not_disabled(tmp_path):
    _write(tmp_path, "server.py", PY_TRIGGER)
    _write(tmp_path, "pyproject.toml", """
[tool.mcp-migrate.rules]
R999 = "off -- typo"
""")

    result = run_check_detailed(tmp_path)

    assert result.disabled_rules == {}
    assert result.config.disabled_rules == {"R999": "typo"}
    assert result.config.warnings == [
        f"{tmp_path / 'pyproject.toml'}: no rule R999 -- "
        "see `mcp-migrate rules` for the 21 that exist"
    ]


def test_registered_rule_id_does_not_warn(tmp_path):
    _write(tmp_path, "server.py", PY_TRIGGER)
    _write(tmp_path, "pyproject.toml", """
[tool.mcp-migrate.rules]
R001 = "off"
""")

    result = run_check_detailed(tmp_path)

    assert result.disabled_rules == {"R001": ""}
    assert result.config.warnings == []


def test_a_disabled_rule_does_not_cost_the_grade(tmp_path):
    """The whole point: disabling a rule must not merely hide its findings
    from the report while still charging the score for them."""
    _write(tmp_path, "server.py", PY_TRIGGER)
    without_config = run_check_detailed(tmp_path)
    assert without_config.value < 100

    _write(tmp_path, "pyproject.toml", """
[tool.mcp-migrate.rules]
R001 = "off"
""")
    with_config = run_check_detailed(tmp_path)
    assert with_config.value == 100
    assert with_config.grade == "A"


def test_include_tests_off_by_default(tmp_path):
    _write(tmp_path / "tests", "test_server.py", PY_TRIGGER)
    result = run_check_detailed(tmp_path)
    assert not any(f.rule_id == "R001" for f in result.findings)


def test_include_tests_flag_alone_turns_it_on(tmp_path):
    _write(tmp_path / "tests", "test_server.py", PY_TRIGGER)
    result = run_check_detailed(tmp_path, include_tests=True)
    assert any(f.rule_id == "R001" for f in result.findings)


def test_include_tests_config_alone_turns_it_on(tmp_path):
    _write(tmp_path / "tests", "test_server.py", PY_TRIGGER)
    _write(tmp_path, "pyproject.toml", "[tool.mcp-migrate]\ninclude-tests = true\n")
    result = run_check_detailed(tmp_path)
    assert any(f.rule_id == "R001" for f in result.findings)


def test_extra_skip_dirs_are_not_scanned(tmp_path):
    _write(tmp_path / "vendor", "server.py", PY_TRIGGER)
    _write(tmp_path, "pyproject.toml", '[tool.mcp-migrate]\nskip = ["vendor/"]\n')

    result = run_check_detailed(tmp_path)
    assert not any(f.rule_id == "R001" for f in result.findings)
    assert result.project.files == []


# --- CLI surface ---------------------------------------------------------

def test_check_json_reports_disabled_rules_and_config_warnings(tmp_path, capsys):
    _write(tmp_path, "server.py", PY_TRIGGER)
    _write(tmp_path, "pyproject.toml", """
[tool.mcp-migrate.rules]
R001 = "off -- deliberate"
""")
    rc = main(["check", "--json", str(tmp_path)])
    assert rc == 0
    out = json.loads(capsys.readouterr().out)
    assert out["disabled_rules"] == [{"rule": "R001", "reason": "deliberate"}]
    assert out["config_warnings"] == []
    assert out["grade"] == "A"


def test_check_text_mentions_disabled_rule_count(tmp_path, capsys):
    _write(tmp_path, "server.py", PY_TRIGGER)
    _write(tmp_path, "pyproject.toml", """
[tool.mcp-migrate.rules]
R001 = "off -- deliberate"
""")
    rc = main(["check", str(tmp_path)])
    assert rc == 0
    out = capsys.readouterr().out
    assert "1 rule(s) disabled by config" in out
    assert "R001" in out
    assert "deliberate" in out


def test_check_json_surfaces_a_config_warning(tmp_path, capsys):
    _write(tmp_path, "server.py", "x = 1\n")
    _write(tmp_path, ".mcp-migrate.toml", '[rules]\nR001 = "maybe"\n')
    rc = main(["check", "--json", str(tmp_path)])
    assert rc == 0
    out = json.loads(capsys.readouterr().out)
    assert len(out["config_warnings"]) == 1
    assert "R001" in out["config_warnings"][0]


def test_fix_skips_a_rule_disabled_by_config(tmp_path, capsys):
    """A rule turned off for `check` shouldn't get auto-fixed either."""
    from mcp_migrate.fixers import all_fixers

    fixer_rule_ids = {fx.rule_id for fx in all_fixers()}
    assert fixer_rule_ids, "no fixers registered -- update this test's rule id"
    target_rule = sorted(fixer_rule_ids)[0]

    _write(tmp_path, "pyproject.toml", f"""
[tool.mcp-migrate.rules]
{target_rule} = "off"
""")
    rc = main(["fix", "--rule", target_rule, str(tmp_path)])
    assert rc == 0
    out = capsys.readouterr().out
    assert "disabled by project config" in out
