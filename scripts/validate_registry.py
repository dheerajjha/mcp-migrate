#!/usr/bin/env python3
"""Validate registry/servers/*.yaml. Runs in CI on every PR."""
from __future__ import annotations

import re
import sys
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
    if "repo" in data and isinstance(data["repo"], str) and not REPO_RX.match(data["repo"]):
        errs.append(f"{path.name}: `repo` must look like owner/name")
    if "name" in data and data["name"] != path.stem:
        errs.append(f"{path.name}: `name` ({data['name']}) must match the filename ({path.stem})")
    if "notes" in data and isinstance(data["notes"], str) and len(data["notes"]) > 200:
        errs.append(f"{path.name}: keep `notes` under 200 characters")
    return errs


def main() -> int:
    files = sorted(SERVERS.glob("*.yaml"))
    if not files:
        print("no entries found")
        return 0
    errors = [e for f in files for e in validate(f)]
    for e in errors:
        print(f"::error::{e}")
    print(f"checked {len(files)} entries, {len(errors)} problems")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
