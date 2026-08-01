#!/usr/bin/env python3
"""Measure the MCP ecosystem against the 2026-07-28 spec, reproducibly.

Produces `data/ecosystem-scan.json`. Every number this project publishes
about other people's code has to be re-derivable by someone who doesn't
trust us, so the whole pipeline lives here rather than in a notebook:

    crawl     every GitHub-hosted server in the official registry
    sample    a seeded random subset (NOT a prefix -- see below)
    languages ask GitHub what each repo is written in
    scan      shallow-clone each Python repo, run the scanner, delete it
    aggregate collapse to the published counts

Run the whole thing:

    python scripts/ecosystem_scan.py --all

Stages cache into --work (default .ecosystem-work/) and are resumable, so
a dropped connection costs one stage rather than the run.

Two things that will bite you if you rewrite this:

- Crawl with `version=latest`. Without it the API paginates over server
  *versions*, not servers: 195 pages instead of ~80, for the same data.
- Sample randomly from the full deduplicated population. An earlier pass
  measured an alphabetical prefix and got a 15.3% -> 35% error in the
  dead-link rate. Registry names are not randomly ordered.
"""
from __future__ import annotations

import argparse
import json
import os
import random
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

REGISTRY = "https://registry.modelcontextprotocol.io/v0/servers?limit=100&version=latest"
GITHUB_API = "https://api.github.com/repos/{slug}"
ROOT = Path(__file__).resolve().parent.parent


def _get(url: str, headers: dict | None = None, tries: int = 6):
    last = None
    for i in range(tries):
        try:
            req = urllib.request.Request(url, headers=headers or {})
            req.add_header("User-Agent", "mcp-migrate-ecosystem-scan")
            with urllib.request.urlopen(req, timeout=60) as r:
                return json.load(r)
        except urllib.error.HTTPError as e:
            if e.code == 404:
                return None
            last = e
            time.sleep(min(2 ** i, 30))
        except Exception as e:
            last = e
            time.sleep(min(2 ** i, 30))
    raise RuntimeError(f"gave up on {url}: {last}")


# --- stages --------------------------------------------------------------

def crawl(work: Path) -> list[str]:
    """Every unique owner/name the registry points at on GitHub."""
    out = work / "repos.json"
    if out.exists():
        return json.loads(out.read_text())

    state = work / "crawl_state.json"
    repos, cursor, pages = set(), None, 0
    if state.exists():
        s = json.loads(state.read_text())
        repos, cursor, pages = set(s["repos"]), s["cursor"], s["pages"]

    while True:
        url = REGISTRY + (f"&cursor={urllib.parse.quote(cursor)}" if cursor else "")
        d = _get(url)
        for entry in d.get("servers", []):
            r = (entry.get("server") or {}).get("repository") or {}
            if r.get("source") != "github" or not r.get("url"):
                continue
            parts = r["url"].rstrip("/").replace("https://github.com/", "").split("/")
            if len(parts) >= 2:
                repos.add(f"{parts[0]}/{parts[1]}")
        pages += 1
        cursor = (d.get("metadata") or {}).get("nextCursor")
        if pages % 5 == 0 or not cursor:
            state.write_text(json.dumps(
                {"repos": sorted(repos), "cursor": cursor, "pages": pages}))
            print(f"  crawl: page {pages}, {len(repos)} repos", flush=True)
        if not cursor:
            break

    out.write_text(json.dumps(sorted(repos)))
    return sorted(repos)


def draw_sample(work: Path, repos: list[str], size: int, seed: int) -> list[str]:
    out = work / "sample.json"
    if out.exists():
        return json.loads(out.read_text())
    rng = random.Random(seed)
    sample = sorted(rng.sample(repos, min(size, len(repos))))
    out.write_text(json.dumps(sample))
    return sample


def languages(work: Path, slugs: list[str]) -> dict[str, str]:
    """Primary language per repo. '__gone__' means GitHub returned 404."""
    out = work / "languages.json"
    done = json.loads(out.read_text()) if out.exists() else {}
    todo = [s for s in slugs if s not in done]
    if not todo:
        return done

    headers = {"Accept": "application/vnd.github+json"}
    token = os.environ.get("GITHUB_TOKEN")
    if token:
        headers["Authorization"] = f"Bearer {token}"
    else:
        print("  note: no GITHUB_TOKEN set -- 60 requests/hour, this will crawl",
              file=sys.stderr)

    def one(slug):
        d = _get(GITHUB_API.format(slug=slug), headers)
        return slug, ("__gone__" if d is None else (d.get("language") or "(none)"))

    with ThreadPoolExecutor(max_workers=8) as ex:
        for i, (slug, lang) in enumerate(ex.map(one, todo), 1):
            done[slug] = lang
            if i % 100 == 0:
                out.write_text(json.dumps(done))
                print(f"  languages: {i}/{len(todo)}", flush=True)
    out.write_text(json.dumps(done))
    return done


def scan(work: Path, slugs: list[str], binary: str) -> dict[str, dict]:
    """Clone, scan, delete. Never keeps more than a few repos on disk."""
    out = work / "scans.json"
    done = json.loads(out.read_text()) if out.exists() else {}
    todo = [s for s in slugs if s not in done]
    tmp = work / "clones"
    tmp.mkdir(exist_ok=True)

    def one(slug):
        d = tmp / slug.replace("/", "__")
        shutil.rmtree(d, ignore_errors=True)
        try:
            p = subprocess.run(
                ["git", "clone", "--depth", "1", "-q",
                 f"https://github.com/{slug}", str(d)],
                capture_output=True, text=True, timeout=180)
            if p.returncode != 0:
                return slug, {"error": "clone_failed"}
            p = subprocess.run([binary, "check", str(d), "--json"],
                               capture_output=True, text=True, timeout=300)
            if not p.stdout.strip():
                return slug, {"error": "no_output"}
            data = json.loads(p.stdout)
            return slug, {
                "scannable": data.get("scannable"),
                "grade": data.get("grade"),
                "score": data.get("score"),
                "files": data.get("files_scanned"),
                "findings": [{"rule": f["rule"], "severity": f["severity"],
                              "location": f["location"]}
                             for f in data.get("findings", [])],
            }
        except subprocess.TimeoutExpired:
            return slug, {"error": "timeout"}
        except Exception as e:  # noqa: BLE001
            return slug, {"error": "exception", "detail": str(e)[:200]}
        finally:
            shutil.rmtree(d, ignore_errors=True)

    with ThreadPoolExecutor(max_workers=6) as ex:
        for i, (slug, row) in enumerate(ex.map(one, todo), 1):
            done[slug] = row
            if i % 25 == 0:
                out.write_text(json.dumps(done))
                print(f"  scan: {i}/{len(todo)}", flush=True)
    out.write_text(json.dumps(done))
    return done


def aggregate(repos, sample, langs, scans, seed, scanner_version) -> dict:
    in_sample = {s: langs[s] for s in sample if s in langs}
    n = len(in_sample)
    gone = sum(1 for v in in_sample.values() if v == "__gone__")
    live = {s: v for s, v in in_sample.items() if v != "__gone__"}

    ok = {k: v for k, v in scans.items() if v.get("scannable")}
    rule_counts = Counter()
    for v in ok.values():
        for r in {f["rule"] for f in v["findings"]}:
            rule_counts[r] += 1

    return {
        "generated_by": f"scripts/ecosystem_scan.py, mcp-migrate {scanner_version}",
        "spec": "2026-07-28",
        "method": {
            "registry": "registry.modelcontextprotocol.io/v0/servers?version=latest",
            "sample_seed": seed,
            "sample_size": len(sample),
            "note": "Random sample of the full deduplicated population, "
                    "not a prefix -- registry names are not randomly ordered.",
            "tests_excluded": True,
        },
        "registry": {
            "unique_github_repos": len(repos),
            "sampled": n,
            "dead_links": gone,
            "dead_link_pct": round(100 * gone / n, 1) if n else None,
            "live": len(live),
        },
        "languages_of_live_sample": dict(Counter(live.values()).most_common()),
        "python_servers_scanned": len(ok),
        "grades": {g: sum(1 for v in ok.values() if v["grade"] == g) for g in "ABCDF"},
        "score_median": (sorted(v["score"] for v in ok.values())[len(ok) // 2]
                         if ok else None),
        "zero_findings": sum(1 for v in ok.values() if not v["findings"]),
        "no_breaking_findings": sum(
            1 for v in ok.values()
            if not any(f["severity"] == "breaking" for f in v["findings"])),
        "rule_prevalence": {
            r: {"servers": c, "pct": round(100 * c / len(ok), 1)}
            for r, c in sorted(rule_counts.items(), key=lambda kv: -kv[1])
        } if ok else {},
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--all", action="store_true", help="run every stage")
    ap.add_argument("--sample", type=int, default=3000)
    ap.add_argument("--seed", type=int, default=20260801)
    ap.add_argument("--work", default=str(ROOT / ".ecosystem-work"))
    ap.add_argument("--binary", default="mcp-migrate",
                    help="the mcp-migrate to scan with")
    ap.add_argument("--out", default=str(ROOT / "data" / "ecosystem-scan.json"))
    args = ap.parse_args()

    work = Path(args.work)
    work.mkdir(parents=True, exist_ok=True)

    print("crawling registry...", flush=True)
    repos = crawl(work)
    print(f"  {len(repos)} unique GitHub repos", flush=True)

    sample = draw_sample(work, repos, args.sample, args.seed)
    print(f"sample: {len(sample)} (seed {args.seed})", flush=True)

    print("resolving languages...", flush=True)
    langs = languages(work, sample)

    python = sorted(s for s in sample if langs.get(s) == "Python")
    print(f"scanning {len(python)} Python repos...", flush=True)
    scans = scan(work, python, args.binary)

    version = subprocess.run([args.binary, "--version"], capture_output=True,
                             text=True).stdout.strip() or "unknown"
    data = aggregate(repos, sample, langs, scans, args.seed, version)

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(data, indent=2) + "\n")
    print(f"\nwrote {out}")
    print(json.dumps(data["registry"], indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
