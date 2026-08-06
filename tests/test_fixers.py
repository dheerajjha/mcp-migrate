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
    assert {"R001", "R004", "R005", "R006", "R007", "R014", "R017", "R019"} <= FIXER_RULE_IDS


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
# R009 -- initialize / notifications/initialized handshake removed
# ---------------------------------------------------------------------------

R009_TODO_MSG = (
    'TODO(mcp-migrate): the initialize/notifications/initialized handshake is '
    'removed; advertise capabilities via server/discover instead, see '
    'https://modelcontextprotocol.io/specification/2026-07-28/changelog and '
    'cookbook/02-initialize-to-server-discover.md'
)
R009_BEFORE = (
    '@server.set_request_handler(InitializeRequest)\n'
    'def handle_initialize(request: InitializeRequest) -> InitializeResult:\n'
    '    print("handshake")\n'
    '    return InitializeResult(protocolVersion="2025-06-18")\n'
    '\n'
    'METHODS = {"notifications/initialized": handle_initialized}\n'
)
R009_AFTER = (
    f'# {R009_TODO_MSG}\n'
    '# @server.set_request_handler(InitializeRequest)\n'
    'def handle_initialize(request: InitializeRequest) -> InitializeResult:\n'
    '    print("handshake")\n'
    f'    # {R009_TODO_MSG}\n'
    '    # return InitializeResult(protocolVersion="2025-06-18")\n'
    '\n'
    f'# {R009_TODO_MSG}\n'
    '# METHODS = {"notifications/initialized": handle_initialized}\n'
)


def test_r009_comments_out_handshake_registration_and_wire_reference():
    result = fix("InitializeHandshakeFixer", R009_BEFORE)
    assert result.changed
    assert result.text == R009_AFTER
    assert FIXERS["InitializeHandshakeFixer"].confidence == "review"
    ast.parse(result.text)


def test_r009_skips_block_opener_lines():
    before = 'def handle_initialize(request: InitializeRequest) -> InitializeResult:\n    pass\n'
    result = fix("InitializeHandshakeFixer", before)
    assert result.changed is False
    assert result.text == before


def test_r009_catches_typescript_schema_suffix():
    before = 'server.setRequestHandler(InitializeRequestSchema, handleInitialize);\n'
    result = fix("InitializeHandshakeFixer", before, path="server.ts")
    assert result.changed
    assert '// TODO(mcp-migrate)' in result.text
    assert '// server.setRequestHandler(InitializeRequestSchema, handleInitialize);' in result.text


def test_r009_leaves_unrelated_code_alone():
    before = 'def initialize_db(path: str) -> None:\n    open(path, "a").close()\n'
    result = fix("InitializeHandshakeFixer", before)
    assert result.changed is False
    assert result.text == before


def test_r009_does_not_comment_out_a_requester_style_identifier():
    """An unbounded `InitializeRequest\\w*` matches `InitializeRequesterHelper`,
    which R009's Python rule does not flag -- `check` grades this file A. A
    fixer that edits it anyway comments out the assignment and leaves the
    next line holding an undefined name: the tool breaks code it just
    called clean. See #87."""
    before = 'helper = InitializeRequesterHelper()\nresult = helper.run()\n'
    result = fix("InitializeHandshakeFixer", before)
    assert result.changed is False
    assert result.text == before


def test_r009_still_catches_the_sdk_names_the_suffix_exists_for():
    """Bounding the suffix must not cost the shape it was added for."""
    for name in ("InitializeRequestSchema", "InitializeResultSchema",
                 "InitializedNotificationSchema"):
        result = fix("InitializeHandshakeFixer", f"x = {name}\n")
        assert result.changed, f"{name} should still be caught"


def test_r009_idempotent():
    once = fix("InitializeHandshakeFixer", R009_BEFORE)
    twice = fix("InitializeHandshakeFixer", once.text)
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
# R013 -- resources/subscribe and resources/unsubscribe removed
# ---------------------------------------------------------------------------

R013_TODO = (
    "# TODO(mcp-migrate): resources/subscribe and resources/unsubscribe are "
    "removed, replaced by the single long-lived subscriptions/listen call "
    "-- see https://modelcontextprotocol.io/specification/2026-07-28/changelog "
    "and cookbook/04-subscribe-to-subscriptions-listen.md"
)

R013_BEFORE = (
    'from mcp.types import SubscribeRequest, UnsubscribeRequest\n'
    '\n'
    'async def handle_subscribe(request: SubscribeRequest):\n'
    '    return {}\n'
    '\n'
    'METHODS = {"resources/subscribe": handle_subscribe}\n'
)
R013_AFTER = (
    f'{R013_TODO}\n'
    '# from mcp.types import SubscribeRequest, UnsubscribeRequest\n'
    '\n'
    'async def handle_subscribe(request: SubscribeRequest):\n'
    '    return {}\n'
    '\n'
    f'{R013_TODO}\n'
    '# METHODS = {"resources/subscribe": handle_subscribe}\n'
)


def test_r013_comments_out_subscribe_references_and_dispatch():
    result = fix("SubscriptionsReplacedFixer", R013_BEFORE)
    assert result.changed
    assert result.text == R013_AFTER
    assert FIXERS["SubscriptionsReplacedFixer"].confidence == "review"
    ast.parse(result.text)


def test_r013_never_comments_out_a_block_opener():
    result = fix("SubscriptionsReplacedFixer", R013_BEFORE)
    assert 'async def handle_subscribe(request: SubscribeRequest):' in result.text
    assert '    return {}' in result.text


def test_r013_declines_a_method_equality_check_on_a_block_opener():
    before = (
        'def dispatch(method):\n'
        '    if method == "resources/unsubscribe":\n'
        '        return {}\n'
    )
    result = fix("SubscriptionsReplacedFixer", before)
    assert result.changed is False
    assert result.text == before


def test_r013_comments_out_dict_shaped_dispatch():
    before = 'const METHODS = { "resources/unsubscribe": unsubscribeHandler };\n'
    result = fix("SubscriptionsReplacedFixer", before)
    assert result.changed
    assert (
        f'{R013_TODO}\n# const METHODS = {{ "resources/unsubscribe": unsubscribeHandler }};\n'
        in result.text
    )


def test_r013_does_not_flag_subscribe_requester():
    # A name that merely starts with SubscribeRequest is not the SDK's
    # SubscribeRequest type -- see #87 on the rule for the same guard.
    before = 'class SubscribeRequester:\n    pass\n'
    result = fix("SubscriptionsReplacedFixer", before)
    assert result.changed is False
    assert result.text == before


def test_r013_leaves_comment_only_mentions_alone():
    before = (
        '# resources/subscribe used to register interest in a resource\n'
        'METHODS = {"tools/list": list_tools}\n'
    )
    result = fix("SubscriptionsReplacedFixer", before)
    assert result.changed is False
    assert result.text == before


def test_r013_idempotent():
    once = fix("SubscriptionsReplacedFixer", R013_BEFORE)
    twice = fix("SubscriptionsReplacedFixer", once.text)
    assert twice.changed is False
    assert twice.text == once.text


# ---------------------------------------------------------------------------
# R019 -- tasks/list and blocking tasks/result removed
# ---------------------------------------------------------------------------

R019_BEFORE = (
    'from mcp.types import GetTaskPayloadRequest, ListTasksRequest\n'
    '\n'
    'async def wait_for_result(session, task_id: str):\n'
    '    req = GetTaskPayloadRequest(taskId=task_id)\n'
    '    return await session.send_request(req)\n'
    '\n'
    'METHODS = {"tasks/list": list_tasks, "tasks/result": blocking_result}\n'
)
R019_AFTER = (
    '# TODO(mcp-migrate): tasks/list and blocking tasks/result are removed; '
    'poll with tasks/get + tasks/update and declare io.modelcontextprotocol/tasks '
    'under extensions — see https://modelcontextprotocol.io/specification/2026-07-28/changelog '
    'and cookbook/11-tasks-polling.md\n'
    '# from mcp.types import GetTaskPayloadRequest, ListTasksRequest\n'
    '\n'
    'async def wait_for_result(session, task_id: str):\n'
    '    # TODO(mcp-migrate): tasks/list and blocking tasks/result are removed; '
    'poll with tasks/get + tasks/update and declare io.modelcontextprotocol/tasks '
    'under extensions — see https://modelcontextprotocol.io/specification/2026-07-28/changelog '
    'and cookbook/11-tasks-polling.md\n'
    '    # req = GetTaskPayloadRequest(taskId=task_id)\n'
    '    return await session.send_request(req)\n'
    '\n'
    '# TODO(mcp-migrate): tasks/list and blocking tasks/result are removed; '
    'poll with tasks/get + tasks/update and declare io.modelcontextprotocol/tasks '
    'under extensions — see https://modelcontextprotocol.io/specification/2026-07-28/changelog '
    'and cookbook/11-tasks-polling.md\n'
    '# METHODS = {"tasks/list": list_tasks, "tasks/result": blocking_result}\n'
)


def test_r019_comments_out_sdk_types_and_wire_methods():
    result = fix("TasksPollingFixer", R019_BEFORE)
    assert result.changed
    assert result.text == R019_AFTER
    assert FIXERS["TasksPollingFixer"].confidence == "review"
    ast.parse(result.text)


def test_r019_skips_block_opener_handler_signatures():
    before = (
        "async def handle_tasks(request: ListTasksRequest):\n"
        "    return []\n"
    )
    result = fix("TasksPollingFixer", before)
    assert result.changed is False
    assert result.text == before


def test_r019_leaves_docstring_prose_alone():
    before = (
        '"""blocking tasks/list + tasks/result pair. Kept only as a migration example."""\n'
        'METHODS = {"tasks/list": list_tasks}\n'
    )
    result = fix("TasksPollingFixer", before)
    assert result.changed
    assert before.splitlines()[0] in result.text
    assert '# METHODS = {"tasks/list": list_tasks}' in result.text
    ast.parse(result.text)


def test_r019_idempotent():
    once = fix("TasksPollingFixer", R019_BEFORE)
    twice = fix("TasksPollingFixer", once.text)
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
# R021 -- old JSON Schema dialect pin
# ---------------------------------------------------------------------------

_TARGET_DIALECT = "https://json-schema.org/draft/2020-12/schema"


def test_r021_rewrites_draft07_url():
    before = '"$schema": "http://json-schema.org/draft-07/schema#"\n'
    result = fix("OldJSONSchemaDialectFixer", before)
    assert result.changed
    assert result.text == '"$schema": "https://json-schema.org/draft/2020-12/schema"\n'
    assert FIXERS["OldJSONSchemaDialectFixer"].confidence == "safe"


def test_r021_rewrites_draft04_url():
    before = '"$schema": "http://json-schema.org/draft-04/schema"\n'
    result = fix("OldJSONSchemaDialectFixer", before)
    assert result.changed
    assert f'"{_TARGET_DIALECT}"' in result.text


def test_r021_rewrites_2019_09_url():
    before = '"$schema": "http://json-schema.org/draft/2019-09/schema"\n'
    result = fix("OldJSONSchemaDialectFixer", before)
    assert result.changed
    assert f'"{_TARGET_DIALECT}"' in result.text


def test_r021_rewrites_short_2019_09():
    before = '"$schema": "2019-09"\n'
    result = fix("OldJSONSchemaDialectFixer", before)
    assert result.changed
    assert f'"{_TARGET_DIALECT}"' in result.text


def test_r021_leaves_ambiguous_comment_alone():
    """A mention of draft-07 that is NOT inside a $schema assignment must not
    be touched -- that would be a false positive and silent corruption."""
    before = "# Previously used draft-07 schema dialect\n"
    result = fix("OldJSONSchemaDialectFixer", before)
    assert result.changed is False
    assert result.text == before


def test_r021_leaves_unrelated_key_alone():
    """An old dialect string in a value keyed by something other than $schema
    must not be rewritten -- the fixer cannot know what that string means."""
    before = '"description": "http://json-schema.org/draft-07/schema#"\n'
    result = fix("OldJSONSchemaDialectFixer", before)
    assert result.changed is False
    assert result.text == before


def test_r021_idempotent():
    before = '"$schema": "http://json-schema.org/draft-07/schema#"\n'
    once = fix("OldJSONSchemaDialectFixer", before)
    twice = fix("OldJSONSchemaDialectFixer", once.text)
    assert twice.changed is False
    assert twice.text == once.text


def test_r021_already_2020_12_is_unchanged():
    before = f'"$schema": "{_TARGET_DIALECT}"\n'
    result = fix("OldJSONSchemaDialectFixer", before)
    assert result.changed is False
    assert result.text == before


# ---------------------------------------------------------------------------
# R020 -- Dynamic Client Registration deprecated
# ---------------------------------------------------------------------------

def test_r020_annotates_register_client():
    before = "def register_client(request):\n    pass\n"
    result = fix("DynamicClientRegistrationDeprecatedFixer", before)
    assert result.changed
    assert "# TODO(mcp-migrate): RFC 7591 Dynamic Client Registration is deprecated" in result.text
    assert "# # TODO" not in result.text
    assert FIXERS["DynamicClientRegistrationDeprecatedFixer"].confidence == "review"


def test_r020_annotates_register_client_request():
    before = "req = RegisterClientRequest()\n"
    result = fix("DynamicClientRegistrationDeprecatedFixer", before)
    assert result.changed
    assert "TODO(mcp-migrate)" in result.text


def test_r020_annotates_dynamic_client_registration():
    before = "class DynamicClientRegistration:\n    pass\n"
    result = fix("DynamicClientRegistrationDeprecatedFixer", before)
    assert result.changed
    assert "TODO(mcp-migrate)" in result.text


def test_r020_leaves_comments_alone():
    before = "# Note: register_client was used previously\n"
    result = fix("DynamicClientRegistrationDeprecatedFixer", before)
    assert result.changed is False
    assert result.text == before


def test_r020_idempotent():
    before = "req = RegisterClientRequest()\n"
    once = fix("DynamicClientRegistrationDeprecatedFixer", before)
    twice = fix("DynamicClientRegistrationDeprecatedFixer", once.text)
    assert twice.changed is False
    assert twice.text == once.text


# ---------------------------------------------------------------------------
# R008 -- trace context not propagated from _meta
# ---------------------------------------------------------------------------

def test_r008_annotates_python_start_as_current_span():
    before = "    with tracer.start_as_current_span(\"call_tool\"):\n        pass\n"
    result = fix("TraceContextFixer", before)
    assert result.changed
    assert "# TODO(mcp-migrate): extract traceparent/tracestate/baggage from _meta" in result.text
    # the span-creation line itself must survive untouched, not get commented out
    assert "    with tracer.start_as_current_span(\"call_tool\"):\n" in result.text


def test_r008_annotates_python_start_span():
    before = "span = tracer.start_span(\"call_tool\")\n"
    result = fix("TraceContextFixer", before)
    assert result.changed
    assert "TODO(mcp-migrate)" in result.text
    assert 'span = tracer.start_span("call_tool")\n' in result.text


def test_r008_annotates_typescript_start_active_span():
    before = 'tracer.startActiveSpan("call_tool", (span) => {\n});\n'
    result = fix("TraceContextFixer", before, path="server.ts")
    assert result.changed
    assert "// TODO(mcp-migrate)" in result.text
    assert FIXERS["TraceContextFixer"].confidence == "review"


def test_r008_leaves_comments_alone():
    before = "# tracer.start_span(\"call_tool\") used to be called here\n"
    result = fix("TraceContextFixer", before)
# R018 -- server-initiated roots/sampling/elicitation -> Multi Round-Trip Requests
# ---------------------------------------------------------------------------

def test_r018_annotates_create_message_call():
    before = "    sample = await ctx.create_message(messages=[])\n"
    result = fix("MultiRoundTripFixer", before)
    assert result.changed
    assert "# TODO(mcp-migrate): server-initiated request replaced by Multi Round-Trip" in result.text
    # the call itself must survive untouched -- it's what needs the rewrite, not dead code
    assert "    sample = await ctx.create_message(messages=[])\n" in result.text


def test_r018_annotates_list_roots_call():
    before = "roots = await ctx.list_roots()\n"
    result = fix("MultiRoundTripFixer", before)
    assert result.changed
    assert "TODO(mcp-migrate)" in result.text


def test_r018_annotates_elicit_request_construction():
    before = "req = ElicitRequest(message=\"pick one\")\n"
    result = fix("MultiRoundTripFixer", before)
    assert result.changed
    assert "TODO(mcp-migrate)" in result.text


def test_r018_annotates_typescript_schema_handler():
    before = 'server.setRequestHandler(CreateMessageRequestSchema, handler);\n'
    result = fix("MultiRoundTripFixer", before, path="server.ts")
    assert result.changed
    assert "// TODO(mcp-migrate)" in result.text
    assert FIXERS["MultiRoundTripFixer"].confidence == "review"


def test_r018_leaves_bare_identifier_without_call_alone():
    # `list_roots` mentioned with no call -- e.g. a def/import line -- isn't
    # a call site to annotate.
    before = "from mcp.client import list_roots\n"
    result = fix("MultiRoundTripFixer", before)
    assert result.changed is False
    assert result.text == before


def test_r008_leaves_unrelated_code_alone():
    before = "def handle_call_tool(request):\n    return dispatch(request)\n"
    result = fix("TraceContextFixer", before)
def test_r018_leaves_comments_alone():
    before = "# ctx.create_message(...) used to be called here\n"
    result = fix("MultiRoundTripFixer", before)
    assert result.changed is False
    assert result.text == before


def test_r008_idempotent():
    before = "span = tracer.start_span(\"call_tool\")\n"
    once = fix("TraceContextFixer", before)
    twice = fix("TraceContextFixer", once.text)
def test_r018_idempotent():
    before = "roots = await ctx.list_roots()\n"
    once = fix("MultiRoundTripFixer", before)
    twice = fix("MultiRoundTripFixer", once.text)
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


# --- comment syntax follows the file, not the fixer (#117) ---------------
#
# `#` does not open a comment in TypeScript. A fixer that hardcodes it
# writes a syntax error into the user's source and then reports success --
# strictly worse than the finding it was repairing, because every other
# failure mode in this project produces a wrong *report* a human reads and
# discards, while this one edits their code and leaves it broken.

TS_SUFFIXES = (".ts", ".tsx", ".mts", ".cts", ".js", ".jsx", ".mjs", ".cjs")

# One source per comment-emitting fixer, shaped to trip it. Written in
# TypeScript syntax, since that is the language whose comments differ.
TS_TRIGGERS = {
    "R001": 'const sessionId = req.headers["Mcp-Session-Id"];\n',
    "R006": 'const transport = "sse";\n',
    "R007": 'const roots = await session.create_message(params);\n',
    "R013": 'const METHODS = { "resources/subscribe": subscribeHandler };\n',
    "R014": 'const lastEventId = req.headers["Last-Event-ID"];\n',
    "R019": 'const m = "tasks/list";\n',
    "R020": 'export async function registerClient(url, metadata) { return fetch(url); }\n',
}


def test_no_fixer_writes_a_python_comment_into_typescript():
    # The regression guard for #117, across every fixer at once: a new
    # fixer that hardcodes `# ` fails here without anyone remembering to
    # add it to a list.
    for fixer in all_fixers():
        source = TS_TRIGGERS.get(fixer.rule_id)
        if source is None:
            continue
        result = fixer.fix(source, Path("server.ts"))
        if not result.changed:
            continue
        added = [
            line for line in result.text.splitlines()
            if line.lstrip().startswith("#")
        ]
        assert not added, (
            f"{type(fixer).__name__} wrote a Python `#` comment into a .ts "
            f"file, which does not parse: {added}"
        )


def test_typescript_fixes_use_slash_comments():
    from mcp_migrate.fixers.r001_session_id import SessionIdHeaderFixer

    source = 'const sessionId = req.headers["Mcp-Session-Id"];\n'
    result = SessionIdHeaderFixer().fix(source, Path("server.ts"))

    assert result.changed
    assert "// TODO(mcp-migrate)" in result.text
    assert '// const sessionId' in result.text
    assert "#" not in result.text


def test_python_fixes_still_use_hash_comments():
    from mcp_migrate.fixers.r001_session_id import SessionIdHeaderFixer

    source = 'session_id = request.headers.get("Mcp-Session-Id")\n'
    result = SessionIdHeaderFixer().fix(source, Path("server.py"))

    assert result.changed
    assert "# TODO(mcp-migrate)" in result.text
    # Checked per line, not as a substring: the TODO carries a spec URL,
    # and `https://` contains a `//` that is not a comment marker.
    assert not [ln for ln in result.text.splitlines() if ln.lstrip().startswith("//")]


@pytest.mark.parametrize("suffix", TS_SUFFIXES)
def test_every_c_family_suffix_gets_slash_comments(suffix):
    # .mts/.cts/.mjs/.cjs are read by the scanner and were missing from the
    # one hardcoded suffix list that did exist, so they corrupted silently.
    from mcp_migrate.fixers.base import comment_prefix

    assert comment_prefix(Path(f"server{suffix}")) == "// "


def test_unknown_suffix_falls_back_to_hash():
    from mcp_migrate.fixers.base import comment_prefix

    assert comment_prefix(Path("server.py")) == "# "
    assert comment_prefix(Path("Makefile")) == "# "


def test_typescript_fix_output_has_no_stray_hash_lines():
    # End-to-end on the issue's own repro: the whole point is that the
    # file still parses as TypeScript afterwards.
    from mcp_migrate.fixers.r001_session_id import SessionIdHeaderFixer
    from mcp_migrate.fixers.r019_tasks_polling import TasksPollingFixer

    source = (
        "export function register(server: Server) {\n"
        '  const sessionId = req.headers["Mcp-Session-Id"];\n'
        '  const m = "tasks/list";\n'
        "  return { sessionId, m };\n"
        "}\n"
    )
    text = SessionIdHeaderFixer().fix(source, Path("server.ts")).text
    text = TasksPollingFixer().fix(text, Path("server.ts")).text

    assert not [ln for ln in text.splitlines() if ln.lstrip().startswith("#")]
    assert text.count("// TODO(mcp-migrate)") == 2


def test_typescript_fixes_stay_idempotent():
    # The `already_commented` check has to recognise `//`, or a second run
    # comments the comment.
    from mcp_migrate.fixers.r001_session_id import SessionIdHeaderFixer

    fixer = SessionIdHeaderFixer()
    once = fixer.fix('const s = req.headers["Mcp-Session-Id"];\n', Path("server.ts")).text
    twice = fixer.fix(once, Path("server.ts"))

    assert not twice.changed, "second run must be a no-op"
