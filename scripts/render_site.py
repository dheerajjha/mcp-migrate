#!/usr/bin/env python3
"""Regenerate docs/index.html -- the GitHub Pages landing page.

GitHub Pages was enabled on this repo (source: main:/docs) long before
anything was there to serve, so https://dheerajjha.github.io/mcp-migrate/
answered 404 while looking, from the repo settings, perfectly healthy.

The page is GENERATED, for the same reason the board and the badges are:
the one thing a landing page must never do is describe a version of the
tool that no longer exists. Every fact on it -- the version, the rule
count, the rule text, the board, the grade colours -- is read here from
the same source the CLI reads, so the page cannot drift from the tool
without a test noticing (see tests/test_site.py).

Why the full rule list is on the page and not a link to it: someone whose
server just broke does not search for "mcp-migrate". They search for the
symptom -- "Mcp-Session-Id removed", "-32002 resource not found", "MCP
initialize replaced". Those 21 strings are the only reason a stranger
ever arrives here, so they have to be indexable text on the page rather
than rows that appear after a click.
"""
from __future__ import annotations

import html
import re
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from mcp_migrate import __version__  # noqa: E402
from mcp_migrate.constants import GRADE_COLOR  # noqa: E402
from mcp_migrate.rules import all_rules  # noqa: E402

SERVERS = ROOT / "registry" / "servers"
OUT = ROOT / "docs" / "index.html"

SITE = "https://dheerajjha.github.io/mcp-migrate/"
REPO = "https://github.com/dheerajjha/mcp-migrate"
SPEC = "2026-07-28"

ORDER = {"A": 0, "B": 1, "C": 2, "D": 3, "F": 4}

# The badge palette is the page palette. A grade rendered one colour in the
# README badge and another here would teach the reader the colour is
# decoration -- the exact failure #226/#229 fixed inside the tool.
HEX = {
    "brightgreen": "#3fb950",
    "green": "#2ea043",
    "yellow": "#d29922",
    "orange": "#db6d28",
    "red": "#f85149",
}

SEV_LABEL = {"breaking": "breaking", "deprecated": "deprecated", "advisory": "advisory"}


def e(s: object) -> str:
    return html.escape(str(s), quote=True)


def split_ref(ref: str) -> tuple[str, str]:
    """`spec_ref` is either 'SEP-1234 <url>' or a bare url."""
    ref = (ref or "").strip()
    m = re.match(r"^(\S+)\s+(https?://\S+)$", ref)
    if m:
        return m.group(1), m.group(2)
    if ref.startswith("http"):
        return "spec", ref
    return ref, ""


def load_entries() -> list[dict]:
    entries = []
    for path in sorted(SERVERS.glob("*.yaml")):
        data = yaml.safe_load(path.read_text())
        if isinstance(data, dict):
            entries.append(data)
    entries.sort(
        key=lambda d: (ORDER.get(d.get("grade", "F"), 9), -(d.get("score") or 0), d.get("name", ""))
    )
    return entries


def board_rows(entries: list[dict]) -> str:
    out = []
    for x in entries:
        grade = x.get("grade", "?")
        colour = HEX.get(GRADE_COLOR.get(grade, ""), "#8b949e")
        score = x.get("score")
        score_txt = f"{score}/100" if score is not None else "&mdash;"
        repo = e(x.get("repo", ""))
        out.append(
            f'<tr>'
            f'<td class="s"><a href="https://github.com/{repo}">{e(x.get("name"))}</a>'
            f'<span class="repo">{repo}</span></td>'
            f'<td><span class="g" style="background:{colour}">{e(grade)}</span></td>'
            f'<td class="num">{score_txt}</td>'
            f'<td class="lang">{e(x.get("language", ""))}</td>'
            f'<td class="what">{e(x.get("notes", "")).strip()}</td>'
            f'</tr>'
        )
    return "\n".join(out)


def rule_rows(rules) -> str:
    out = []
    for r in rules:
        label, url = split_ref(r.spec_ref)
        ref = f'<a href="{e(url)}">{e(label)}</a>' if url else e(label)
        out.append(
            f'<tr id="{e(r.id.lower())}">'
            f'<td class="rid"><a href="#{e(r.id.lower())}">{e(r.id)}</a></td>'
            f'<td><span class="sev sev-{e(r.severity)}">{e(SEV_LABEL.get(r.severity, r.severity))}</span></td>'
            f'<td class="rt"><strong>{e(r.title)}</strong><span class="fix">{e(r.fix)}</span></td>'
            f'<td class="ref">{ref}</td>'
            f'</tr>'
        )
    return "\n".join(out)


def main() -> int:
    entries = load_entries()
    rules = all_rules()

    tally: dict[str, int] = {}
    for x in entries:
        tally[x.get("grade")] = tally.get(x.get("grade"), 0) + 1
    summary = ", ".join(f"{tally[g]}× {g}" for g in "ABCDF" if g in tally)

    n_breaking = sum(1 for r in rules if r.severity == "breaking")
    n_dep = sum(1 for r in rules if r.severity == "deprecated")
    n_adv = sum(1 for r in rules if r.severity == "advisory")

    # The same claim the README board makes, in the same words. A landing
    # page is exactly where the temptation is to round "we scanned these"
    # up to "these adopted us"; the tool refuses to overclaim about a
    # codebase, so the site does not get to overclaim about the tool.
    owned = sum(1 for x in entries if x.get("submitted_by") == "owner")
    if owned:
        provenance = (
            f"<strong>{owned} submitted by the server&rsquo;s own maintainers</strong>, "
            f"{len(entries) - owned} checked by this project."
        )
    else:
        provenance = (
            "Every row here was produced by this project scanning a public repository. "
            "It is a survey, not a list of adopters &mdash; nobody below has endorsed "
            f"this tool. If you maintain one of them, <a href=\"{REPO}/blob/main/registry/README.md\">"
            "submit your own entry</a> and it becomes yours to correct."
        )

    desc = (
        f"The MCP {SPEC} spec revision removes sessions, the initialize handshake, "
        f"ping, logging/setLevel and resources/subscribe. mcp-migrate finds all "
        f"{len(rules)} breakages in your server and fixes {n_breaking} of them for you."
    )

    doc = f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Is your MCP server ready for {SPEC}? &middot; mcp-migrate</title>
<meta name="description" content="{e(desc)}">
<link rel="canonical" href="{SITE}">
<meta property="og:type" content="website">
<meta property="og:url" content="{SITE}">
<meta property="og:title" content="Is your MCP server ready for {SPEC}?">
<meta property="og:description" content="{e(desc)}">
<meta property="og:image" content="{REPO}/raw/main/docs/banner.jpg">
<meta name="twitter:card" content="summary_large_image">
<meta name="twitter:title" content="Is your MCP server ready for {SPEC}?">
<meta name="twitter:description" content="{e(desc)}">
<meta name="twitter:image" content="{REPO}/raw/main/docs/banner.jpg">
<style>
:root{{
  --bg:#ffffff; --fg:#1f2328; --mut:#59636e; --line:#d1d9e0; --soft:#f6f8fa;
  --acc:#0969da; --code:#1f2328; --codebg:#f6f8fa;
  --breaking:#f85149; --deprecated:#d29922; --advisory:#8b949e;
}}
@media (prefers-color-scheme:dark){{
  :root:not([data-theme="light"]){{
    --bg:#0d1117; --fg:#e6edf3; --mut:#9198a1; --line:#2f3742; --soft:#151b23;
    --acc:#4493f8; --code:#e6edf3; --codebg:#151b23;
  }}
}}
:root[data-theme="dark"]{{
  --bg:#0d1117; --fg:#e6edf3; --mut:#9198a1; --line:#2f3742; --soft:#151b23;
  --acc:#4493f8; --code:#e6edf3; --codebg:#151b23;
}}
*{{box-sizing:border-box}}
body{{background:var(--bg);color:var(--fg);font:16px/1.6 -apple-system,BlinkMacSystemFont,"Segoe UI",Helvetica,Arial,sans-serif;margin:0}}
.wrap{{max-width:920px;margin:0 auto;padding:0 20px}}
a{{color:var(--acc);text-decoration:none}}
a:hover{{text-decoration:underline}}
code,pre{{font-family:ui-monospace,SFMono-Regular,"SF Mono",Menlo,Consolas,monospace}}
header{{padding-block:56px 40px;border-bottom:1px solid var(--line)}}
h1{{font-size:2.1rem;line-height:1.25;margin:0 0 14px;letter-spacing:-.02em}}
.sub{{font-size:1.12rem;color:var(--mut);margin:0 0 28px;max-width:64ch}}
.cta{{background:var(--codebg);border:1px solid var(--line);border-radius:8px;padding:14px 16px;overflow-x:auto;margin:0 0 10px}}
.cta pre{{margin:0;color:var(--code);font-size:.94rem}}
.cta .p{{color:var(--mut);user-select:none}}
.note{{font-size:.88rem;color:var(--mut);margin:0}}
.pills{{display:flex;flex-wrap:wrap;gap:8px;margin:26px 0 0;padding:0;list-style:none}}
.pills li{{font-size:.83rem;color:var(--mut);border:1px solid var(--line);border-radius:999px;padding:3px 11px}}
section{{padding-block:44px;border-bottom:1px solid var(--line)}}
h2{{font-size:1.4rem;margin:0 0 6px;letter-spacing:-.01em}}
.lede{{color:var(--mut);margin:0 0 22px;max-width:70ch}}
.scroll{{overflow-x:auto;-webkit-overflow-scrolling:touch}}
table{{border-collapse:collapse;width:100%;font-size:.9rem}}
th{{text-align:left;font-size:.74rem;text-transform:uppercase;letter-spacing:.05em;color:var(--mut);font-weight:600;padding:0 12px 8px 0;border-bottom:1px solid var(--line);white-space:nowrap}}
td{{padding:11px 12px 11px 0;border-bottom:1px solid var(--line);vertical-align:top}}
.s a{{font-weight:600}}
.repo{{display:block;font-size:.76rem;color:var(--mut);font-family:ui-monospace,monospace}}
.g{{display:inline-block;min-width:22px;text-align:center;color:#fff;font-weight:700;border-radius:4px;padding:1px 7px;font-size:.82rem}}
.num{{font-variant-numeric:tabular-nums;color:var(--mut);white-space:nowrap}}
.lang{{color:var(--mut)}}
.what{{color:var(--mut);min-width:230px}}
.rid a{{font-family:ui-monospace,monospace;font-weight:600}}
.rt strong{{font-weight:600;display:block}}
.fix{{display:block;color:var(--mut);font-size:.86rem;margin-top:3px}}
.ref{{white-space:nowrap;font-size:.84rem}}
.sev{{display:inline-block;font-size:.72rem;font-weight:600;text-transform:uppercase;letter-spacing:.04em;border-radius:4px;padding:2px 7px;color:#fff;white-space:nowrap}}
.sev-breaking{{background:var(--breaking)}}
.sev-deprecated{{background:var(--deprecated)}}
.sev-advisory{{background:var(--advisory)}}
.grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(210px,1fr));gap:18px;margin-top:6px}}
.card{{border:1px solid var(--line);border-radius:8px;padding:16px;background:var(--soft)}}
.card h3{{margin:0 0 6px;font-size:.95rem}}
.card p{{margin:0;font-size:.88rem;color:var(--mut)}}
footer{{padding-block:34px 60px;color:var(--mut);font-size:.88rem}}
footer a{{margin-right:16px}}
@media (max-width:560px){{h1{{font-size:1.6rem}}.what{{display:none}}}}
</style>
</head>
<body>

<header>
<div class="wrap">
<h1>Is your MCP server ready for {SPEC}?</h1>
<p class="sub">The {SPEC} spec revision removes protocol sessions, replaces the
<code>initialize</code> handshake with <code>server/discover</code>, and deletes
<code>ping</code>, <code>logging/setLevel</code> and <code>resources/subscribe</code>.
<strong>mcp-migrate</strong> finds all {len(rules)} of those breakages in your code and rewrites
your server for the ones it can fix safely.</p>
<div class="cta"><pre><span class="p">$ </span>uvx mcp-migrate check .
<span class="p">$ </span>uvx mcp-migrate fix . --write</pre></div>
<p class="note">No install, no config, no account. Exit code 1 if it finds anything, so
it drops straight into CI.</p>
<ul class="pills">
<li>{len(rules)} rules</li>
<li>{n_breaking} breaking &middot; {n_dep} deprecated &middot; {n_adv} advisory</li>
<li>Python &middot; TypeScript (partial)</li>
<li>SARIF for code scanning</li>
<li>v{__version__}</li>
</ul>
</div>
</header>

<section>
<div class="wrap">
<h2>The readiness board</h2>
<p class="lede">{len(entries)} public MCP servers, graded against {SPEC} ({summary}).
{provenance}</p>
<div class="scroll">
<table>
<thead><tr><th>Server</th><th>Grade</th><th>Score</th><th>Lang</th><th>What it does</th></tr></thead>
<tbody>
{board_rows(entries)}
</tbody>
</table>
</div>
</div>
</section>

<section>
<div class="wrap">
<h2>What it checks</h2>
<p class="lede">Every rule, what it means, and the spec change behind it. If your
server is failing and you landed here from a search, find the symptom below.</p>
<div class="scroll">
<table>
<thead><tr><th>Rule</th><th>Severity</th><th>What it finds &amp; what to do</th><th>Spec</th></tr></thead>
<tbody>
{rule_rows(rules)}
</tbody>
</table>
</div>
</div>
</section>

<section>
<div class="wrap">
<h2>Three ways to run it</h2>
<div class="grid">
<div class="card"><h3>Once, right now</h3><p><code>uvx mcp-migrate check .</code> &mdash;
prints a graded report and exits 1 if anything is wrong.</p></div>
<div class="card"><h3>In CI</h3><p>The <a href="https://github.com/marketplace/actions/mcp-migrate">GitHub
Action</a> runs the same check on every push and uploads SARIF to code scanning.</p></div>
<div class="card"><h3>As a pre-commit hook</h3><p>Pinned to a release tag, so a
breaking pattern never lands on main in the first place.</p></div>
</div>
</div>
</section>

<footer>
<div class="wrap">
<a href="{REPO}">Source</a>
<a href="https://pypi.org/project/mcp-migrate/">PyPI</a>
<a href="https://github.com/marketplace/actions/mcp-migrate">GitHub Action</a>
<a href="{REPO}/blob/main/registry/README.md">Add your server</a>
<a href="{REPO}/issues">Issues</a>
<p style="margin:18px 0 0">MIT licensed. Not affiliated with Anthropic or the Model
Context Protocol project. Generated from the registry and the rule set at v{__version__}
&mdash; if this page and the tool disagree, the tool is right and it is a bug.</p>
</div>
</footer>

</body>
</html>
"""

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(doc)
    print(f"rendered {OUT.relative_to(ROOT)}: {len(entries)} servers, {len(rules)} rules, v{__version__}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
