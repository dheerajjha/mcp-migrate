"""`fix` only touches files `check` flags (#336).

A fixer used to see every file and decide for itself, so every precision gate
its rule had (MCP context, exclusions, suppressions) was invisible to it.
The issue's case: R014's rule stays silent on an ordinary browser EventSource
route beside an MCP server, but R014's fixer commented out the route's
`Last-Event-ID` read anyway, leaving the next line using an undefined name.

`run_fix` now runs the selected fixers' rules first and hands each fixer only
the files its rule flags. These tests drive `run_fix` / `main` rather than
`Fixer.fix`, because the string-level fixer tests bypass the gate entirely.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from mcp_migrate.cli import main, run_check_detailed, run_fix
from mcp_migrate.rules import all_rules

FIXTURES = Path(__file__).parent / "fixtures"

FASTMCP_SERVER = '''from mcp.server.fastmcp import FastMCP

mcp = FastMCP("demo")


@mcp.tool()
def echo(text: str) -> str:
    return text
'''

# The shape from #336, written fresh rather than copied from the real repo:
# a Starlette SSE route that reads the header for its own replay cursor, in a
# file with no MCP surface. The next line still uses `marker`, so commenting
# the read out breaks the route.
CHAT_ROUTE_PY = '''from starlette.requests import Request
from starlette.responses import StreamingResponse


async def chat_events(request: Request):
    marker = request.headers.get("last-event-id")
    return StreamingResponse(stream_after(marker), media_type="text/event-stream")
'''

CHAT_ROUTE_TS = '''export async function chatEvents(req: Request, res: Response) {
  const marker = req.headers["last-event-id"] ?? "";
  res.write(streamAfter(marker));
}
'''

# A real MCP SSE resume handler: same header read, MCP surface in the file.
MCP_RESUME_HANDLER = '''from mcp.server import Server

server = Server("demo")


async def resume(request):
    cursor = request.headers.get("Last-Event-ID")
    return cursor
'''


def _write(root: Path, files: dict[str, str]) -> None:
    for name, text in files.items():
        (root / name).write_text(text)


def _changed(results) -> dict[str, set[str]]:
    return {str(f.path): {fx.rule_id for fx, _ in changes} for f, _, changes in results}


@pytest.mark.parametrize("route_name, route_src", [
    ("routes.py", CHAT_ROUTE_PY),
    ("routes.ts", CHAT_ROUTE_TS),
], ids=["python", "typescript"])
def test_r014_fixer_leaves_a_file_check_does_not_flag_alone(tmp_path, capsys, route_name, route_src):
    """#336: `check` reports nothing in the route, so `fix` must not edit it."""
    _write(tmp_path, {"server.py": FASTMCP_SERVER, route_name: route_src})

    check = run_check_detailed(tmp_path, rule_ids=frozenset({"R014"}))
    assert not check.findings, "precondition: R014's rule is silent on the route"

    _, _, results = run_fix(tmp_path, rule_ids=frozenset({"R014"}))
    assert route_name not in _changed(results)

    assert main(["fix", str(tmp_path), "--rule", "R014", "--write"]) == 0
    assert "Nothing to fix" in capsys.readouterr().out
    assert (tmp_path / route_name).read_text() == route_src


def test_r014_fixer_still_rewrites_a_file_check_flags(tmp_path):
    """The gate is not "never fix": the same header read with MCP surface in
    its file is a finding, and the fixer still repairs it."""
    _write(tmp_path, {"resume.py": MCP_RESUME_HANDLER, "routes.py": CHAT_ROUTE_PY})

    check = run_check_detailed(tmp_path, rule_ids=frozenset({"R014"}))
    assert {str(f.path) for f in check.findings} == {"resume.py"}

    main(["fix", str(tmp_path), "--rule", "R014", "--write"])

    fixed = (tmp_path / "resume.py").read_text()
    assert '# cursor = request.headers.get("Last-Event-ID")' in fixed
    assert "TODO(mcp-migrate)" in fixed
    assert (tmp_path / "routes.py").read_text() == CHAT_ROUTE_PY


def test_a_suppressed_finding_keeps_the_fixer_off_the_file(tmp_path, capsys):
    """`ignore[R014]` means "leave this line alone"; with no other R014
    finding in the file, nothing opens the gate."""
    src = MCP_RESUME_HANDLER.replace(
        'cursor = request.headers.get("Last-Event-ID")',
        'cursor = request.headers.get("Last-Event-ID")  '
        "# mcp-migrate: ignore[R014]: proxied through to an upstream, not our resume cursor",
    )
    _write(tmp_path, {"resume.py": src})

    check = run_check_detailed(tmp_path, rule_ids=frozenset({"R014"}))
    assert not check.findings
    assert [f.rule_id for f in check.suppressed] == ["R014"]

    main(["fix", str(tmp_path), "--write"])

    assert "Nothing to fix" in capsys.readouterr().out
    assert (tmp_path / "resume.py").read_text() == src


# R007 (Roots deprecated) and R018 (server-initiated roots/list replaced)
# both fire here, and `overlap.dedupe()` folds every R007 finding into R018's,
# so the report shows R018 alone. Both rules have fixers.
OVERLAP_SERVER = '''from mcp.server.lowlevel import Server
from mcp.types import ListRootsResult, RootsCapability

server = Server("demo")
caps = RootsCapability()


async def roots(session) -> ListRootsResult:
    return await session.list_roots()
'''


def test_the_overlap_pair_keeps_both_fixers(tmp_path):
    """The gate reads findings before dedupe. Gating on the merged report
    would silently retire R007's fixer here, since the report shows no R007."""
    _write(tmp_path, {"server.py": OVERLAP_SERVER})

    report = run_check_detailed(tmp_path).findings
    assert "R018" in {f.rule_id for f in report}
    assert "R007" not in {f.rule_id for f in report}, "precondition: dedupe folded R007 away"

    _, _, both = run_fix(tmp_path, rule_ids=frozenset({"R007", "R018"}))
    assert "R007" in _changed(both)["server.py"]

    _, _, r018_only = run_fix(tmp_path, rule_ids=frozenset({"R018"}))
    assert _changed(r018_only)["server.py"] == {"R018"}


OTEL_SERVER = '''from opentelemetry import trace

tracer = trace.get_tracer(__name__)


def handle():
    with tracer.start_as_current_span("handle"):
        return 1
'''

# A span start with no `@opentelemetry/...` import: R008's TypeScript side
# has nothing to fire on, whatever the Python side says.
TS_SPAN = '''export function handle(tracer: any) {
  return tracer.startActiveSpan("handle", (span: any) => span.end());
}
'''


def test_a_project_level_finding_opens_the_gate_for_its_language(tmp_path):
    """R008 is project-level ("OpenTelemetry is used, traceparent is read
    nowhere" names no file), but its fixer edits the span sites. Its finding
    opens the gate for the language that produced it, and only that one."""
    _write(tmp_path, {"server.py": OTEL_SERVER, "client.ts": TS_SPAN})

    findings = run_check_detailed(tmp_path, rule_ids=frozenset({"R008"})).findings
    assert [(f.rule_id, f.path) for f in findings] == [("R008", None)]

    _, _, results = run_fix(tmp_path, rule_ids=frozenset({"R008"}))
    assert _changed(results) == {"server.py": {"R008"}}


def test_no_project_level_finding_means_no_project_level_fix(tmp_path):
    """Before #336 the R008 fixer annotated span starts even in a project that
    already reads traceparent, where `check` has nothing to say."""
    reads_it = OTEL_SERVER + '\n\ndef meta(m):\n    traceparent = m.get("traceparent")\n    return traceparent\n'
    _write(tmp_path, {"server.py": reads_it})

    assert not run_check_detailed(tmp_path, rule_ids=frozenset({"R008"})).findings
    _, _, results = run_fix(tmp_path, rule_ids=frozenset({"R008"}))
    assert results == []


# ---------------------------------------------------------------------------
# The property: every (rule, file) `fix` changes is one `check` flags.
# ---------------------------------------------------------------------------

LANGUAGES = {r.id: set(r.languages) for r in all_rules()}
FIXTURE_DIRS = sorted(p for p in FIXTURES.iterdir() if p.is_dir() and not p.name.startswith("__"))


def _check_flags(root: Path, rule_id: str, path: Path, language: str, include_tests: bool) -> bool:
    # One rule at a time, so dedupe has no pair partner to merge it into and
    # what comes back is exactly "did this rule fire here", post-suppression.
    findings = run_check_detailed(root, include_tests=include_tests, rule_ids=frozenset({rule_id})).findings
    return any(
        f.path == path or (f.path is None and language in LANGUAGES[rule_id])
        for f in findings
    )


@pytest.mark.parametrize("include_tests", [False, True])
@pytest.mark.parametrize("root", FIXTURE_DIRS, ids=lambda p: p.name)
def test_fix_never_changes_a_file_for_a_rule_check_does_not_flag(root, include_tests):
    """Catches any future drift between a fixer and its rule, on the corpus
    this repo already maintains."""
    _, _, results = run_fix(root, include_tests=include_tests)
    for f, _, changes in results:
        for rule_id in {fx.rule_id for fx, _ in changes}:
            assert _check_flags(root, rule_id, f.path, f.language, include_tests), (
                f"{rule_id}'s fixer changed {f.path} but `check` has no {rule_id} finding there"
            )
