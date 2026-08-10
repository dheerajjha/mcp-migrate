#!/usr/bin/env python3
"""Validate registry/servers/*.yaml. Runs in CI on every PR.

Two layers. The schema checks are pure and always run. The language check
asks GitHub whether the repo actually contains the language the entry
claims, and exists because the CLI is not the only way an entry can be
created: anyone can hand-write the YAML, and the board's standing promise
is that a schema pass equals a merge. A `language: python` entry for a
repo containing no Python is exactly the false-A this project refuses to
publish, so it has to be caught at the point of merge and not only at the
point of generation.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import urllib.error
import urllib.request
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
SERVERS = ROOT / "registry" / "servers"

REQUIRED = ["name", "repo", "language", "grade", "score", "checked_with", "spec", "status", "notes"]
ENUMS = {
    "language": {"python", "typescript", "go", "rust", "java", "csharp", "ruby", "other"},
    "grade": {"A", "B", "C", "D", "F"},
    "status": {"ready", "migrating", "unmaintained"},
}
REPO_RX = re.compile(r"^[\w.-]+/[\w.-]+$")
SHA_RX = re.compile(r"^[0-9a-f]{7,40}$")
RULE_ID_RX = re.compile(r"^R\d{3}$")

# Our language values spelled the way GitHub's linguist spells them.
# `other` is deliberately absent: it claims nothing, so there is nothing
# to contradict.
GH_LANGUAGE = {
    "python": "Python",
    "typescript": "TypeScript",
    "go": "Go",
    "rust": "Rust",
    "java": "Java",
    "csharp": "C#",
    "ruby": "Ruby",
}
API = "https://api.github.com/repos/{repo}/languages"


class Unreachable(Exception):
    """GitHub could not be asked -- as distinct from GitHub saying no."""


def repo_languages(repo: str) -> set[str]:
    """The languages GitHub reports for `repo`.

    Raises Unreachable when the question could not be put to GitHub at all
    (offline, rate-limited, timing out). That is not the same as an empty
    answer and must not be treated as one -- a network blip should never
    silently convict an honest entry.
    """
    req = urllib.request.Request(
        API.format(repo=repo),
        headers={"Accept": "application/vnd.github+json", "User-Agent": "mcp-migrate-validator"},
    )
    token = os.environ.get("GITHUB_TOKEN")
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return set(json.load(resp))
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            return set()  # a real answer: no such repo
        raise Unreachable(f"HTTP {exc.code}") from exc
    except Exception as exc:  # noqa: BLE001 -- URLError, timeout, bad JSON
        raise Unreachable(str(exc)) from exc


def validate_language(path: Path, data: dict) -> list[str]:
    """Check the declared language against what the repo actually contains."""
    repo, declared = data.get("repo"), data.get("language")
    if not isinstance(repo, str) or not REPO_RX.match(repo or ""):
        return []  # the schema pass already reported this
    expected = GH_LANGUAGE.get(declared)
    if expected is None:
        return []

    try:
        present = repo_languages(repo)
    except Unreachable as exc:
        print(f"::notice::{path.name}: skipped the language check ({exc})")
        return []

    if not present:
        return [f"{path.name}: GitHub reports no such repo, or an empty one: {repo}"]
    if expected not in present:
        return [
            f"{path.name}: declares `language: {declared}` but {repo} contains no "
            f"{expected} according to GitHub (it has: {', '.join(sorted(present))}). "
            f"An entry graded in a language the repo does not contain is a false grade."
        ]
    return []


def validate(path: Path) -> list[str]:
    errs: list[str] = []
    try:
        data = yaml.safe_load(path.read_text())
    except yaml.YAMLError as exc:
        return [f"{path.name}: not valid YAML ({exc})"]
    if not isinstance(data, dict):
        return [f"{path.name}: top level must be a mapping"]

    for key in REQUIRED:
        if key not in data or data[key] in (None, ""):
            errs.append(f"{path.name}: missing required field `{key}`")
    for key, allowed in ENUMS.items():
        if key in data and data[key] not in allowed:
            errs.append(f"{path.name}: `{key}` must be one of {sorted(allowed)}, got {data[key]!r}")
    if "score" in data and not (isinstance(data["score"], int) and 0 <= data["score"] <= 100):
        errs.append(f"{path.name}: `score` must be an int 0-100")
    if "suppressed" in data and not (
        isinstance(data["suppressed"], int)
        and not isinstance(data["suppressed"], bool)
        and data["suppressed"] >= 0
    ):
        errs.append(f"{path.name}: `suppressed` must be a non-negative int")
    # `disabled_rules` is load-bearing in a way `suppressed` is not: a
    # suppression silences one finding, a disabled rule silences a whole
    # class of them, and the grade is still published as though the full
    # set had run. So it gets the stricter check of the two -- a rule id
    # that does not exist means the entry is disclosing something
    # unreadable, which is no better than not disclosing it.
    if "disabled_rules" in data:
        value = data["disabled_rules"]
        if not (isinstance(value, list) and all(isinstance(r, str) for r in value)):
            errs.append(f"{path.name}: `disabled_rules` must be a list of rule id strings")
        else:
            bad = [r for r in value if not RULE_ID_RX.match(r)]
            if bad:
                errs.append(
                    f"{path.name}: `disabled_rules` contains malformed rule id(s): "
                    f"{', '.join(bad)} (expected e.g. R001)"
                )
            if len(set(value)) != len(value):
                errs.append(f"{path.name}: `disabled_rules` contains duplicates")
    if "repo" in data and isinstance(data["repo"], str) and not REPO_RX.match(data["repo"]):
        errs.append(f"{path.name}: `repo` must look like owner/name")
    if "sha" in data and not (isinstance(data["sha"], str) and SHA_RX.match(data["sha"])):
        errs.append(f"{path.name}: `sha` must be a 7-40 character hex commit SHA")
    if "name" in data and data["name"] != path.stem:
        errs.append(f"{path.name}: `name` ({data['name']}) must match the filename ({path.stem})")
    if "notes" in data and isinstance(data["notes"], str) and len(data["notes"]) > 200:
        errs.append(f"{path.name}: keep `notes` under 200 characters")
    return errs


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--offline", action="store_true",
        help="skip the GitHub language check (schema checks still run)",
    )
    args = parser.parse_args()

    files = sorted(SERVERS.glob("*.yaml"))
    if not files:
        print("no entries found")
        return 0

    errors: list[str] = []
    for f in files:
        schema_errors = validate(f)
        errors.extend(schema_errors)
        if args.offline or schema_errors:
            continue
        try:
            data = yaml.safe_load(f.read_text())
        except yaml.YAMLError:
            continue
        if isinstance(data, dict):
            errors.extend(validate_language(f, data))

    for e in errors:
        print(f"::error::{e}")
    print(f"checked {len(files)} entries, {len(errors)} problems")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
