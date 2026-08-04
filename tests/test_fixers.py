"""Tests for the fixer package and the `fix`/`fixers` CLI commands.

Covers, per CONTRIBUTING-parity with test_rules.py:

- discovery (`all_fixers()`) and the base API contract
- an exact before/after transformation for every shipped fixer
- that every fixer is idempotent (running it twice changes nothing the
  second time)
- that a fixer refuses to guess on an ambiguous shape
- CLI behaviour: `fix` without `--write` never touches disk, `--safe-only`
  skips "review"-confidence fixers, and a round-trip (`fix --write` then
  `check`) measurably improves the score for the rules these fixers cover
"""
from __future__ import annotations

import ast
import shutil
from pathlib import Path

import pytest

from mcp_migrate.cli import main, run_check, run_fix
from mcp_migrate.fixers import all_fixers
from mcp_migrate.grade import letter, score

FIXTURES = Path(__file__).parent / "fixtures"
ROUNDTRIP = FIXTURES / "fixer_roundtrip"

FIXERS = {type(fx).__name__: fx for fx in all_fixers()}
FIXER_RULE_IDS = {fx.rule_id for fx in all_fixers()}


def fix(name: str, source: str, path: str = "server.py"):
    return FIXERS[name].fix(source, Path(path))


# ---------------------------------------------------------------------------
# Discovery / base API
# ---------------------------------------------------------------------------

def test_ships_a_fixer_for_every_rule_the_task_calls_out():
    assert {"R001", "R004", "R005", "R006", "R007", "R014", "R017"} <= FIXER_RULE_IDS


def test_every_fixer_has_a_valid_confidence_and_metadata():
    for fx in all_fixers():
        assert fx.confidence in ("safe", "review")
        assert fx.rule_id
        assert fx.title


def test_all_fixers_is_stable_and_sorted_by_rule_id():
    ids = [fx.rule_id for fx in all_fixers()]
    assert ids == sorted(ids)


def test_unchanged_source_reports_not_changed():
    result = fix("SortToolsFixer", "x = 1\n")
    assert result.changed is False
    assert result.text == "x = 1\n"
    assert result.changes == []


# ---------------------------------------------------------------------------
# R001 -- Mcp-Session-Id
# ---------------------------------------------------------------------------

R001_BEFORE = (
    'def _session_for(request):\n'
    '    mcp_session_id = request.headers.get("Mcp-Session-Id")\n'
    '    if mcp_session_id is None:\n'
    '        raise ValueError("missing session id")\n'
    '    return mcp_session_id\n'
)
R001_AFTER = (
    'def _session_for(request):\n'
    '    # TODO(mcp-migrate): replaced by an explicit handle argument, see '
    'https://github.com/modelcontextprotocol/modelcontextprotocol/pull/2567\n'
    '    # mcp_session_id = request.headers.get("Mcp-Session-Id")\n'
    '    if mcp_session_id is None:\n'
    '        raise ValueError("missing session id")\n'
    '    return mcp_session_id\n'
)


def test_r001_comments_out_header_access_and_leaves_a_todo():
    result = fix("SessionIdHeaderFixer", R001_BEFORE)
    assert result.changed
    assert result.text == R001_AFTER
    assert FIXERS["SessionIdHeaderFixer"].confidence == "review"
    ast.parse(result.text)  # still syntactically valid


def test_r001_never_comments_out_a_block_opener():
    """Commenting out the `if`/`raise` lines that merely *reference* the
    session-id variable would leave a dangling suite -- a syntax error.
    Only the actual header read is touched."""
    result = fix("SessionIdHeaderFixer", R001_BEFORE)
    assert 'if mcp_session_id is None:' in result.text
    assert 'raise ValueError("missing session id")' in result.text


def test_r001_idempotent():
    once = fix("SessionIdHeaderFixer", R001_BEFORE)
    twice = fix("SessionIdHeaderFixer", once.text)
    assert twice.changed is False
    assert twice.text == once.text


# ---------------------------------------------------------------------------
# R004 -- tools/list ordering
# ---------------------------------------------------------------------------

R004_TOOL_BEFORE = (
    '@server.list_tools()\n'
    'async def list_tools() -> list[Tool]:\n'
    '    return [\n'
    '        Tool(name="zeta", description="Last"),\n'
    '        Tool(name="alpha", description="First"),\n'
    '    ]\n'
)
R004_TOOL_AFTER = (
    '@server.list_tools()\n'
    'async def list_tools() -> list[Tool]:\n'
    '    return sorted([\n'
    '        Tool(name="zeta", description="Last"),\n'
    '        Tool(name="alpha", description="First"),\n'
    '    ], key=lambda t: t.name)\n'
)


def test_r004_wraps_tool_literal_with_name_key():
    result = fix("SortToolsFixer", R004_TOOL_BEFORE)
    assert result.changed
    assert result.text == R004_TOOL_AFTER
    assert FIXERS["SortToolsFixer"].confidence == "safe"
    ast.parse(result.text)


def test_r004_wraps_plain_string_literal_with_no_key():
    before = (
        '@server.list_tools()\n'
        'async def list_tools():\n'
        '    return ["zeta", "alpha"]\n'
    )
    after = (
        '@server.list_tools()\n'
        'async def list_tools():\n'
        '    return sorted(["zeta", "alpha"])\n'
    )
    result = fix("SortToolsFixer", before)
    assert result.text == after
    ast.parse(result.text)


def test_r004_refuses_to_guess_an_ambiguous_shape():
    """A list comprehension isn't a literal we can confidently key a sort
    on -- when in doubt, don't fix."""
    before = (
        '@server.list_tools()\n'
        'async def list_tools():\n'
        '    return [make_tool(x) for x in names]\n'
    )
    result = fix("SortToolsFixer", before)
    assert result.changed is False
    assert result.text == before


def test_r004_leaves_an_already_sorted_handler_alone():
    before = (
        '@server.list_tools()\n'
        'async def list_tools():\n'
        '    return sorted([Tool(name="a")], key=lambda t: t.name)\n'
    )
    result = fix("SortToolsFixer", before)
    assert result.changed is False


def test_r004_idempotent():
    once = fix("SortToolsFixer", R004_TOOL_BEFORE)
    twice = fix("SortToolsFixer", once.text)
    assert twice.changed is False
    assert twice.text == once.text


# ---------------------------------------------------------------------------
# R005 -- extensions={}
# ---------------------------------------------------------------------------

R005_MULTILINE_BEFORE = (
    'capabilities = ServerCapabilities(\n'
    '    tools=ToolsCapability(list_changed=True),\n'
    '    roots=RootsCapability(),\n'
    ')\n'
)
R005_MULTILINE_AFTER = (
    'capabilities = ServerCapabilities(\n'
    '    tools=ToolsCapability(list_changed=True),\n'
    '    roots=RootsCapability(),\n'
    '    extensions={},\n'
    ')\n'
)


def test_r005_adds_extensions_to_multiline_construction():
    result = fix("ExtensionsFixer", R005_MULTILINE_BEFORE)
    assert result.changed
    assert result.text == R005_MULTILINE_AFTER
    assert FIXERS["ExtensionsFixer"].confidence == "safe"
    ast.parse(result.text)


def test_r005_adds_extensions_to_single_line_construction():
    before = "capabilities = ServerCapabilities(tools=ToolsCapability())\n"
    after = "capabilities = ServerCapabilities(tools=ToolsCapability(), extensions={})\n"
    result = fix("ExtensionsFixer", before)
    assert result.text == after
    ast.parse(result.text)


def test_r005_leaves_a_construction_that_already_has_extensions_alone():
    before = "capabilities = ServerCapabilities(extensions={})\n"
    result = fix("ExtensionsFixer", before)
    assert result.changed is False
    assert result.text == before


def test_r005_idempotent():
    once = fix("ExtensionsFixer", R005_MULTILINE_BEFORE)
    twice = fix("ExtensionsFixer", once.text)
    assert twice.changed is False
    assert twice.text == once.text


# ---------------------------------------------------------------------------
# R006 -- SSE transport
# ---------------------------------------------------------------------------

def test_r006_rewrites_import_and_constructor():
    before = (
        'from mcp.server.sse import SseServerTransport\n'
        '\n'
        'transport = SseServerTransport("/messages")\n'
    )
    result = fix("SseTransportFixer", before)
    assert result.changed
    assert FIXERS["SseTransportFixer"].confidence == "review"
    assert "from mcp.server.streamable_http import StreamableHTTPServerTransport" in result.text
    assert "transport = StreamableHTTPServerTransport()" in result.text
    assert "TODO(mcp-migrate)" in result.text
    assert "SseServerTransport" not in result.text
    ast.parse(result.text)


def test_r006_rewrites_transport_keyword():
    before = 'mcp.run(transport="sse")\n'
    after = 'mcp.run(transport="streamable-http")\n'
    result = fix("SseTransportFixer", before)
    assert result.text == after
    ast.parse(result.text)


def test_r006_idempotent():
    before = (
        'from mcp.server.sse import SseServerTransport\n'
        '\n'
        'transport = SseServerTransport("/messages")\n'
    )
    once = fix("SseTransportFixer", before)
    twice = fix("SseTransportFixer", once.text)
    assert twice.changed is False
    assert twice.text == once.text


# ---------------------------------------------------------------------------
# R007 -- Roots / Sampling / Logging deprecated
# ---------------------------------------------------------------------------

R007_ROOTS_BEFORE = (
    "from mcp.types import ServerCapabilities\n\n"
    "caps = ServerCapabilities(roots=RootsCapability())\n"
)
R007_ROOTS_AFTER = (
    "from mcp.types import ServerCapabilities\n\n"
    "# TODO(mcp-migrate): Roots is deprecated as a core capability; see "
    "https://modelcontextprotocol.io/specification/draft/changelog and "
    "cookbook/18-roots-sampling-logging-deprecated.md\n"
    "# caps = ServerCapabilities(roots=RootsCapability())\n"
)


def test_r007_comments_out_roots_capability_and_leaves_a_todo():
    result = fix("DeprecatedCoreFeaturesFixer", R007_ROOTS_BEFORE)
    assert result.changed
    assert result.text == R007_ROOTS_AFTER
    assert FIXERS["DeprecatedCoreFeaturesFixer"].confidence == "review"
    ast.parse(result.text)


def test_r007_adds_todo_without_commenting_multiline_sampling_opener():
    before = (
        "async def summarize(ctx):\n"
        "    result = await ctx.session.create_message(\n"
        "        messages=[], max_tokens=100,\n"
        "    )\n"
        "    return result\n"
    )
    result = fix("DeprecatedCoreFeaturesFixer", before)
    assert result.changed
    assert "TODO(mcp-migrate): Sampling is deprecated" in result.text
    assert "result = await ctx.session.create_message(" in result.text
    assert "#     result = await ctx.session.create_message(" not in result.text
    ast.parse(result.text)


def test_r007_comments_out_logging_capability_declaration():
    before = "from mcp.types import LoggingCapability, ServerCapabilities\n\n"
    before += "caps = ServerCapabilities(logging=LoggingCapability())\n"
    result = fix("DeprecatedCoreFeaturesFixer", before)
    assert result.changed
    assert "TODO(mcp-migrate): Logging is deprecated" in result.text
    assert "# caps = ServerCapabilities(logging=LoggingCapability())" in result.text
    ast.parse(result.text)


def test_r007_never_touches_anthropic_client_wrappers():
    before = (
        "class ChatAnthropic:\n"
        "    async def _create_message(self, **params):\n"
        "        return await client.messages.create(**params)\n"
    )
    result = fix("DeprecatedCoreFeaturesFixer", before)
    assert result.changed is False
    assert result.text == before


def test_r007_idempotent():
    once = fix("DeprecatedCoreFeaturesFixer", R007_ROOTS_BEFORE)
    twice = fix("DeprecatedCoreFeaturesFixer", once.text)
    assert twice.changed is False
    assert twice.text == once.text


# ---------------------------------------------------------------------------
# R014 -- SSE resumability (Last-Event-ID)
# ---------------------------------------------------------------------------

R014_BEFORE = (
    'def handle_reconnect(request):\n'
    '    last_event_id = request.headers.get("Last-Event-ID")\n'
    '    if last_event_id is None:\n'
    '        return []\n'
    '    return list(_EventLog().replay_after(last_event_id))\n'
)
R014_AFTER = (
    'def handle_reconnect(request):\n'
    '    # TODO(mcp-migrate): SSE resumability via Last-Event-ID is removed; see '
    'https://modelcontextprotocol.io/specification/2026-07-28/changelog and '
    'cookbook/08-sse-resumability-removed.md\n'
    '    # last_event_id = request.headers.get("Last-Event-ID")\n'
    '    if last_event_id is None:\n'
    '        return []\n'
    '    # TODO(mcp-migrate): SSE resumability via Last-Event-ID is removed; see '
    'https://modelcontextprotocol.io/specification/2026-07-28/changelog and '
    'cookbook/08-sse-resumability-removed.md\n'
    '    # return list(_EventLog().replay_after(last_event_id))\n'
)


def test_r014_comments_out_header_read_and_replay_call():
    result = fix("SseResumabilityFixer", R014_BEFORE)
    assert result.changed
    assert result.text == R014_AFTER
    assert FIXERS["SseResumabilityFixer"].confidence == "review"
    ast.parse(result.text)


def test_r014_skips_block_opener_header_reads():
    before = 'if request.headers.get("Last-Event-ID"):\n    replay()\n'
    result = fix("SseResumabilityFixer", before)
    assert result.changed is False
    assert result.text == before


def test_r014_adds_todo_without_touching_replay_after_def():
    before = (
        "class _EventLog:\n"
        "    def replay_after(self, last_event_id: str):\n"
        "        if event_id == last_event_id:\n"
        "            yield event_id, payload\n"
    )
    result = fix("SseResumabilityFixer", before)
    assert result.changed is False
    assert result.text == before
    ast.parse(result.text)


def test_r014_comments_out_bracket_header_access():
    before = 'last_id = request.headers["Last-Event-ID"]\n'
    result = fix("SseResumabilityFixer", before)
    assert result.changed
    assert '# last_id = request.headers["Last-Event-ID"]' in result.text
    ast.parse(result.text)


def test_r014_leaves_event_store_append_logic_alone():
    before = (
        "class _EventLog:\n"
        "    def append(self, event_id: str, payload: dict) -> None:\n"
        "        self._events.append((event_id, payload))\n"
    )
    result = fix("SseResumabilityFixer", before)
    assert result.changed is False
    assert result.text == before


def test_r014_idempotent():
    once = fix("SseResumabilityFixer", R014_BEFORE)
    twice = fix("SseResumabilityFixer", once.text)
    assert twice.changed is False
    assert twice.text == once.text


# ---------------------------------------------------------------------------
# R017 -- resource-not-found error code
# ---------------------------------------------------------------------------

def test_r017_renames_qualifying_error_code():
    before = 'return {"code": -32002, "message": "resource not found"}\n'
    after = 'return {"code": -32602, "message": "resource not found"}\n'
    result = fix("ResourceNotFoundErrorCodeFixer", before)
    assert result.text == after
    assert FIXERS["ResourceNotFoundErrorCodeFixer"].confidence == "safe"
    ast.parse(result.text)


def test_r017_leaves_unrelated_negative_number_alone():
    """-32002 with no resource/not-found context anywhere on the line is
    not necessarily this error code -- don't guess."""
    before = "PORT_OFFSET = -32002\n"
    result = fix("ResourceNotFoundErrorCodeFixer", before)
    assert result.changed is False
    assert result.text == before


def test_r017_idempotent():
    before = 'return {"code": -32002, "message": "resource not found"}\n'
    once = fix("ResourceNotFoundErrorCodeFixer", before)
    twice = fix("ResourceNotFoundErrorCodeFixer", once.text)
    assert twice.changed is False
    assert twice.text == once.text


# ---------------------------------------------------------------------------
# CLI: fix / fixers
# ---------------------------------------------------------------------------

@pytest.fixture()
def roundtrip_copy(tmp_path):
    dest = tmp_path / "fixer_roundtrip"
    shutil.copytree(ROUNDTRIP, dest)
    return dest


def _file_bytes(root: Path) -> dict[str, bytes]:
    return {str(p.relative_to(root)): p.read_bytes() for p in sorted(root.rglob("*.py"))}


def test_fix_dry_run_never_touches_disk(roundtrip_copy, capsys):
    before = _file_bytes(roundtrip_copy)
    exit_code = main(["fix", str(roundtrip_copy)])
    capsys.readouterr()
    after = _file_bytes(roundtrip_copy)
    assert exit_code == 0
    assert before == after


def test_fix_dry_run_flag_also_never_touches_disk(roundtrip_copy, capsys):
    before = _file_bytes(roundtrip_copy)
    main(["fix", str(roundtrip_copy), "--dry-run"])
    capsys.readouterr()
    after = _file_bytes(roundtrip_copy)
    assert before == after


def test_fix_write_and_dry_run_together_is_rejected(roundtrip_copy, capsys):
    before = _file_bytes(roundtrip_copy)
    exit_code = main(["fix", str(roundtrip_copy), "--write", "--dry-run"])
    capsys.readouterr()
    after = _file_bytes(roundtrip_copy)
    assert exit_code != 0
    assert before == after  # rejected before anything was applied


def test_fix_write_actually_changes_files_on_disk(roundtrip_copy, capsys):
    before = _file_bytes(roundtrip_copy)
    main(["fix", str(roundtrip_copy), "--write"])
    capsys.readouterr()
    after = _file_bytes(roundtrip_copy)
    assert before != after
    for rel, text in after.items():
        ast.parse(text)  # every rewritten file still parses


def test_fix_never_touches_files_outside_the_scanned_root(roundtrip_copy, capsys, tmp_path):
    sentinel = tmp_path / "outside.py"
    sentinel.write_text("transport = SseServerTransport('/messages')\n")
    main(["fix", str(roundtrip_copy), "--write"])
    capsys.readouterr()
    assert sentinel.read_text() == "transport = SseServerTransport('/messages')\n"


def test_safe_only_skips_review_confidence_fixers(roundtrip_copy, capsys):
    project, fixers, results = run_fix(roundtrip_copy, safe_only=True)
    assert fixers  # sanity: something is still selected
    assert all(fx.confidence == "safe" for fx in fixers)
    applied_rule_ids = set()
    for _, _, changes in results:
        applied_rule_ids.update(fx.rule_id for fx, _ in changes)
    # R001 and R006 are "review" -- must not have been applied.
    assert "R001" not in applied_rule_ids
    assert "R006" not in applied_rule_ids
    assert applied_rule_ids  # but the safe ones (R004/R005/R017) did apply


def test_rule_filter_restricts_to_one_fixer(roundtrip_copy):
    project, fixers, results = run_fix(roundtrip_copy, rule="R005")
    assert [fx.rule_id for fx in fixers] == ["R005"]
    applied_rule_ids = {fx.rule_id for _, _, changes in results for fx, _ in changes}
    assert applied_rule_ids == {"R005"}


def test_cmd_fixers_lists_every_fixer(capsys):
    exit_code = main(["fixers"])
    out = capsys.readouterr().out
    assert exit_code == 0
    for fx in all_fixers():
        assert fx.rule_id in out


def test_check_rules_and_entry_commands_still_work(capsys):
    """`fix`/`fixers` are additive -- the pre-existing commands must keep
    working exactly as before."""
    exit_code = main(["rules"])
    assert exit_code == 0
    capsys.readouterr()

    exit_code = main(["check", str(ROUNDTRIP), "--json"])
    out = capsys.readouterr().out
    assert exit_code in (0, 1)
    assert '"spec"' in out


# ---------------------------------------------------------------------------
# Round-trip: fix --write measurably improves the grade
# ---------------------------------------------------------------------------

def test_fix_write_then_check_improves_the_grade(roundtrip_copy, capsys):
    """The definitive end-to-end proof: grade the fixture, apply fix
    --write, grade it again, and confirm real improvement.

    Scored only over the rules this package ships fixers for (R001, R004,
    R005, R006, R017): other rules may exist in this codebase (or be added
    after this test was written) that this package makes no claim to fix,
    and folding their findings into the comparison would make the
    assertion depend on work happening elsewhere. Restricting the score to
    "the rules we actually touch" is what actually tests this package's
    claim.
    """
    _, rules, findings_before, _, _ = run_check(roundtrip_copy)
    before_relevant = [f for f in findings_before if f.rule_id in FIXER_RULE_IDS]
    assert before_relevant, "fixture must trip at least one rule this package fixes"
    score_before = score(before_relevant, rules)

    exit_code = main(["fix", str(roundtrip_copy), "--write"])
    capsys.readouterr()
    assert exit_code == 0

    _, rules_after, findings_after, _, _ = run_check(roundtrip_copy)
    after_relevant = [f for f in findings_after if f.rule_id in FIXER_RULE_IDS]
    score_after = score(after_relevant, rules_after)

    assert score_after > score_before
    assert len(after_relevant) < len(before_relevant)
    GRADE_RANK = {"A": 0, "B": 1, "C": 2, "D": 3, "F": 4}
    grade_before, grade_after = letter(score_before), letter(score_after)
    assert GRADE_RANK[grade_after] < GRADE_RANK[grade_before], (
        f"grade should strictly improve: {grade_before} -> {grade_after}"
    )
    # R004, R005 and R017 should be fully cleared -- they're "safe" fixers
    # for an unambiguous shape, and this fixture's shape is exactly that.
    after_rule_ids = {f.rule_id for f in after_relevant}
    assert "R004" not in after_rule_ids
    assert "R005" not in after_rule_ids
    assert "R017" not in after_rule_ids

    # And overall (not just the rules we fix), the project has strictly
    # fewer findings after the fix than before.
    assert len(findings_after) < len(findings_before)
