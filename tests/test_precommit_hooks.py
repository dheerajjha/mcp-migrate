"""`.pre-commit-hooks.yaml` and `--allow-unscannable`.

The hook always scans the whole project (`pass_filenames: false`), so an
unrelated-language repo or a partial monorepo path would otherwise fail
every single commit on exit 2 rather than on an actual finding -- that's
the failure `--allow-unscannable` exists to prevent.
"""
from __future__ import annotations

from pathlib import Path

import yaml

from mcp_migrate.cli import main

REPO_ROOT = Path(__file__).resolve().parent.parent


def test_hook_file_is_valid_yaml_with_one_hook():
    hooks = yaml.safe_load((REPO_ROOT / ".pre-commit-hooks.yaml").read_text())
    assert len(hooks) == 1
    hook = hooks[0]
    assert hook["id"] == "mcp-migrate"
    assert hook["language"] == "python"


def test_hook_scans_the_whole_project_not_just_staged_files():
    hooks = yaml.safe_load((REPO_ROOT / ".pre-commit-hooks.yaml").read_text())
    assert hooks[0]["pass_filenames"] is False


def test_hook_entry_opts_into_allow_unscannable():
    hooks = yaml.safe_load((REPO_ROOT / ".pre-commit-hooks.yaml").read_text())
    assert "--allow-unscannable" in hooks[0]["entry"]


def test_allow_unscannable_turns_exit_2_into_0(tmp_path, capsys):
    empty = tmp_path / "empty"
    empty.mkdir()
    exit_code = main(["check", str(empty), "--allow-unscannable"])
    out = capsys.readouterr().out

    assert exit_code == 0
    assert "Nothing scannable" in out, "still says what happened, just doesn't fail on it"
    assert "Grade" not in out


def test_allow_unscannable_does_not_touch_a_breaking_exit(tmp_path):
    (tmp_path / "server.py").write_text(
        "from mcp.types import PingRequest\n\n"
        "def handle():\n"
        "    return PingRequest()\n"
    )
    exit_code = main(["check", str(tmp_path), "--allow-unscannable"])
    assert exit_code == 1, "a real breaking finding must still fail the hook"


def test_allow_unscannable_defaults_to_off(tmp_path):
    empty = tmp_path / "empty"
    empty.mkdir()
    assert main(["check", str(empty)]) == 2
