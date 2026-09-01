"""Make the package and the standalone scripts importable without a real
editable install (the project's README.md doesn't exist yet, which makes
`pip install -e .` fail on the hatchling readme check)."""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "src"
SCRIPTS = ROOT / "scripts"

for path in (SRC, SCRIPTS):
    p = str(path)
    if p not in sys.path:
        sys.path.insert(0, p)


@pytest.fixture(autouse=True)
def _no_ansi_in_captured_output(monkeypatch):
    """Stop rich from colouring output during tests.

    Several tests assert on what `check` prints. rich decides whether to
    emit ANSI escapes from the environment, and `FORCE_COLOR` -- which a
    lot of people set globally, and which some terminals and CI images set
    for you -- makes it colour even when stdout is a pytest capture buffer.
    The escapes land *inside* the captured string and in the middle of the
    very numbers being asserted on, so `"3 of 21"` stops matching because
    it is really `"\\x1b[1;36m3\\x1b[0m of \\x1b[1;36m21\\x1b[0m"`.

    That failure is invisible in CI (no FORCE_COLOR there) and reproducible
    on a contributor's laptop, which is the worst possible combination: a
    green suite here, a red one on the machine of someone making their
    first PR. Normalising the environment is the fix; asserting on
    ANSI-stripped text would only paper over the next one.
    """
    monkeypatch.delenv("FORCE_COLOR", raising=False)
    monkeypatch.delenv("COLORTERM", raising=False)
    monkeypatch.setenv("NO_COLOR", "1")
    monkeypatch.setenv("TERM", "dumb")


@pytest.fixture(autouse=True)
def _git_root_isolation(monkeypatch):
    """Keep `git rev-parse` from discovering a repository above temp dirs.

    `_git_sha` (and `test_entry_sha.py`) decide whether a scanned tree is a
    real git checkout by asking `git -C <root> rev-parse HEAD`. Git walks up
    from its `-C` argument looking for a `.git`, so if a test's `tmp_path`
    happens to sit inside a parent git workspace (a contributor running the
    suite from inside their repo, or a temp directory mounted under one),
    git would report the *ancestor* checkout's HEAD for a directory that is
    not itself a repository, and
    `test_git_sha_of_a_non_git_directory_is_none` would fail.

    GIT_CEILING_DIRECTORIES tells git the highest directory it may search
    from. Pointing it at the system temp root means every pytest `tmp_path`
    -- always a child of that root -- is barred from reaching any real repo
    above it, so a non-repo scan directory reliably stays `None`.
    """
    monkeypatch.setenv("GIT_CEILING_DIRECTORIES", tempfile.gettempdir())
