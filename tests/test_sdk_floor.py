"""`declared_mcp_floor`, and the R010 gate built on it.

R010 used to fire on 16 of 16 board servers and tell each of them to add a
handler the SDK registers itself. The premise was wrong rather than the
detection: on `mcp` 2.x, `Server.__init__` registers `server/discover`, so
an absence check against the project's *own source* reports a gap that is
not there; on 1.x the method does not exist at all, so there is nothing to
add and the remediation is "upgrade". See #257.

The rule now asks which SDK the project declares. What it must never do is
guess: an unreadable declaration has to mean silence, because a finding
nobody can act on costs more than a missing one.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from mcp_migrate.rules.r010_server_discover_missing import ServerDiscoverMissing
from mcp_migrate.scan import load_project
from mcp_migrate.sdk import _floor_from_requirement, declared_mcp_floor

HANDLERS = (
    "from mcp.server import Server\n"
    "from mcp.types import Tool\n\n"
    "app = Server('demo')\n\n"
    "@app.list_tools()\n"
    "async def list_tools() -> list[Tool]:\n"
    "    return []\n"
)


# --- reading a floor out of one requirement string -----------------------

@pytest.mark.parametrize(
    "spec,expected",
    [
        ("mcp>=2.0.0", (2, 0, 0)),
        ("mcp==2.7.0", (2, 7, 0)),
        ("mcp>=1.2,<2", (1, 2)),
        ("mcp~=2.1", (2, 1)),
        ("mcp[cli]>=2.0", (2, 0)),
        ("mcp >= 3.2", (3, 2)),
        ("mcp^2.0", (2, 0)),
        ("  mcp>=1.9  ", (1, 9)),
    ],
)
def test_floor_is_read_from_a_lower_bound(spec, expected):
    assert _floor_from_requirement(spec) == expected


@pytest.mark.parametrize(
    "spec",
    [
        "mcp",            # no constraint at all
        "mcp<3",          # an upper bound says nothing about the floor
        "mcp!=1.4",       # nor does an exclusion
        "fastmcp>=2.0",   # a different package on its own version line
        "mcpx>=2.0",      # not `mcp`; a prefix match here would be a lie
        "",
        "# mcp>=2.0",     # a commented-out requirement is not a requirement
    ],
)
def test_unreadable_specs_answer_none_rather_than_guess(spec):
    assert _floor_from_requirement(spec) is None


# --- reading a floor out of a project ------------------------------------

def write(root: Path, name: str, text: str) -> None:
    (root / name).write_text(text)


def test_floor_from_pep621_dependencies(tmp_path):
    write(tmp_path, "pyproject.toml",
          '[project]\nname = "x"\nversion = "0"\ndependencies = ["mcp>=1.9.0", "rich"]\n')
    assert declared_mcp_floor(tmp_path) == (1, 9, 0)


def test_floor_from_optional_dependencies(tmp_path):
    write(tmp_path, "pyproject.toml",
          '[project]\nname = "x"\nversion = "0"\ndependencies = []\n'
          '[project.optional-dependencies]\nserver = ["mcp>=2.3"]\n')
    assert declared_mcp_floor(tmp_path) == (2, 3)


def test_floor_from_poetry(tmp_path):
    write(tmp_path, "pyproject.toml",
          '[tool.poetry]\nname = "x"\n[tool.poetry.dependencies]\nmcp = "^2.1"\n')
    assert declared_mcp_floor(tmp_path) == (2, 1)


def test_floor_from_requirements_txt(tmp_path):
    write(tmp_path, "requirements.txt", "rich==13.0\nmcp>=1.4.0\n")
    assert declared_mcp_floor(tmp_path) == (1, 4, 0)


def test_the_highest_declared_floor_wins(tmp_path):
    """Two declarations cannot both bind; the project cannot resolve below
    the higher one."""
    write(tmp_path, "pyproject.toml",
          '[project]\nname = "x"\nversion = "0"\ndependencies = ["mcp>=1.2"]\n')
    write(tmp_path, "requirements.txt", "mcp>=2.1\n")
    assert declared_mcp_floor(tmp_path) == (2, 1)


def test_no_declaration_is_none_not_zero(tmp_path):
    write(tmp_path, "pyproject.toml", '[project]\nname = "x"\nversion = "0"\n')
    assert declared_mcp_floor(tmp_path) is None


def test_a_fastmcp_project_is_undeterminable(tmp_path):
    """fastmcp has its own version line and pulls `mcp` in transitively, so
    `fastmcp==2.7.0` says nothing readable about which `mcp` resolves."""
    write(tmp_path, "pyproject.toml",
          '[project]\nname = "x"\nversion = "0"\ndependencies = ["fastmcp==2.7.0"]\n')
    assert declared_mcp_floor(tmp_path) is None


def test_a_missing_directory_is_none(tmp_path):
    assert declared_mcp_floor(tmp_path / "nope") is None


# --- the R010 gate -------------------------------------------------------

def check_r010(root: Path):
    return ServerDiscoverMissing().check(load_project(root))


def test_r010_is_silent_on_a_declared_2x_project(tmp_path):
    """The whole of #257: on 2.x the SDK registers the handler, so this
    finding would be false."""
    write(tmp_path, "server.py", HANDLERS)
    write(tmp_path, "pyproject.toml",
          '[project]\nname = "x"\nversion = "0"\ndependencies = ["mcp>=2.0.0"]\n')

    assert check_r010(tmp_path) == []


def test_r010_fires_on_a_declared_1x_project(tmp_path):
    """1.x is the mirror image: the method does not exist, so the gap is
    real -- the remediation is just 'upgrade' rather than 'add a handler'."""
    write(tmp_path, "server.py", HANDLERS)
    write(tmp_path, "pyproject.toml",
          '[project]\nname = "x"\nversion = "0"\ndependencies = ["mcp>=1.9.0"]\n')

    assert [f.rule_id for f in check_r010(tmp_path)] == ["R010"]


def test_r010_is_silent_when_the_sdk_cannot_be_determined(tmp_path):
    """Silence over a guess. A declaration is not a resolved version, and a
    finding nobody can act on costs more than a missing one."""
    write(tmp_path, "server.py", HANDLERS)

    assert check_r010(tmp_path) == []


def test_the_fix_text_no_longer_tells_anyone_to_add_a_handler():
    """The advice was unactionable in both directions -- impossible on 1.x,
    unnecessary on 2.x -- and two contributors wrote `@app.discover()`
    fixers against it (#253, #254)."""
    fix = ServerDiscoverMissing.fix

    assert "mcp>=2.0" in fix
    assert "Add a handler for it alongside your other request handlers" not in fix
