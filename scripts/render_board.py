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
        # `or 0` rather than a default: a `suppressed:` key written with no
        # value parses as None, and None > 0 is a TypeError. validate_registry
        # rejects that entry, but this script runs independently of it, and a
        # traceback is a worse answer than a rendered board.
        suppression_note = (
            f" ({e['suppressed']} suppressed)" if (e.get("suppressed") or 0) > 0 else ""
        )
        # A disabled rule never ran, so the grade is computed as though the
        # full rule set had passed. Recording that in the YAML and not here
        # would be disclosure nobody reads: the whole question a board answers
        # is whether two A grades mean the same thing, and they do not when
        # one of them switched a breaking rule off. Same `or []` reasoning as
        # above -- an empty `disabled_rules:` key parses as None.
        disabled = e.get("disabled_rules") or []
        disabled_note = (
            f" ({len(disabled)} rule{'s' if len(disabled) > 1 else ''} off: "
            f"{', '.join(sorted(disabled))})"
            if disabled
            else ""
        )
        rows.append(
            f"| [{e.get('name')}](https://github.com/{repo}) | **{e.get('grade')}**{suppression_note}{disabled_note} "
            f"| {EMOJI.get(e.get('status'), e.get('status'))} | {e.get('language')} | {notes} |"
        )

    tally = {}
    for e in entries:
        tally[e.get("grade")] = tally.get(e.get("grade"), 0) + 1
    summary = ", ".join(f"{tally[g]}x {g}" for g in "ABCDF" if g in tally)

    # "Checked" and "opted in" are different claims and the headline says which
    # is which. Every entry here was written by this project scanning a public
    # repo -- that is a survey, not adoption, and a board that blurred the two
    # would be overclaiming in exactly the way this tool refuses to elsewhere.
    owned = sum(1 for e in entries if e.get("submitted_by") == "owner")
    if owned:
        provenance = (
            f"**{owned} submitted by the server's own maintainers**, "
            f"{len(entries) - owned} checked by this project."
        )
    else:
        provenance = (
            "All of these were checked by this project, not submitted by the "
            "servers' maintainers -- so read it as a survey, not as adoption. "
            "If you maintain one of these, "
            "[submit your own entry](registry/README.md) and it becomes yours."
        )

    table = (
        f"\n**{len(entries)} servers checked** ({summary or 'none yet'})\n\n"
        f"{provenance}\n\n" + "\n".join(rows) + "\n"
    )

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
