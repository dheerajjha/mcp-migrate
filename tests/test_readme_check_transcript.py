"""Keep README's headline ``check`` transcript aligned with real CLI output."""
from __future__ import annotations

import json
import re
from collections import Counter
from pathlib import Path

from mcp_migrate import __version__
from mcp_migrate.cli import main

ROOT = Path(__file__).resolve().parent.parent
README = ROOT / "README.md"
FIXTURE = ROOT / "tests" / "fixtures" / "fixer_roundtrip"


def _headline_transcript(readme: str) -> str:
    section = readme.split("## `mcp-migrate check`", 1)[1]
    return section.split("```", 2)[1]


def test_headline_check_transcript_matches_cli(capsys):
    exit_code = main(["check", str(FIXTURE), "--json"])
    data = json.loads(capsys.readouterr().out)
    assert exit_code == 1

    readme = README.read_text(encoding="utf-8")
    transcript = _headline_transcript(readme)

    assert f"mcp-migrate v{data['version']}  ->  fixer_roundtrip" in transcript

    finding_counts = Counter(
        (finding["severity"], finding["rule"])
        for finding in data["findings"]
    )
    for (severity, rule), count in finding_counts.items():
        rows = re.findall(rf"(?m)^{severity}\s+{rule}\s+", transcript)
        assert len(rows) == count, (
            f"README lists {len(rows)} {severity} {rule} row(s); CLI reports {count}"
        )

    counts = data["counts"]
    summary = (
        f"Grade {data['grade']} ({data['score']}/100)  "
        f"{counts['breaking']} breaking, {counts['deprecated']} deprecated, "
        f"{counts['advisory']} advisory"
    )
    assert summary in transcript


def test_readme_cli_banners_match_package_version():
    readme = README.read_text(encoding="utf-8")
    versions = re.findall(r"mcp-migrate v(\d+\.\d+\.\d+)\s+->", readme)
    assert versions
    assert set(versions) == {__version__}


def test_readme_typescript_block_matches_the_ungraded_message(tmp_path, capsys):
    """README's TypeScript transcript, against the sentence the CLI actually prints.

    #265 was three stale numbers in the Python transcript; #268 pinned those.
    This block was left unpinned and had drifted the same way -- README said
    "Every rule reads it now", the tool says "TypeScript is read by every
    rule". Same class of bug, one section down, and nothing was holding it.

    Asserted against a real run rather than a hardcoded string, so a future
    rewording of the message fails here instead of silently making the README
    a paraphrase again.
    """
    (tmp_path / "server.ts").write_text(
        'import { SSEServerTransport } from "@modelcontextprotocol/sdk/server/sse.js";\n'
        'const transport = new SSEServerTransport("/messages", res);\n',
        encoding="utf-8",
    )
    main(["check", str(tmp_path)])
    # Whitespace-collapsed on both sides: rich wraps the console message at the
    # terminal width and README wraps it for the page, so the line breaks
    # differ by construction and only the words are comparable.
    printed = " ".join(capsys.readouterr().out.split())

    readme = README.read_text(encoding="utf-8")
    ts_section = readme.split("$ mcp-migrate check ./my-ts-server", 1)[1]
    documented = " ".join(ts_section.split("```", 1)[0].split())

    claim = "TypeScript is read by every rule, but whether it gets graded is"
    assert claim in printed, "the CLI no longer prints the sentence this test pins"
    assert claim in documented, (
        "README's TypeScript block has drifted from the message the CLI prints.\n"
        f"  CLI:    ...{claim}...\n"
        "  README: see the block under `$ mcp-migrate check ./my-ts-server`"
    )
