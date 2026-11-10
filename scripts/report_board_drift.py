#!/usr/bin/env python3
"""Report regrade drift without treating scan failures as grade changes."""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

MARKER = "<!-- mcp-migrate-board-drift -->"
TITLE = "Published board grades have drifted"


def gh(*args: str, input_text: str | None = None) -> str:
    result = subprocess.run(
        ["gh", *args], input=input_text, text=True, capture_output=True, check=True
    )
    return result.stdout


def report(path: Path, status: int) -> int:
    if status not in (0, 1):
        print(f"Regrade failed operationally (exit {status}).", file=sys.stderr)
        return 2
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        drifts, problems = data["drifts"], data["problems"]
        if not isinstance(drifts, list) or not isinstance(problems, list):
            raise ValueError("drifts and problems must be lists")
        if bool(status) != bool(drifts or problems):
            raise ValueError("exit status does not match regrade output")
    except (OSError, ValueError, KeyError, TypeError) as exc:
        print(f"Invalid regrade output: {exc}", file=sys.stderr)
        return 2

    if problems:
        print("Regrade operational problems:", file=sys.stderr)
        for problem in problems:
            print(f"  {problem!r}", file=sys.stderr)

    if drifts:
        repo = os.environ["GITHUB_REPOSITORY"]
        endpoint = f"repos/{repo}/issues"
        pages = json.loads(gh("api", "--paginate", "--slurp", f"{endpoint}?state=open&per_page=100"))
        existing = any(
            not issue.get("pull_request")
            and issue.get("user", {}).get("login") == "github-actions[bot]"
            and MARKER in (issue.get("body") or "")
            for page in pages
            for issue in page
        )
        if existing:
            print("An open board drift report already exists.")
        else:
            details = json.dumps(drifts, indent=2, ensure_ascii=True)
            body = (
                f"{MARKER}\nThe pinned board regrade found grade or score drift. "
                "Review the recorded and current values and update the registry if appropriate.\n\n"
                + "\n".join("    " + line for line in details.splitlines())
            )
            payload = json.dumps({"title": TITLE, "body": body})
            gh("api", "--method", "POST", endpoint, "--input", "-", input_text=payload)
            print("Opened a board drift report.")

    return 1 if drifts or problems else 0


if __name__ == "__main__":
    try:
        sys.exit(report(Path(sys.argv[1]), int(sys.argv[2])))
    except (subprocess.CalledProcessError, OSError, ValueError, KeyError, IndexError) as exc:
        print(f"Could not report regrade result: {exc}", file=sys.stderr)
        sys.exit(2)
