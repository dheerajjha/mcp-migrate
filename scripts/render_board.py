#!/usr/bin/env python3
"""Regenerate the board table in README.md from registry/servers/*.yaml."""
from __future__ import annotations

from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
SERVERS = ROOT / "registry" / "servers"
README = ROOT / "README.md"
START, END = "<!-- BOARD:START -->", "<!-- BOARD:END -->"

ORDER = {"A": 0, "B": 1, "C": 2, "D": 3, "F": 4}
EMOJI = {"ready": "ready", "migrating": "migrating", "unmaintained": "unmaintained"}


def main() -> int:
    entries = []
    for path in sorted(SERVERS.glob("*.yaml")):
        data = yaml.safe_load(path.read_text())
        if isinstance(data, dict):
            entries.append(data)
    entries.sort(key=lambda d: (ORDER.get(d.get("grade", "F"), 9), -d.get("score", 0), d.get("name", "")))

    rows = ["| server | grade | status | language | what it does |",
            "| --- | --- | --- | --- | --- |"]
    for e in entries:
        repo = e.get("repo", "")
        notes = str(e.get("notes", "")).strip().replace("|", "\\|")
        rows.append(
            f"| [{e.get('name')}](https://github.com/{repo}) | **{e.get('grade')}** "
            f"| {EMOJI.get(e.get('status'), e.get('status'))} | {e.get('language')} | {notes} |"
        )

    tally = {}
    for e in entries:
        tally[e.get("grade")] = tally.get(e.get("grade"), 0) + 1
    summary = ", ".join(f"{tally[g]}x {g}" for g in "ABCDF" if g in tally)
    table = f"\n**{len(entries)} servers checked** ({summary or 'none yet'})\n\n" + "\n".join(rows) + "\n"

    text = README.read_text()
    if START not in text or END not in text:
        print("board markers missing from README.md")
        return 1
    before = text.split(START)[0]
    after = text.split(END)[1]
    README.write_text(f"{before}{START}\n{table}\n{END}{after}")
    print(f"rendered {len(entries)} entries")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
