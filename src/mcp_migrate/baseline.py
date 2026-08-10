"""Baseline: let `check` fail only on findings introduced since a snapshot.

A finding's (path, line) address moves whenever a line above it is
inserted or removed, so keying a baseline on line number alone would treat
every reflow as an entirely new set of findings. Instead a finding is
identified by (rule id, path, the text of the line it points at) -- the
line's own content survives edits elsewhere in the file far better than a
line number does. A finding with no line to point at (project-wide, like
R010) falls back to its message, since there is nothing else to anchor on.

`score()` never reads this module -- it runs over every finding a rule
produced, baselined or not (see cli.run_check_detailed). This module only
decides which of those findings are new enough to fail `check` on. The
letter grade is a claim about the code; the baseline is a claim about what
a team has, for now, agreed to tolerate, and the two must not blend.
"""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

from .rules.base import Finding, Project

BASELINE_VERSION = 1
DEFAULT_FILENAME = ".mcp-migrate-baseline.json"


class BaselineError(Exception):
    """The baseline file exists but is not one mcp-migrate can read."""


def _anchor_line(project: Project, path: Path | None, line: int | None) -> str | None:
    if path is None or line is None or line < 1:
        return None
    for f in project.files:
        if f.path == path:
            lines = f.lines
            return lines[line - 1].strip() if line <= len(lines) else None
    return None


def finding_key(f: Finding, project: Project) -> tuple[str, str, str]:
    """What identifies `f` across edits: not where it is, but what it is."""
    path = str(f.path) if f.path else ""
    anchor = _anchor_line(project, f.path, f.line) or f.message.strip()
    return (f.rule_id, path, anchor)


def build(findings: list[Finding], project: Project) -> list[dict]:
    """Every current finding, as a baseline entry ready to serialize."""
    entries = []
    for f in findings:
        rule_id, path, anchor = finding_key(f, project)
        entries.append({
            "rule": rule_id,
            "path": str(f.path) if f.path else None,
            "line": f.line,
            "message": f.message,
            "key": [rule_id, path, anchor],
        })
    entries.sort(key=lambda e: (e["rule"], e["path"] or "", e["line"] or 0))
    return entries


def write(path: Path, findings: list[Finding], project: Project) -> int:
    """Write a baseline to `path`. Returns how many findings were recorded."""
    entries = build(findings, project)
    path.write_text(
        json.dumps({"version": BASELINE_VERSION, "findings": entries}, indent=2) + "\n",
        encoding="utf-8",
    )
    return len(entries)


def load(path: Path) -> list[dict]:
    try:
        raw = path.read_text(encoding="utf-8")
    except OSError as e:
        raise BaselineError(f"could not read {path}: {e}") from e
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as e:
        raise BaselineError(f"{path} is not valid JSON: {e}") from e
    if not isinstance(data, dict) or not isinstance(data.get("findings"), list):
        raise BaselineError(f'{path} does not look like a baseline file (no "findings" list)')
    return data["findings"]


def diff(
    findings: list[Finding], project: Project, baseline_entries: list[dict],
) -> tuple[list[Finding], list[dict]]:
    """(findings not accounted for by the baseline, baseline entries nothing matched).

    Matching consumes one baseline entry per matching finding, so two
    findings that happen to share a key (the same line pattern hit twice
    in one file) are tracked by count rather than by mere presence -- a
    baseline of one such finding still flags the second as new.
    """
    by_key: dict[tuple, list[dict]] = {}
    for e in baseline_entries:
        by_key.setdefault(tuple(e["key"]), []).append(e)

    matched = Counter()
    new_findings = []
    for f in findings:
        key = finding_key(f, project)
        if matched[key] < len(by_key.get(key, ())):
            matched[key] += 1
        else:
            new_findings.append(f)

    stale = []
    for key, entries in by_key.items():
        unmatched = len(entries) - matched[key]
        if unmatched > 0:
            stale.extend(entries[:unmatched])
    stale.sort(key=lambda e: (e["rule"], e["path"] or "", e["line"] or 0))
    return new_findings, stale
