"""`mcp-migrate entry` records the commit it graded, when it can.

A board entry names a repo, not a state, unless it also carries the sha
of the tree that was actually checked -- see #223. Without it "repo:
acme/notes-mcp" is a claim about a moving target and nothing can check
a published grade against what it was a claim about. The tests below
guard both halves: the sha shows up when the scanned tree is a git
checkout, and it stays out (rather than lying with a stale or wrong
value) when it isn't.
"""
from __future__ import annotations

import re
import subprocess

from mcp_migrate.cli import main

PY_CLEAN = "import httpx\n\n\ndef handle(r):\n    return r\n"
SHA_RX = re.compile(r"^[0-9a-f]{40}$")


def project(tmp_path, name, body):
    tmp_path.mkdir(parents=True, exist_ok=True)
    (tmp_path / name).write_text(body, encoding="utf-8")
    return tmp_path


def git_project(tmp_path, name, body):
    root = project(tmp_path, name, body)
    run = lambda *args: subprocess.run(
        ["git", *args], cwd=root, capture_output=True, text=True, check=True
    )
    run("init", "-q")
    run("-c", "user.email=test@example.com", "-c", "user.name=Test", "add", ".")
    run("-c", "user.email=test@example.com", "-c", "user.name=Test", "commit", "-q", "-m", "initial")
    return root, run("rev-parse", "HEAD").stdout.strip()


def test_entry_omits_sha_outside_a_git_checkout(tmp_path, capsys):
    exit_code = main([
        "entry", str(project(tmp_path, "server.py", PY_CLEAN)),
        "--repo", "acme/notes-mcp",
    ])
    out = capsys.readouterr().out

    assert exit_code == 0
    assert "sha:" not in out


def test_entry_carries_the_commit_sha_of_a_git_checkout(tmp_path, capsys):
    root, sha = git_project(tmp_path, "server.py", PY_CLEAN)

    exit_code = main(["entry", str(root), "--repo", "acme/notes-mcp"])
    out = capsys.readouterr().out

    assert exit_code == 0
    assert f"sha: {sha}\n" in out
    line = next(l for l in out.splitlines() if l.startswith("sha:"))
    assert SHA_RX.match(line.removeprefix("sha: ")), "should be the full 40-char sha, not shortened"


def test_git_sha_of_a_non_git_directory_is_none(tmp_path):
    from mcp_migrate.cli import _git_sha

    assert _git_sha(project(tmp_path, "server.py", PY_CLEAN)) is None


def test_git_sha_of_a_git_checkout_matches_head(tmp_path):
    from mcp_migrate.cli import _git_sha

    root, sha = git_project(tmp_path, "server.py", PY_CLEAN)
    assert _git_sha(root) == sha
