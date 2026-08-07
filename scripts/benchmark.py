#!/usr/bin/env python3
"""Wall-clock throughput on a generated tree. Run by hand -- see #185.

`tests/test_scan_complexity.py` guards the shape of the cost (does a rule
scan once per project or once per file); it deliberately says nothing
about seconds, because a wall-clock assertion on a shared CI runner just
flakes and gets deleted. This is the other half: a number a human can
read, and a contributor can diff their branch against `main` with.

Three phases, timed separately because they have different costs:

    walk   languages.survey() -- os.walk with SKIP_DIRS pruning
    load   scan.load_project() -- read + (for Python) ast.parse every file
    rules  every rule against the loaded Project, same loop as `cli.run_check`

Usage:

    python scripts/benchmark.py
    python scripts/benchmark.py --files 5000 --node-modules 20000
"""
from __future__ import annotations

import argparse
import random
import sys
import time
from pathlib import Path
from tempfile import TemporaryDirectory

from rich.console import Console
from rich.table import Table

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from mcp_migrate import languages, scan  # noqa: E402
from mcp_migrate.rules import all_rules  # noqa: E402

# Same shapes as tests/test_scan_complexity.py's fixture: content that
# actually trips rules, not empty files. A rule that returns before
# reaching its per-file loop looks free no matter how it's written, and
# that would make the "rules" phase measure nothing.
TS_FILE = """\
import {{ Server }} from "@modelcontextprotocol/sdk/server/index.js";
import {{ ListToolsRequestSchema }} from "@modelcontextprotocol/sdk/types.js";
import {{ SSEServerTransport }} from "@modelcontextprotocol/sdk/server/sse.js";

const server = new Server({{ name: "demo-{i}", version: "1.0.0" }});

export async function handle{i}(req, res) {{
  const sessionId = req.headers["mcp-session-id"];
  server.setRequestHandler(ListToolsRequestSchema, async () => {{
    return {{
      jsonrpc: "2.0",
      id: req.id,
      result: {{ tools: [{{ name: "b_tool" }}, {{ name: "a_tool" }}] }},
    }};
  }});
  return {{ sessionId, method: "tasks/list" }};
}}
{filler}
"""

PY_FILE = """\
from mcp.server.sse import SseServerTransport


def handle_{i}(request):
    session_id = request.headers.get("Mcp-Session-Id")
    return {{"session": session_id, "method": "tasks/list"}}
{filler}
"""

# A realistic tree isn't uniform: mostly small files, a handful of large
# ones. Weights roughly mirror what `ecosystem_scan.py` sees in the wild.
SIZE_MIX = [(20, 0.70), (100, 0.25), (500, 0.05)]


def _filler(rng: random.Random, lines: int, comment: str) -> str:
    return "\n".join(f"{comment} line {n}" for n in range(lines))


def _pick_size(rng: random.Random) -> int:
    r = rng.random()
    upto = 0.0
    for lines, weight in SIZE_MIX:
        upto += weight
        if r <= upto:
            return lines
    return SIZE_MIX[-1][0]


def generate_tree(root: Path, n_files: int, n_node_modules: int, seed: int) -> None:
    rng = random.Random(seed)
    src = root / "src"
    src.mkdir(parents=True, exist_ok=True)
    for i in range(n_files):
        lines = _pick_size(rng)
        if i % 2 == 0:
            body = TS_FILE.format(i=i, filler=_filler(rng, lines, "//"))
            (src / f"mod{i}.ts").write_text(body, encoding="utf-8")
        else:
            body = PY_FILE.format(i=i, filler=_filler(rng, lines, "#"))
            (src / f"mod{i}.py").write_text(body, encoding="utf-8")

    if n_node_modules:
        vendor = root / "node_modules" / "some-package" / "dist"
        vendor.mkdir(parents=True, exist_ok=True)
        for i in range(n_node_modules):
            (vendor / f"chunk{i}.js").write_text(
                f"module.exports.chunk{i} = () => {i};\n", encoding="utf-8"
            )


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--files", type=int, default=1000,
                    help="real source files to generate (default: 1000)")
    ap.add_argument("--node-modules", type=int, default=5000,
                    help="extra vendored .js files under node_modules, to show what "
                         "survey()'s os.walk pruning is worth (default: 5000, 0 to skip)")
    ap.add_argument("--seed", type=int, default=20260807)
    args = ap.parse_args()

    console = Console()

    with TemporaryDirectory(prefix="mcp-migrate-bench-") as tmp:
        root = Path(tmp)
        console.print(
            f"generating {args.files} source files"
            + (f" + {args.node_modules} vendored" if args.node_modules else "")
            + f" (seed {args.seed})...", style="dim"
        )
        generate_tree(root, args.files, args.node_modules, args.seed)

        table = Table(title=f"benchmark: {args.files} files, "
                             f"{args.node_modules} node_modules")
        table.add_column("phase")
        table.add_column("wall-clock", justify="right")
        table.add_column("files/sec", justify="right")

        t0 = time.perf_counter()
        counts = languages.survey(root)
        t_walk = time.perf_counter() - t0
        walked = sum(counts.values())
        table.add_row("walk", f"{t_walk:.3f}s", f"{walked / t_walk:,.0f}")

        t0 = time.perf_counter()
        project = scan.load_project(root)
        t_load = time.perf_counter() - t0
        table.add_row("load", f"{t_load:.3f}s", f"{len(project.files) / t_load:,.0f}")

        rules = list(all_rules())
        t0 = time.perf_counter()
        views: dict[str, object] = {}
        findings = []
        for rule in rules:
            for language in rule.languages:
                if language not in views:
                    views[language] = project.for_language(language)
                view = views[language]
                if view.files:
                    findings.extend(rule.check(view))
        t_rules = time.perf_counter() - t0
        table.add_row("rules", f"{t_rules:.3f}s", f"{len(project.files) / t_rules:,.0f}")

        table.add_row("total", f"{t_walk + t_load + t_rules:.3f}s", "")

        console.print(table)
        console.print(
            f"{len(rules)} rules, {len(findings)} findings, "
            f"{walked} files walked, {len(project.files)} files loaded (non-test, "
            f"Python/TypeScript)", style="dim"
        )

    return 0


if __name__ == "__main__":
    sys.exit(main())
