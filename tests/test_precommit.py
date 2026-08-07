"""The pre-commit wrapper.

One decision, one test file: pre-commit treats any non-zero exit as a
failed hook, and `check` exits 2 for "no readable source in a supported
language". Left alone, the hook would block every commit in a repository
the tool cannot read -- which is every repository, right up until someone
adds their first Python or TypeScript file.

A hook that blocks commits for a reason the user cannot act on gets
uninstalled within the hour, and then it catches nothing ever again.
"""
from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from mcp_migrate.precommit import main as precommit_main

ROOT = Path(__file__).resolve().parent.parent
HOOKS = yaml.safe_load((ROOT / ".pre-commit-hooks.yaml").read_text(encoding="utf-8"))

BREAKING = "import httpx\nmcp_session_id = 1\n"
CLEAN = "import httpx\n\n\ndef handle(r):\n    return r\n"


def project(tmp_path, name, body):
    tmp_path.mkdir(parents=True, exist_ok=True)
    (tmp_path / name).write_text(body, encoding="utf-8")
    return tmp_path


# --- the one decision ----------------------------------------------------

def test_an_unreadable_tree_does_not_block_the_commit(tmp_path, capsys):
    (tmp_path / "notes.txt").write_text("no source here\n")
    code = precommit_main([str(tmp_path)])
    capsys.readouterr()
    assert code == 0, "exit 2 must not fail the hook"


def test_check_still_exits_two_on_the_same_tree(tmp_path, capsys):
    # The wrapper changes the hook, not the CLI. `check` keeps saying
    # "could not check it", which is the honest answer for a tool.
    from mcp_migrate.cli import main as cli_main

    (tmp_path / "notes.txt").write_text("no source here\n")
    code = cli_main(["check", str(tmp_path)])
    capsys.readouterr()
    assert code == 2


def test_a_breaking_finding_still_blocks_the_commit(tmp_path, capsys):
    # The entire point of installing the hook.
    code = precommit_main([str(project(tmp_path, "server.py", BREAKING))])
    capsys.readouterr()
    assert code == 1


def test_a_clean_project_passes(tmp_path, capsys):
    code = precommit_main([str(project(tmp_path, "server.py", CLEAN))])
    capsys.readouterr()
    assert code == 0


def test_the_unreadable_message_is_still_printed(tmp_path, capsys):
    # Not fatal is not the same as not shown -- "we could not read this"
    # is still something the user should see.
    (tmp_path / "notes.txt").write_text("no source here\n")
    precommit_main([str(tmp_path)])
    assert "scannable" in capsys.readouterr().out.lower()


# --- argument handling ---------------------------------------------------

def test_a_bare_path_is_treated_as_an_argument_not_a_subcommand(tmp_path, capsys):
    # Regression: testing only for a leading dash meant a path was parsed
    # as a subcommand name, argparse exited 2, and the wrapper turned that
    # into a *pass* -- silently disabling the hook.
    code = precommit_main([str(project(tmp_path, "server.py", BREAKING))])
    capsys.readouterr()
    assert code == 1, "a path argument must still reach `check`"


def test_an_explicit_check_is_accepted(tmp_path, capsys):
    code = precommit_main(["check", str(project(tmp_path, "server.py", CLEAN))])
    capsys.readouterr()
    assert code == 0


def test_flags_are_passed_through(tmp_path, capsys):
    code = precommit_main([str(project(tmp_path, "server.py", CLEAN)), "--json"])
    out = capsys.readouterr().out
    assert code == 0
    assert out.lstrip().startswith("{"), "--json should have reached check"


# --- the hook definition itself -----------------------------------------

def test_exactly_one_hook_is_declared():
    assert len(HOOKS) == 1
    assert HOOKS[0]["id"] == "mcp-migrate"


def test_the_hook_runs_the_wrapper_not_check_directly():
    # `entry: mcp-migrate check` would reintroduce the exit-2 problem.
    assert HOOKS[0]["entry"] == "mcp-migrate-precommit"


def test_the_hook_scans_the_project_not_the_staged_files():
    # Several rules are whole-project questions -- R010 asks whether
    # server/discover exists *anywhere*. Handed only staged files it would
    # answer that about a partial tree and fire wrongly.
    assert HOOKS[0]["pass_filenames"] is False


def test_the_hook_is_gated_on_languages_the_scanner_reads():
    types = set(HOOKS[0]["types_or"])
    assert {"python", "ts"} <= types


def test_the_entry_point_is_declared_in_pyproject():
    text = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    assert 'mcp-migrate-precommit = "mcp_migrate.precommit:main"' in text
