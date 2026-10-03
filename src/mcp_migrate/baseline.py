"""Baseline file: accept today's findings, fail the build only on new ones.

This is the sibling of `suppress.py` (#203, issue #180), not an extension of
it. #203's own description drew the line this module depends on: inline
suppression is "this line is fine forever," a baseline is "not today." So
unlike a suppression, a baselined finding still counts against the grade --
`grade.score()` never reads anything in this module. What a baseline changes
is narrower and orthogonal: which findings are allowed to fail the build,
via `--fail-on`. See BASELINE_PLAN.md for the full design writeup.

Matching key is `(rule_id, path, normalized snippet)` -- deliberately not
`path:line`. A baseline keyed on the line number breaks the moment an
unrelated line is inserted above it, which defeats the entire point of
letting a project adopt this incrementally: the baseline would go stale on
the very next unrelated commit. `Finding.snippet` (the stripped source line
a rule matched) is already captured on every finding a rule reports, so no
new scanning is needed -- just whitespace-run collapsing on top of the
`.strip()` a rule's `search*()` call already did, to also absorb
reindentation without absorbing an actual content change.

The same (rule, path, snippet) can legitimately occur more than once in one
file (a pattern repeated in a loop, or copy-pasted). `apply()` matches these
as a multiset: if a repeated pattern's count drops from 3 to 2 between the
baseline and today, exactly one occurrence is reported `stale` and zero are
`new` -- one specific instance was fixed, not "everything about this rule is
unknown again."
"""
from __future__ import annotations

import json
import re
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

from .rules.base import Finding

# The conventional filename, referenced in --write-baseline's help text and
# the README -- not enforced anywhere; any path is accepted.
DEFAULT_FILENAME = ".mcp-migrate-baseline.json"

_WS_RX = re.compile(r"\s+")


def _normalize(snippet: str | None) -> str | None:
    """Collapse whitespace runs so reindentation doesn't break a match.

    `Finding.snippet` is already `.strip()`-ped by the time a rule sets it
    (every `Project.search*` yields `line.strip()`); this absorbs the other
    half of "survives reformatting" -- a line gaining or losing internal
    spacing -- without absorbing an actual content change, which a full
    normalize (e.g. stripping punctuation) would risk doing.
    """
    if snippet is None:
        return None
    return _WS_RX.sub(" ", snippet.strip())


def _path_str(path) -> str | None:
    """Repo-relative, forward-slash -- stable across platforms.

    `Finding.path` is a `Path` built from `path.relative_to(root)` in
    `scan.py`, which does not itself normalize separators. A baseline
    written on Windows must still match on Linux CI, so this is the one
    place that conversion happens, used for both writing and matching.
    """
    if path is None:
        return None
    return Path(path).as_posix()


@dataclass(frozen=True)
class BaselineEntry:
    """One recorded finding, as read from a baseline file."""

    rule_id: str
    path: str | None
    snippet: str | None
    line: int | None = None  # human-readable only -- never read back for matching

    def key(self) -> tuple[str, str | None, str | None]:
        return (self.rule_id, self.path, _normalize(self.snippet))

    def location(self) -> str:
        if self.path is None:
            return "(project)"
        return f"{self.path}:{self.line}" if self.line else self.path


def _finding_key(f: Finding) -> tuple[str, str | None, str | None]:
    return (f.rule_id, _path_str(f.path), _normalize(f.snippet))


@dataclass
class LoadResult:
    """What reading a baseline file produced.

    `warning` is set for a file that exists but couldn't be understood
    (malformed JSON, wrong shape, unreadable entries) -- reported the same
    way a malformed `pyproject.toml`/`.mcp-migrate.toml` is in config.py:
    fall back to an empty baseline rather than failing the run, but never
    silently. A genuinely missing file is not a warning at all -- see
    `load()`.
    """

    entries: list[BaselineEntry] = field(default_factory=list)
    warning: str | None = None


def load(path: Path) -> LoadResult:
    """Read a baseline file, or an empty one if it doesn't exist yet.

    A missing file is deliberately not an error: it lets a team add
    `--baseline PATH` to CI before PATH exists in the branch being checked
    (or before `--write-baseline` has ever been run at all), with every
    finding simply counting as new on that first run -- exactly the
    behavior wanted the moment the flag is turned on.
    """
    if not path.exists():
        return LoadResult()
    try:
        raw = path.read_text(encoding="utf-8")
    except OSError as e:
        return LoadResult(warning=f"{path}: could not read baseline ({e})")
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as e:
        return LoadResult(warning=f"{path}: invalid JSON, ignoring baseline ({e})")
    if not isinstance(data, dict) or not isinstance(data.get("findings"), list):
        return LoadResult(warning=f"{path}: not a recognised baseline file, ignoring")

    entries: list[BaselineEntry] = []
    skipped = 0
    for item in data["findings"]:
        if not isinstance(item, dict) or not item.get("rule"):
            skipped += 1
            continue
        entries.append(BaselineEntry(
            rule_id=str(item["rule"]).upper(),
            path=item.get("path"),
            snippet=item.get("snippet"),
            line=item.get("line"),
        ))
    warning = None
    if skipped:
        plural = "entry" if skipped == 1 else "entries"
        warning = f"{path}: {skipped} malformed {plural} ignored"
    return LoadResult(entries=entries, warning=warning)


def write(path: Path, findings: list[Finding], *, version: str, spec: str) -> None:
    """Overwrite `path` with exactly `findings` -- nothing merged in.

    Full regeneration rather than an incremental update is what makes this
    double as the prune mechanism the issue asks for: a finding that's been
    fixed since the last write simply isn't in `findings` any more, so it
    isn't in the file after this call. No separate `--prune-baseline` flag
    is needed.

    `line` is stored for a human reading the file, and is never read back
    by `load()`/`apply()` for matching -- see the module docstring for why
    matching is keyed on the snippet instead.
    """
    data = {
        "tool": "mcp-migrate",
        "version": version,
        "spec": spec,
        "findings": [
            {
                "rule": f.rule_id,
                "path": _path_str(f.path),
                "line": f.line,
                "snippet": f.snippet,
            }
            for f in sorted(
                findings,
                key=lambda f: (f.rule_id, _path_str(f.path) or "", f.line or 0),
            )
        ],
    }
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


@dataclass
class ApplyResult:
    new: list[Finding]
    known: list[Finding]
    stale: list[BaselineEntry]


def apply(findings: list[Finding], entries: list[BaselineEntry]) -> ApplyResult:
    """Partition `findings` into `new` and `known` against `entries`.

    Matching is a multiset on `(rule_id, path, normalized snippet)`: each
    baseline entry can absorb exactly one matching finding. `stale` is
    whatever's left over in `entries` afterward -- baselined occurrences
    nothing this run matched, i.e. fixed or moved code. See the module
    docstring for why this has to be a multiset rather than a set.
    """
    entries_by_key: dict[tuple, list[BaselineEntry]] = {}
    for e in entries:
        entries_by_key.setdefault(e.key(), []).append(e)
    available: Counter = Counter({k: len(v) for k, v in entries_by_key.items()})

    # Sorted so matching is deterministic when a key has more findings than
    # baseline entries (or vice versa) -- earliest line in the file wins the
    # "known" slot, consistent with how a human would read the diff.
    findings_sorted = sorted(
        findings, key=lambda f: (_path_str(f.path) or "", f.line or 0)
    )
    new: list[Finding] = []
    known: list[Finding] = []
    for f in findings_sorted:
        k = _finding_key(f)
        if available.get(k, 0) > 0:
            available[k] -= 1
            known.append(f)
        else:
            new.append(f)

    stale: list[BaselineEntry] = []
    for k, leftover in available.items():
        if leftover > 0:
            stale.extend(entries_by_key[k][:leftover])
    return ApplyResult(new=new, known=known, stale=stale)
