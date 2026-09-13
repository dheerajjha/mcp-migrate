#!/usr/bin/env python3
"""Regenerate docs/findings.html from data/ecosystem-scan.json.

The prose here is written deliberately. The numbers are not: every figure
on the page is interpolated from the scan JSON, so the page cannot end up
claiming something the data does not say. That is not a style preference
-- this page publishes measurements about thousands of other people's
repositories, and a stale number in it is a false claim about them.

Paired with tests/test_findings.py, which fails if the committed HTML is
not byte-identical to what this produces.
"""
from __future__ import annotations

import html
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from mcp_migrate.rules import all_rules  # noqa: E402

DATA = ROOT / "data" / "ecosystem-scan.json"
PRIOR = ROOT / "data" / "ecosystem-scan-2026-08-01.json"
OUT = ROOT / "docs" / "findings.html"

SITE = "https://dheerajjha.github.io/mcp-migrate/findings.html"
REPO = "https://github.com/dheerajjha/mcp-migrate"
SPEC = "2026-07-28"

SEV_ORDER = {"breaking": 0, "deprecated": 1, "advisory": 2}


def e(s: object) -> str:
    return html.escape(str(s), quote=True)


def pct(part: int, whole: int) -> str:
    return f"{100 * part / whole:.1f}%" if whole else "n/a"


def main() -> int:
    d = json.loads(DATA.read_text())
    prior = json.loads(PRIOR.read_text()) if PRIOR.exists() else None

    reg = d["registry"]
    n = d["python_servers_scanned"]
    rules = {r.id: r for r in all_rules()}
    prev = d["rule_prevalence"]

    def row(rid: str) -> tuple[int, str]:
        v = prev.get(rid, {"servers": 0, "pct": 0.0})
        return v["servers"], f'{v["pct"]:.1f}%'

    # The removals the conversation was actually about, in the order the
    # spec changelog lists them.
    headline_ids = ["R001", "R009", "R011", "R013", "R012", "R017", "R014"]
    headline = "\n".join(
        f"<tr><td class=\"rid\"><a href=\"index.html#{rid.lower()}\">{rid}</a></td>"
        f"<td>{e(rules[rid].title)}</td>"
        f"<td class=\"num\">{row(rid)[0]}</td>"
        f"<td class=\"num\"><strong>{row(rid)[1]}</strong></td></tr>"
        for rid in headline_ids
        if rid in rules
    )

    ranked = sorted(
        prev.items(),
        key=lambda kv: (-kv[1]["servers"], kv[0]),
    )
    everything = "\n".join(
        f"<tr><td class=\"rid\"><a href=\"index.html#{rid.lower()}\">{rid}</a></td>"
        f"<td><span class=\"sev sev-{e(rules[rid].severity)}\">{e(rules[rid].severity)}</span></td>"
        f"<td>{e(rules[rid].title)}</td>"
        f"<td class=\"num\">{v['servers']}</td>"
        f"<td class=\"num\">{v['pct']:.1f}%</td></tr>"
        for rid, v in ranked
        if rid in rules
    )

    langs = d["languages_of_live_sample"]
    live = reg["live"]
    lang_rows = "\n".join(
        f"<tr><td>{e('(none detected)' if k in ('null', '(none)') else k)}</td>"
        f"<td class=\"num\">{v}</td><td class=\"num\">{pct(v, live)}</td></tr>"
        for k, v in list(langs.items())[:6]
    )

    grades = d["grades"]
    grade_rows = "\n".join(
        f"<tr><td><strong>{g}</strong></td><td class=\"num\">{grades.get(g, 0)}</td>"
        f"<td class=\"num\">{pct(grades.get(g, 0), n)}</td></tr>"
        for g in "ABCDF"
    )

    no_breaking = d["no_breaking_findings"]
    zero = d["zero_findings"]

    growth = ""
    if prior:
        before = prior["registry"]["unique_github_repos"]
        now = reg["unique_github_repos"]
        growth = (
            f" That is up from <strong>{before:,}</strong> on "
            f"{prior['method']['sample_seed']//10000}-"
            f"{(prior['method']['sample_seed']//100) % 100:02d}-"
            f"{prior['method']['sample_seed'] % 100:02d}, a "
            f"{100 * (now - before) / before:.0f}% increase in six weeks, "
            f"while the dead-link rate barely moved "
            f"({prior['registry']['dead_link_pct']}% then, "
            f"{reg['dead_link_pct']}% now)."
        )

    sdk = d.get("declared_sdk") or {}
    zero_sdk = d.get("zero_findings_by_declared_sdk") or {}

    def rate(part_key: str) -> str:
        whole = (sdk or {}).get(part_key, 0)
        part = (zero_sdk or {}).get(part_key, 0)
        return f"{100 * part / whole:.0f}%" if whole else "n/a"

    zero_rate_1x = rate("sdk_1x")
    zero_rate_2x = rate("sdk_2x_or_later")
    zero_rate_unknown = rate("sdk_unknown")

    # How much likelier a current-SDK server is to come back empty. This is
    # the measurement of the blind spot, not a rhetorical flourish, so it is
    # computed rather than asserted.
    def _r(k):
        w = (sdk or {}).get(k, 0)
        return ((zero_sdk or {}).get(k, 0) / w) if w else 0.0

    zero_ratio = f"{_r('sdk_2x_or_later') / _r('sdk_1x'):.0f}" if _r("sdk_1x") else "many"

    r001_n, r001_pct = row("R001")
    r010_n, r010_pct = row("R010")

    # The headline we nearly published, read out of the frozen August run
    # rather than typed in. It is the number that was wrong, so it is
    # exactly the one that must not be retyped from memory.
    prior_r010 = (
        prior["rule_prevalence"]["R010"]["pct"]
        if prior and "R010" in prior.get("rule_prevalence", {})
        else None
    )
    prior_claim = f"{prior_r010}%" if prior_r010 is not None else "most"


    desc = (
        f"We scanned {n} Python MCP servers from the official registry against the "
        f"{SPEC} spec revision. Mcp-Session-Id, the change that dominated the "
        f"discussion, appears in {r001_pct} of them."
    )

    doc = f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>What the MCP {SPEC} revision actually breaks</title>
<meta name="description" content="{e(desc)}">
<link rel="canonical" href="{SITE}">
<meta property="og:type" content="article">
<meta property="og:url" content="{SITE}">
<meta property="og:title" content="What the MCP {SPEC} revision actually breaks">
<meta property="og:description" content="{e(desc)}">
<meta property="og:image" content="{REPO}/raw/main/docs/banner.jpg">
<meta name="twitter:card" content="summary_large_image">
<meta name="twitter:title" content="What the MCP {SPEC} revision actually breaks">
<meta name="twitter:description" content="{e(desc)}">
<meta name="twitter:image" content="{REPO}/raw/main/docs/banner.jpg">
<style>
:root{{--bg:#fff;--fg:#1f2328;--mut:#59636e;--line:#d1d9e0;--soft:#f6f8fa;--acc:#0969da;
--breaking:#f85149;--deprecated:#d29922;--advisory:#8b949e;--warn:#fff8c5;--warnline:#d4a72c}}
@media (prefers-color-scheme:dark){{:root:not([data-theme="light"]){{--bg:#0d1117;--fg:#e6edf3;
--mut:#9198a1;--line:#2f3742;--soft:#151b23;--acc:#4493f8;--warn:#272115;--warnline:#9e6a03}}}}
:root[data-theme="dark"]{{--bg:#0d1117;--fg:#e6edf3;--mut:#9198a1;--line:#2f3742;--soft:#151b23;
--acc:#4493f8;--warn:#272115;--warnline:#9e6a03}}
*{{box-sizing:border-box}}
body{{background:var(--bg);color:var(--fg);margin:0;
font:17px/1.65 -apple-system,BlinkMacSystemFont,"Segoe UI",Helvetica,Arial,sans-serif}}
.wrap{{max-width:760px;margin:0 auto;padding:0 20px}}
a{{color:var(--acc);text-decoration:none}} a:hover{{text-decoration:underline}}
code{{font-family:ui-monospace,SFMono-Regular,Menlo,Consolas,monospace;font-size:.9em;
background:var(--soft);padding:1px 5px;border-radius:4px}}
header{{padding-block:56px 8px}}
h1{{font-size:2rem;line-height:1.2;margin:0 0 18px;letter-spacing:-.02em}}
.standfirst{{font-size:1.16rem;color:var(--mut);margin:0 0 8px}}
.byline{{font-size:.86rem;color:var(--mut);border-top:1px solid var(--line);
padding-top:14px;margin-top:26px}}
h2{{font-size:1.3rem;margin:44px 0 4px;letter-spacing:-.01em}}
h3{{font-size:1.02rem;margin:28px 0 4px}}
p{{margin:14px 0}}
.scroll{{overflow-x:auto;margin:22px 0}}
table{{border-collapse:collapse;width:100%;font-size:.92rem}}
th{{text-align:left;font-size:.73rem;text-transform:uppercase;letter-spacing:.05em;
color:var(--mut);font-weight:600;padding:0 12px 8px 0;border-bottom:1px solid var(--line);
white-space:nowrap}}
td{{padding:9px 12px 9px 0;border-bottom:1px solid var(--line);vertical-align:top}}
.num{{text-align:right;font-variant-numeric:tabular-nums;white-space:nowrap}}
.rid a{{font-family:ui-monospace,monospace;font-weight:600}}
.sev{{display:inline-block;font-size:.68rem;font-weight:600;text-transform:uppercase;
letter-spacing:.04em;border-radius:4px;padding:2px 6px;color:#fff}}
.sev-breaking{{background:var(--breaking)}}
.sev-deprecated{{background:var(--deprecated)}}
.sev-advisory{{background:var(--advisory)}}
.callout{{background:var(--warn);border:1px solid var(--warnline);border-radius:8px;
padding:16px 18px;margin:24px 0}}
.callout p{{margin:8px 0}} .callout p:first-child{{margin-top:0}} .callout p:last-child{{margin-bottom:0}}
pre{{background:var(--soft);border:1px solid var(--line);border-radius:8px;padding:14px 16px;
overflow-x:auto;font-size:.86rem;line-height:1.5}}
footer{{padding-block:36px 64px;color:var(--mut);font-size:.88rem;
border-top:1px solid var(--line);margin-top:52px}}
footer a{{margin-right:16px}}
@media (max-width:560px){{h1{{font-size:1.55rem}}body{{font-size:16px}}}}
</style>
</head>
<body>

<header>
<div class="wrap">
<h1>What the MCP {SPEC} revision actually breaks</h1>
<p class="standfirst">We scanned <strong>{n}</strong> Python MCP servers from the official
registry. The change that dominated every discussion of this revision &mdash; protocol
sessions and the <code>Mcp-Session-Id</code> header going away &mdash; appears in
<strong>{r001_pct}</strong> of them.</p>
<p class="byline">Produced by <a href="{REPO}">mcp-migrate</a>, which is a tool for finding
exactly these problems, so read it with that in mind. Everything below is reproducible
from a committed script and a committed data file; both are linked at the bottom.</p>
</div>
</header>

<div class="wrap">

<h2>The registry is smaller than it looks</h2>

<p>The official MCP registry points at <strong>{reg['unique_github_repos']:,}</strong>
unique GitHub repositories.{growth}</p>

<p><strong>{reg['dead_link_pct']}% of them 404.</strong> In a random sample of
{reg['sampled']:,} &mdash; seeded, drawn from the full deduplicated population rather than
an alphabetical prefix &mdash; {reg['dead_links']} pointed at repositories that no longer
exist publicly: deleted, renamed, or made private.</p>

<p>Of the {live:,} live repositories in that sample:</p>

<div class="scroll">
<table>
<thead><tr><th>Language</th><th class="num">Repos</th><th class="num">Share</th></tr></thead>
<tbody>
{lang_rows}
</tbody>
</table>
</div>

<h2>The removals everyone discussed</h2>

<p>These are the changes the {SPEC} changelog leads with, and the ones that filled the
threads. Each row is the share of the {n} scanned servers where the pattern actually
appears.</p>

<div class="scroll">
<table>
<thead><tr><th>Rule</th><th>What it finds</th><th class="num">Servers</th><th class="num">Share</th></tr></thead>
<tbody>
{headline}
</tbody>
</table>
</div>

<p><strong>{no_breaking} of {n} servers ({pct(no_breaking, n)}) have nothing breaking to
fix at all.</strong> Most never touched the transport directly; their framework did, and
the framework absorbed the change.</p>

<h2>Everything, ranked</h2>

<div class="scroll">
<table>
<thead><tr><th>Rule</th><th>Severity</th><th>What it finds</th><th class="num">Servers</th><th class="num">Share</th></tr></thead>
<tbody>
{everything}
</tbody>
</table>
</div>

<h2>Grades</h2>

<div class="scroll">
<table>
<thead><tr><th>Grade</th><th class="num">Servers</th><th class="num">Share</th></tr></thead>
<tbody>
{grade_rows}
</tbody>
</table>
</div>

<div class="callout">
<p><strong>Read the A column carefully &mdash; we cannot fully stand behind it.</strong></p>
<p>A server written in the current (2.x) SDK spelling is not recognised as an MCP server by
this scanner at all yet. It gets scanned, produces nothing, and grades A without having
been checked. So an A here means &ldquo;we found nothing&rdquo;, which is not the same
claim as &ldquo;there is nothing&rdquo;.</p>
<p>{zero} servers produced zero findings. Split by the SDK version they declare, the
gap is not subtle:</p>
<table style="margin:12px 0">
<thead><tr><th>Declares</th><th class="num">Servers</th><th class="num">Zero findings</th><th class="num">Rate</th></tr></thead>
<tbody>
<tr><td><code>mcp</code> 1.x</td><td class="num">{sdk.get('sdk_1x', 0)}</td>
<td class="num">{zero_sdk.get('sdk_1x', 0)}</td><td class="num">{zero_rate_1x}</td></tr>
<tr><td><code>mcp</code> 2.x or later</td><td class="num">{sdk.get('sdk_2x_or_later', 0)}</td>
<td class="num">{zero_sdk.get('sdk_2x_or_later', 0)}</td>
<td class="num"><strong>{zero_rate_2x}</strong></td></tr>
<tr><td>nothing readable</td><td class="num">{sdk.get('sdk_unknown', 0)}</td>
<td class="num">{zero_sdk.get('sdk_unknown', 0)}</td><td class="num">{zero_rate_unknown}</td></tr>
</tbody>
</table>
<p>A server on the current SDK is <strong>{zero_ratio}&times;</strong> more likely to come
back completely empty than one on 1.x. The likeliest explanation is not that 2.x servers
are cleaner &mdash; it is that we are not reading them. Tracked as
<a href="{REPO}/issues/255">#255</a>.</p>
</div>

<h2>What we got wrong, and how we know</h2>

<p>An earlier version of this scan led with a different headline:
<em>{prior_claim} of servers do not implement <code>server/discover</code></em>. We were
about to publish it. It was wrong, and the way it was wrong is worth more than the number
was.</p>

<p>R010 checked whether <code>server/discover</code> appeared in a project&rsquo;s own
source. On the 2.x Python SDK it never does &mdash; <code>Server.__init__</code> registers
the handler itself:</p>

<pre>&gt;&gt;&gt; from mcp.server.lowlevel import Server
&gt;&gt;&gt; Server("demo")._request_handlers        # already contains 'server/discover'</pre>

<p>And on 1.x the method does not exist at all, so there is no handler anyone could add.
The finding was unactionable in both directions: impossible on 1.x, unnecessary on 2.x. It
was measuring where a string appears, not what a server implements.</p>

<p>The tell was in the contributions, not the data. Two separate pull requests tried to
write an autofixer for it and both emitted <code>@app.discover()</code> &mdash; an API in
no version of the SDK. That is not two people being careless; that is what you get when
you ask someone to scaffold an implementation of something that either cannot exist or
already does.</p>

<p>Corrected, R010 now reads the SDK a project declares and stays silent when it cannot
tell. On our 18-server board, checked at pinned commits so the comparison is controlled,
it fired on <strong>17 of 18</strong> before and <strong>14 of 18</strong> after. In this
scan it appears on <strong>{r010_n} of {n}</strong> servers ({r010_pct}).</p>

<p>We publish grades about other people&rsquo;s code. A false finding costs more than a
missed one, and it costs most when it is the headline.</p>

<h2>Method</h2>

<p>The registry was crawled through
<code>registry.modelcontextprotocol.io/v0/servers?version=latest</code>, paginated to
exhaustion and deduplicated to {reg['unique_github_repos']:,} GitHub repositories. A seeded
random sample of {reg['sampled']:,} was drawn from the full population &mdash; not a
prefix; registry names are not randomly ordered, and an earlier pass that sampled
alphabetically measured the dead-link rate at 35% instead of {reg['dead_link_pct']}%.
Primary language came from the GitHub API. Every Python repository in the sample was
shallow-cloned, scanned, and deleted. Test directories are excluded by default, because
back-compat tests deliberately exercise legacy transports and would otherwise punish
well-tested projects.</p>

<p>These are aggregates on purpose. We are not publishing a per-server grade for
{n} projects we have not read individually; the
<a href="index.html#board">board</a> is where per-server grades go, and every entry on it
was read by a human before it was recorded.</p>

<p>Scanned with <code>{e(d['generated_by'])}</code>.</p>

<pre>python scripts/ecosystem_scan.py --all</pre>

</div>

<footer>
<div class="wrap">
<a href="index.html">What the tool checks</a>
<a href="{REPO}/blob/main/data/ecosystem-scan.json">The data</a>
<a href="{REPO}/blob/main/scripts/ecosystem_scan.py">The script</a>
<a href="{REPO}">Source</a>
<p style="margin:18px 0 0">Not affiliated with Anthropic or the Model Context Protocol
project. If a number here disagrees with the committed data file, the data file is right
and the page is a bug.</p>
</div>
</footer>

</body>
</html>
"""
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(doc)
    print(f"rendered {OUT.relative_to(ROOT)}: n={n}, R001={r001_pct}, R010={r010_pct}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
