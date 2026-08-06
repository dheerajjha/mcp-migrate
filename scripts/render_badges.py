#!/usr/bin/env python3
"""Generate shields.io endpoint JSON from registry/servers/*.yaml.

The badge `check` prints today is frozen at the moment it was printed. It
keeps saying A after the project regresses, after the spec moves, after a
rule ships that the project fails. A migration badge that cannot go stale
is worse than no badge: it is a claim that quietly stops being true, and
the reader has no way to tell.

A shields.io *endpoint* badge fixes that by inverting who holds the value.
Instead of baking the grade into the image URL, the URL points at a JSON
document we publish, and shields renders whatever it says at request time.
Regenerate the JSON when the registry changes and every badge in every
README updates itself.

    https://img.shields.io/endpoint?url=https://dheerajjha.github.io/mcp-migrate/badge/sooperset/mcp-atlassian.json

This is a transform over data we already have -- `registry/servers/*.yaml`
carries a grade per listed server -- not new analysis. No server, no
database, no secrets: static files on GitHub Pages.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
SERVERS = ROOT / "registry" / "servers"
OUT = ROOT / "docs" / "badge"

LABEL = "MCP 2026-07-28"

# Must agree with how the grades read elsewhere, or the badge undermines
# the thing it is reporting: a C rendered in green teaches the reader that
# the colour means nothing, and then the next badge is not trusted either.
GRADE_COLOR = {
    "A": "brightgreen",
    "B": "brightgreen",
    "C": "yellow",
    "D": "red",
    "F": "red",
}
UNKNOWN_COLOR = "lightgrey"

# A 404 renders as a broken image on a stranger's README. Anyone can point
# an endpoint URL at us -- including at a repo we have never scanned -- so
# the miss case has to be a real, valid badge that says so plainly.
UNKNOWN = {
    "schemaVersion": 1,
    "label": LABEL,
    "message": "not listed",
    "color": UNKNOWN_COLOR,
    "isError": False,
}


def slug(repo: str) -> str:
    """`owner/name` -> the path segment we publish it under.

    Kept deliberately strict rather than URL-escaping: a repo field that
    is not a plain `owner/name` is a registry error worth surfacing, not
    something to encode and forget. Callers get None and decide.
    """
    parts = [p for p in str(repo).strip().strip("/").split("/") if p]
    if len(parts) != 2:
        return ""
    owner, name = parts
    if any(c in owner + name for c in "\\?#%..") or not owner or not name:
        return ""
    return f"{owner}/{name}"


WORST_FIRST = ["F", "D", "C", "B", "A"]


def _label(version: str = "", suffix: str = "") -> str:
    """`checked_with` rides in the label rather than being dropped.

    A badge that renders live but reflects a scan from six weeks ago is
    only slightly better than a frozen one. Naming the version that
    produced the grade is the cheapest honest form of that caveat, and it
    is already in the YAML.
    """
    label = f"{LABEL} ({version})" if version else LABEL
    return f"{label} {suffix}".strip()


def _version(entry: dict) -> str:
    return str(entry.get("checked_with", "")).replace("mcp-migrate", "").strip()


def badge_for(entry: dict) -> dict:
    """The shields endpoint document for one registry entry."""
    grade = str(entry.get("grade", "")).upper()
    label = _label(_version(entry))

    if grade not in GRADE_COLOR:
        # A grade outside A-F means the registry is wrong, and inventing a
        # colour for it would hide that. Say unknown; validate_registry.py
        # is where it gets rejected.
        return {**UNKNOWN, "label": label, "message": "unknown"}

    return {
        "schemaVersion": 1,
        "label": label,
        "message": grade,
        "color": GRADE_COLOR[grade],
        "isError": False,
    }


def badge_for_repo(entries: list[dict]) -> dict:
    """The document for a whole repository, which may hold several servers.

    Monorepos are the case the obvious implementation gets wrong. Three
    registry entries share `modelcontextprotocol/servers` and three share
    `awslabs/mcp`; keying badges by repo alone means the last one written
    wins and the badge reports an arbitrary one of the three grades, with
    nothing on screen to say so.

    So a multi-server repo reports its **worst** grade, and says how many
    servers that covers. Worst rather than mean or best because this badge
    is a migration-readiness claim: "one of the servers in here is an F"
    is the fact a reader needs, and averaging it away would produce
    exactly the quietly-untrue badge this whole change exists to remove.
    """
    if len(entries) == 1:
        return badge_for(entries[0])

    grades = {str(e.get("grade", "")).upper() for e in entries}
    worst = next((g for g in WORST_FIRST if g in grades), None)
    version = _version(entries[0])
    label = _label(version, f"({len(entries)} servers)")

    if worst is None:
        return {**UNKNOWN, "label": label, "message": "unknown"}

    return {
        "schemaVersion": 1,
        "label": label,
        "message": worst,
        "color": GRADE_COLOR[worst],
        "isError": False,
    }


def load_entries() -> list[dict]:
    entries = []
    for path in sorted(SERVERS.glob("*.yaml")):
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
        if isinstance(data, dict):
            entries.append(data)
    return entries


def render(entries: list[dict], out: Path) -> tuple[int, list[str]]:
    """Write the endpoint documents.

    Two addresses per server, because they answer different questions:

      docs/badge/<name>.json          one registry entry, exactly
      docs/badge/<owner>/<repo>.json  the repository as a whole

    `name` is unique by construction (it must match the filename), so it
    is the precise address for a server inside a monorepo. The repo path
    is what someone puts in a README, and aggregates when it has to.

    Returns (files written, problems). Problems are reported rather than
    raised so one malformed entry cannot stop every other badge from
    regenerating -- a stale badge is the bug being fixed here.
    """
    out.mkdir(parents=True, exist_ok=True)
    problems: list[str] = []
    written = 0

    by_repo: dict[str, list[dict]] = {}

    for entry in entries:
        name = str(entry.get("name", "")).strip()
        if name and "/" not in name and ".." not in name:
            (out / f"{name}.json").write_text(
                json.dumps(badge_for(entry), indent=2) + "\n", encoding="utf-8",
            )
            written += 1
        else:
            problems.append(f"entry with repo {entry.get('repo')!r} has an unusable name {name!r}")

        path_slug = slug(entry.get("repo", ""))
        if not path_slug:
            problems.append(
                f"{name or '<unnamed>'}: repo {entry.get('repo')!r} is not a "
                "plain owner/name, no repo-level badge written"
            )
            continue
        by_repo.setdefault(path_slug, []).append(entry)

    for path_slug, group in by_repo.items():
        target = out / f"{path_slug}.json"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(
            json.dumps(badge_for_repo(group), indent=2) + "\n", encoding="utf-8",
        )
        written += 1

    # Served for anything not in the registry, so an unlisted repo renders
    # a badge instead of a broken image on someone's README.
    (out / "unknown.json").write_text(
        json.dumps(UNKNOWN, indent=2) + "\n", encoding="utf-8",
    )

    return written, problems


def main() -> int:
    entries = load_entries()
    written, problems = render(entries, OUT)

    for problem in problems:
        print(f"warning: {problem}", file=sys.stderr)

    rel = OUT.relative_to(ROOT)
    print(f"Wrote {written} badge endpoint(s) to {rel}/ (+ unknown.json)")
    # Warnings, not failures: a bad `repo` field is validate_registry.py's
    # job to reject, and failing here as well would only stop every other
    # badge from being refreshed.
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
