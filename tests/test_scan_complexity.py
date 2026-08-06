"""A guard against #67 coming back.

#67 was a real O(n**2): R015's TypeScript path re-ran two `search_wire`
scans of the whole project inside its per-file loop. #70 hoisted them out
and measured 63.0 ms -> 3.1 ms at 200 files, a 20x speedup.

Nothing stopped it from returning. The rule interface makes it easy to do
by accident -- `project.search_*` reads like a cheap accessor at the call
site, and inside a `for f in project.files` loop it is quadratic. There
are 21 rules and 14 of them carry a second language path, so there is a
lot of surface for someone to reintroduce it in good faith.

Of the three approaches floated in #86 -- an absolute time ceiling, a
ratio between two sizes, or counting `search_*` calls -- this counts the
calls, for the reason the issue gives: it is the only one that cannot
flake, and a flaky perf test in CI is worse than no test because people
learn to re-run it and then it catches nothing. The CI matrix is four
Python versions on shared runners, which is exactly where a wall-clock
budget goes bad.

What makes counting *exact* rather than a proxy here: `run_check` invokes
each rule once per language it declares, and every `search_*` method
already iterates all files internally. So a rule that scans correctly
issues **the same number of calls whether the project holds 20 files or
200** -- the count is a constant of the rule, not a function of project
size. A rule that scans per-file issues one call per file, and the count
moves with N. That is a difference in kind, not degree, so the assertion
needs no tolerance and no timing.

The instrumentation is test-only on purpose. Adding a counter to
`Project` would put bookkeeping in the hot path of the very thing being
measured, to serve a test; wrapping the methods here changes nothing that
ships.
"""
from __future__ import annotations

from collections import Counter

from mcp_migrate import cli
from mcp_migrate.rules import all_rules
from mcp_migrate.rules.base import Project, Rule

SEARCH_METHODS = ("search", "search_code", "search_wire")

SMALL, LARGE = 20, 200

# Captured once, at import, before any test can wrap them. Re-reading them
# with getattr inside the helper would wrap the previous wrapper when a
# test counts twice, and the second count would come out doubled.
_ORIGINAL_SEARCH = {name: getattr(Project, name) for name in SEARCH_METHODS}

# Trips several rules across both languages on purpose: a rule that finds
# nothing may return before reaching its per-file loop, and would then
# look linear no matter how it was written.
#
# `$I` substitution rather than str.format -- these bodies are full of
# literal braces.
TS_FILE = """\
import { Server } from "@modelcontextprotocol/sdk/server/index.js";
import { ListToolsRequestSchema } from "@modelcontextprotocol/sdk/types.js";
import { SSEServerTransport } from "@modelcontextprotocol/sdk/server/sse.js";

const server = new Server({ name: "demo-$I", version: "1.0.0" });

export async function handle(req, res) {
  const sessionId = req.headers["mcp-session-id"];
  server.setRequestHandler(ListToolsRequestSchema, async () => {
    return {
      jsonrpc: "2.0",
      id: req.id,
      result: { tools: [{ name: "b_tool" }, { name: "a_tool" }] },
    };
  });
  return { sessionId, method: "tasks/list" };
}
"""

PY_FILE = """\
from mcp.server.sse import SseServerTransport


def handle_$I(request):
    session_id = request.headers.get("Mcp-Session-Id")
    return {"session": session_id, "method": "tasks/list"}
"""


def _make_project(root, n):
    src = root / "src"
    src.mkdir(parents=True, exist_ok=True)
    for i in range(n):
        (src / f"mod{i}.ts").write_text(TS_FILE.replace("$I", str(i)), encoding="utf-8")
        (src / f"mod{i}.py").write_text(PY_FILE.replace("$I", str(i)), encoding="utf-8")
    return root


def _count_scans(monkeypatch, root, rules=None):
    """Run a full check over `root`, returning {rule_id: search_* calls}.

    `rules` is both the set instrumented *and* the set `run_check` runs --
    one list, used for both, so the two cannot drift apart. (They did while
    this was being written: patching only the executed set left every count
    at zero, and the guard passed on a rule it never measured.)

    Attribution needs no call stack: `run_check` runs one rule at a time,
    so a single "currently executing" marker is enough.
    """
    rules = list(rules if rules is not None else all_rules())
    counts: Counter = Counter()
    current = {"rule": None}

    for name, original in _ORIGINAL_SEARCH.items():
        def wrapper(self, *a, _original=original, **kw):
            if current["rule"] is not None:
                counts[current["rule"]] += 1
            return _original(self, *a, **kw)

        monkeypatch.setattr(Project, name, wrapper)

    instrumented = []
    for rule in rules:
        original_check = type(rule).check

        def checked(project, _rule=rule, _original=original_check):
            current["rule"] = _rule.id
            try:
                return _original(_rule, project)
            finally:
                current["rule"] = None

        # Bound per instance rather than patched onto the class: two rules
        # can share a base, and patching the class twice would nest the
        # wrappers and double-count.
        rule.check = checked
        instrumented.append(rule)

    monkeypatch.setattr(cli, "all_rules", lambda: instrumented)
    cli.run_check(root)
    return counts


def test_no_rule_scans_the_project_once_per_file(tmp_path, monkeypatch):
    """The #67 shape, caught exactly.

    A rule whose scan count grows with the file count is scanning inside a
    per-file loop. At 20 vs 200 files that is a 10x difference in issued
    scans, and every one of them walks every file.
    """
    small = _count_scans(monkeypatch, _make_project(tmp_path / "small", SMALL))
    large = _count_scans(monkeypatch, _make_project(tmp_path / "large", LARGE))

    grew = {
        rule_id: f"{small[rule_id]} -> {large[rule_id]}"
        for rule_id in set(small) | set(large)
        if large[rule_id] > small[rule_id]
    }

    assert not grew, (
        "these rules issue more whole-project scans as the project grows, "
        f"which is the O(n**2) shape from #67 -- hoist the scan out of the "
        f"per-file loop: {grew}"
    )


def test_the_guard_would_have_caught_issue_67(tmp_path, monkeypatch):
    """The test's own regression test.

    A guard that silently stops guarding is worse than none, so this
    reintroduces the #67 pattern in a throwaway rule and asserts the
    counter notices. Without it, a refactor that broke attribution would
    leave the suite green and the protection gone.
    """

    class QuadraticRule(Rule):
        id = "R999"
        title = "deliberately quadratic, for the guard's own test"
        languages = ("typescript",)

        def check(self, project):
            for _f in project.files:
                list(project.search_wire(r"tasks/list"))  # <- the #67 shape
            return []

    small = _count_scans(
        monkeypatch, _make_project(tmp_path / "small", SMALL), rules=[QuadraticRule()],
    )
    large = _count_scans(
        monkeypatch, _make_project(tmp_path / "large", LARGE), rules=[QuadraticRule()],
    )

    assert small["R999"] == SMALL
    assert large["R999"] == LARGE
    assert large["R999"] > small["R999"], "the guard failed to notice a quadratic rule"


def test_a_linear_rule_passes_the_guard(tmp_path, monkeypatch):
    """The other half: the guard must not flag correct code.

    A rule that hoists its scan out of the loop -- the shape #70 changed
    R015 into -- issues the same count at both sizes.
    """

    class LinearRule(Rule):
        id = "R998"
        title = "correctly hoisted, for the guard's own test"
        languages = ("typescript",)

        def check(self, project):
            hits = list(project.search_wire(r"tasks/list"))  # hoisted
            for _f in project.files:
                _ = hits
            return []

    small = _count_scans(
        monkeypatch, _make_project(tmp_path / "small", SMALL), rules=[LinearRule()],
    )
    large = _count_scans(
        monkeypatch, _make_project(tmp_path / "large", LARGE), rules=[LinearRule()],
    )

    assert small["R998"] == large["R998"] == 1


def test_scan_counts_are_deterministic(tmp_path, monkeypatch):
    """Two runs over the same tree count identically.

    The property that makes this safe in CI: it depends on nothing but the
    code, so it cannot flake on a slow or loaded runner the way a
    wall-clock budget would.
    """
    root = _make_project(tmp_path / "repeat", SMALL)
    assert _count_scans(monkeypatch, root) == _count_scans(monkeypatch, root)


def test_the_fixture_actually_exercises_the_rules(tmp_path):
    """A rule that returns early never reaches its per-file loop.

    If the fixture stopped tripping anything, the guard above would pass
    over a project where nothing was measured -- green, and worthless.
    """
    _project, _rules, findings, _value, _grade = cli.run_check(
        _make_project(tmp_path / "live", SMALL)
    )
    assert len({f.rule_id for f in findings}) >= 3, (
        "the synthetic project must trip several rules, or the guard "
        "measures rules that returned early"
    )
