"""What languages is this tree written in, and can we read any of them?

`mcp-migrate` reads Python and TypeScript. It does not read the other
nine languages it can name, and it must never pretend otherwise. Before
this module existed, `check` derived a grade from an empty finding set
without ever asking whether it had read anything at all -- so a
TypeScript server (and most MCP servers are TypeScript) scored a
confident A/100, and `entry` would happily emit a registry entry claiming
`language: python` for a repo containing no Python whatsoever.

The standing rule this enforces: never report a grade for something you
could not read. Silence is an acceptable output; a confident A about a
file you never opened is not.
"""
from __future__ import annotations

import os
from collections import Counter
from pathlib import Path

from .scan import SKIP_DIRS

# Languages with enough rule coverage to carry a grade. Everything else we
# can only count and name -- which is enough to explain why we're refusing.
SUPPORTED = frozenset({"python"})

# Languages some rules can read, but not yet enough of them to put a letter
# on. TypeScript findings are real and worth printing; a *grade* derived
# from them would be a claim about the rules that didn't run, which is the
# same false-A this tool refuses to hand out for an empty directory.
# (Deliberately not a count -- the last one sat here saying "19" long after
# it was 1.)
# Move a language from here to SUPPORTED when coverage is broad enough to
# mean something.
PARTIAL = frozenset({"typescript"})

EXTENSIONS = {
    ".py": "python", ".pyi": "python",
    ".ts": "typescript", ".tsx": "typescript", ".mts": "typescript", ".cts": "typescript",
    ".js": "javascript", ".jsx": "javascript", ".mjs": "javascript", ".cjs": "javascript",
    ".go": "go",
    ".rs": "rust",
    ".java": "java",
    ".kt": "kotlin",
    ".cs": "csharp",
    ".rb": "ruby",
    ".php": "php",
    ".swift": "swift",
}

DISPLAY = {
    "python": "Python", "typescript": "TypeScript", "javascript": "JavaScript",
    "go": "Go", "rust": "Rust", "java": "Java", "kotlin": "Kotlin",
    "csharp": "C#", "ruby": "Ruby", "php": "PHP", "swift": "Swift",
}


def survey(root: Path) -> Counter:
    """Count source files per language under `root`.

    Walks with `os.walk` rather than `rglob` so vendored directories can be
    pruned before descending: `node_modules` alone can hold six figures of
    `.js` files, which would both dominate the count and cost real time to
    walk. Uses the same skip list as the scanner, so what this reports and
    what the scanner reads stay in agreement.
    """
    counts: Counter = Counter()
    for _dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
        for name in filenames:
            lang = EXTENSIONS.get(Path(name).suffix.lower())
            if lang is not None:
                counts[lang] += 1
    return counts


def primary(counts: Counter) -> str | None:
    """The language this tree is mostly written in, or None if it holds no
    source we recognise.

    Ties break toward a language we support: a repo with equal amounts of
    Python and TypeScript is one we can say something true about, so we'd
    rather call it Python than decline.
    """
    if not counts:
        return None
    return max(counts.items(), key=lambda kv: (kv[1], kv[0] in SUPPORTED, kv[0]))[0]


def describe(counts: Counter, limit: int = 3) -> str:
    """"24 TypeScript, 3 Python" -- for telling someone what we did find."""
    if not counts:
        return "no recognised source files"
    return ", ".join(
        f"{n} {DISPLAY.get(lang, lang)}" for lang, n in counts.most_common(limit)
    )
