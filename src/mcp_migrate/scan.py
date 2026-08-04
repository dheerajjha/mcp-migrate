from __future__ import annotations

import ast
import fnmatch
from pathlib import Path

from .rules.base import Project, SourceFile

SKIP_DIRS = {".git", ".venv", "venv", "node_modules", "__pycache__", "dist",
             "build", ".tox", ".mypy_cache", ".pytest_cache", "site-packages"}

# Path segments that mark a file as test code, not the server itself. Real
# servers' test suites routinely contain string literals that *look* like
# the very protocol surface these rules search for -- e.g. an integration
# test posting a literal `{"method": "tools/list"}` payload, or a
# backward-compatibility test that deliberately exercises the deprecated
# legacy transport. Both are evidence the project is well tested, not
# evidence the server itself is broken, so they're skipped by default.
# `--include-tests` disables this.
#
# `__tests__` / `__mocks__` / `spec` / `e2e` are the JavaScript and
# TypeScript spellings of the same idea. Leaving them out meant every TS
# project's test suite was read as production code -- caught by pointing
# the freshly ported rules at modelcontextprotocol/servers, where both
# findings for `src/filesystem` were in `__tests__/`.
TEST_DIR_SEGMENTS = {
    "tests", "test", "testing", "fixtures", "examples", "docs",
    "__tests__", "__mocks__", "spec", "specs", "e2e",
}

# Filenames that mark a module as test code even when it doesn't live
# under one of TEST_DIR_SEGMENTS (e.g. a `test_foo.py` next to the module
# it tests, or a root-level `conftest.py`).
#
# The `*.test.*` / `*.spec.*` pair is close to universal in JS/TS and is
# the dominant convention for tests that sit *beside* the module they
# cover, where no directory segment can give them away.
# Name is historical (tests first). Also covers type-checked docs
# examples (*.examples.ts) used by e.g. modelcontextprotocol/typescript-sdk
# for JSDoc snippet sync — prose that compiles, not production servers.
TEST_FILE_PATTERNS = (
    "test_*.py", "*_test.py", "conftest.py",
    "*.test.ts", "*.test.tsx", "*.test.mts", "*.test.cts",
    "*.spec.ts", "*.spec.tsx", "*.spec.mts", "*.spec.cts",
    "*.examples.ts", "*.examples.tsx", "*.examples.mts", "*.examples.cts",
)


def _is_test_path(rel_path: Path) -> bool:
    if any(part in TEST_DIR_SEGMENTS for part in rel_path.parts[:-1]):
        return True
    return any(fnmatch.fnmatch(rel_path.name, pat) for pat in TEST_FILE_PATTERNS)


# Extension -> language, for everything the rules can read. `.d.ts` is
# excluded below: it is generated type declarations, never an
# implementation, and grading someone on their build output is noise.
SOURCE_EXTENSIONS = {
    ".py": "python",
    ".ts": "typescript", ".mts": "typescript", ".cts": "typescript",
    ".tsx": "typescript",
}


def _language_of(path: Path) -> str | None:
    if path.name.endswith(".d.ts"):
        return None
    return SOURCE_EXTENSIONS.get(path.suffix.lower())


def load_project(root: Path, *, include_tests: bool = False) -> Project:
    files: list[SourceFile] = []
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        language = _language_of(path)
        if language is None:
            continue
        rel = path.relative_to(root)
        # Skipped relative to `root`, not the absolute filesystem path --
        # the project itself might legitimately live under a directory
        # named e.g. "test" or "build" somewhere above `root` (this is
        # exactly the situation for mcp-migrate's own fixtures, which live
        # under tests/fixtures/<name> and are scanned with that directory
        # as root), and that shouldn't cause every file in it to vanish.
        if any(part in SKIP_DIRS for part in rel.parts[:-1]):
            continue
        if not include_tests and _is_test_path(rel):
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        tree = None
        if language == "python":
            try:
                tree = ast.parse(text, filename=str(path))
            except SyntaxError:
                tree = None
        files.append(SourceFile(path=rel, text=text, tree=tree, language=language))
    return Project(root=root, files=files)
