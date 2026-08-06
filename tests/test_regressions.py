"""Regression tests for false positives found scanning 14 real MCP servers.

Each test below is anchored to real evidence from that scan:

- mcp-neo4j-cypher: 10 of 15 findings came from `"method": "tools/list"`
  string payloads in integration tests.
- motherduck: 15 of 20 findings came from a deliberate legacy-transport
  backward-compat test; the R001 hit that remained was inside a
  `click.option(help=...)` string explaining a CLI flag.
- mcp-atlassian: its only R001 hit was inside a `logger.debug(...)` message;
  its 19 R003 hits (475 penalty points) were all plain Confluence/Jira REST
  calls with no MCP transport surface anywhere in the file.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from mcp_migrate.cli import run_check
from mcp_migrate.grade import RULE_CAP, WEIGHT, score
from mcp_migrate.rules.base import Finding, Rule
from mcp_migrate.rules.r004_tool_ordering import NondeterministicToolOrder
from mcp_migrate.rules.r005_extensions import NoExtensionsDeclared
from mcp_migrate.rules.r007_deprecated_features import DeprecatedCoreFeatures
from mcp_migrate.rules.r009_initialize_handshake_removed import (
    InitializeHandshakeStillImplemented,
)
from mcp_migrate.rules.r010_server_discover_missing import ServerDiscoverMissing
from mcp_migrate.rules.r011_ping_removed import PingRemoved
from mcp_migrate.rules.r017_resource_not_found_code_changed import (
    ResourceNotFoundCodeChanged,
)
from mcp_migrate.rules.r020_dynamic_client_registration_deprecated import (
    DynamicClientRegistrationDeprecated,
)
from mcp_migrate.rules.r021_json_schema_2020_12_required import OldJSONSchemaDialect
from mcp_migrate.scan import load_project

FIXTURES = Path(__file__).parent / "fixtures"


def _findings_by_rule(root: Path, **kwargs) -> dict[str, list]:
    _, _, findings, _, _ = run_check(root, **kwargs)
    by_rule: dict[str, list] = {}
    for f in findings:
        by_rule.setdefault(f.rule_id, []).append(f)
    return by_rule


# --- 1. test code is skipped by default -----------------------------------

TEST_SKIP_PROJECT = FIXTURES / "test_skip_project"


def test_findings_in_tests_dir_are_skipped_by_default():
    by_rule = _findings_by_rule(TEST_SKIP_PROJECT)
    assert "R006" not in by_rule, (
        "R006 should not fire on tests/test_legacy_transport_compat.py "
        "when --include-tests is not passed"
    )


def test_include_tests_flag_finds_them():
    by_rule = _findings_by_rule(TEST_SKIP_PROJECT, include_tests=True)
    assert "R006" in by_rule, "--include-tests should surface findings inside tests/"


@pytest.mark.parametrize("dirname", ["tests", "test", "testing", "fixtures", "examples", "docs"])
def test_each_test_dir_segment_is_skipped_by_default(tmp_path, dirname):
    (tmp_path / dirname).mkdir()
    (tmp_path / dirname / "offender.py").write_text(
        'from mcp.server.sse import SseServerTransport\n'
        'transport = SseServerTransport("/messages")\n'
    )
    project = load_project(tmp_path)
    assert project.files == [], f"{dirname}/ should be skipped by default"

    project_included = load_project(tmp_path, include_tests=True)
    assert len(project_included.files) == 1, f"{dirname}/ should be scanned with include_tests=True"


@pytest.mark.parametrize("filename", ["test_thing.py", "thing_test.py", "conftest.py"])
def test_each_test_filename_pattern_is_skipped_by_default(tmp_path, filename):
    (tmp_path / filename).write_text(
        'from mcp.server.sse import SseServerTransport\n'
        'transport = SseServerTransport("/messages")\n'
    )
    project = load_project(tmp_path)
    assert project.files == [], f"{filename} should be skipped by default"

    project_included = load_project(tmp_path, include_tests=True)
    assert len(project_included.files) == 1, f"{filename} should be scanned with include_tests=True"


def test_skipping_is_relative_to_scan_root_not_absolute_path():
    """legacy_server/clean_server live under tests/fixtures/ -- scanning them
    directly (root = .../tests/fixtures/legacy_server) must not vanish just
    because "tests" and "fixtures" appear in the *absolute* path above root.
    """
    project = load_project(FIXTURES / "legacy_server")
    assert len(project.files) == 6


# --- 2. comments/docstrings/log strings don't count as usage --------------

COMMENT_ONLY = FIXTURES / "comment_only_mentions"


def test_mention_in_docstring_comment_and_log_string_does_not_fire_r001():
    by_rule = _findings_by_rule(COMMENT_ONLY)
    assert "R001" not in by_rule, (
        f"R001 should not fire on text-only mentions of Mcp-Session-Id: {by_rule.get('R001')}"
    )


def test_search_code_excludes_docstrings_comments_and_strings(tmp_path):
    (tmp_path / "mod.py").write_text(
        '"""A module about WIDGET things."""\n'
        "# WIDGET is mentioned here too\n"
        'log = "WIDGET seen in a log message"\n'
        "WIDGET = 1\n"
    )
    project = load_project(tmp_path)
    code_hits = list(project.search_code(r"WIDGET"))
    assert len(code_hits) == 1
    assert code_hits[0][1] == 4  # only the real assignment, line 4

    text_hits = list(project.search(r"WIDGET"))
    assert len(text_hits) == 4  # plain search still finds all four


def test_search_code_falls_back_to_plain_search_on_tokenize_failure(tmp_path):
    # Deliberately invalid Python (unterminated string) -- must not crash,
    # and must still find the match via the plain-search fallback.
    bad = tmp_path / "bad.py"
    bad.write_text('WIDGET = "unterminated\n')
    project = load_project(tmp_path)
    assert project.files, "file with a syntax error should still be loaded (tree=None is fine)"
    hits = list(project.search_code(r"WIDGET"))
    assert len(hits) == 1


# --- 3. R003 requires MCP protocol surface in the same file ----------------

REST_WRAPPER = FIXTURES / "rest_wrapper_no_mcp_surface"


def test_plain_rest_post_with_no_mcp_surface_does_not_fire_r003():
    by_rule = _findings_by_rule(REST_WRAPPER)
    assert "R003" not in by_rule, (
        f"R003 should not fire on a REST client with no MCP transport surface: {by_rule.get('R003')}"
    )


def test_r003_still_fires_when_file_hand_rolls_jsonrpc_payload():
    by_rule = _findings_by_rule(FIXTURES / "legacy_server")
    assert "R003" in by_rule, "R003 should still fire when a file posts a hand-rolled jsonrpc payload"


def test_fastmcp_import_alone_does_not_satisfy_the_mcp_surface_gate():
    """`mcp.server.fastmcp` owns the transport entirely -- a file that only
    imports FastMCP and separately posts to its own backend API is not
    hand-rolling MCP transport, confirmed against real false positives on
    aws-documentation-mcp-server and duckduckgo-mcp-server."""
    by_rule = _findings_by_rule(FIXTURES / "fastmcp_wrapper_no_mcp_surface")
    assert "R003" not in by_rule, (
        f"R003 should not fire on a FastMCP tool that calls an unrelated REST API: {by_rule.get('R003')}"
    )


# --- 4. a single rule cannot dominate the score ----------------------------

class _FakeBreakingRule(Rule):
    id = "R900"
    severity = "breaking"


def test_twenty_hits_of_one_breaking_rule_cost_25_points_not_500():
    rules = {"R900": _FakeBreakingRule()}
    findings = [Finding(rule_id="R900", message="x") for _ in range(20)]
    # Uncapped this would be 20 * WEIGHT["breaking"] = 500 points of penalty
    # (score floored at 0). Capped, a single rule can cost at most
    # RULE_CAP["breaking"] points.
    assert 20 * WEIGHT["breaking"] > 100
    value = score(findings, rules)
    assert value == 100 - RULE_CAP["breaking"]
    assert value == 75


def test_rule_cap_applies_independently_per_rule():
    class _FakeAdvisoryRule(Rule):
        id = "R901"
        severity = "advisory"

    rules = {"R900": _FakeBreakingRule(), "R901": _FakeAdvisoryRule()}
    findings = (
        [Finding(rule_id="R900", message="x") for _ in range(10)]
        + [Finding(rule_id="R901", message="y") for _ in range(10)]
    )
    value = score(findings, rules)
    expected_penalty = RULE_CAP["breaking"] + RULE_CAP["advisory"]
    assert value == 100 - expected_penalty


def test_single_hit_is_unaffected_by_the_cap():
    rules = {"R900": _FakeBreakingRule()}
    findings = [Finding(rule_id="R900", message="x")]
    assert score(findings, rules) == 100 - WEIGHT["breaking"]


# --- CLI display cap (findings table capped at 5/rule, JSON stays full) ---

def test_cli_json_output_is_never_truncated_per_rule(capsys):
    import json

    from mcp_migrate.cli import main

    exit_code = main(["check", str(FIXTURES / "legacy_server"), "--json"])
    data = json.loads(capsys.readouterr().out)
    assert exit_code in (0, 1)
    assert isinstance(data["findings"], list)


def test_cli_human_output_caps_findings_per_rule_and_says_how_many_more(tmp_path, capsys):
    # A file with many hand-rolled-looking assignments named to trip R002
    # (module-level dict literally named `sessions`) many times over by
    # spreading the same pattern across many module-level names.
    lines = [f"sessions_{i}: dict = {{}}" for i in range(8)]
    (tmp_path / "server.py").write_text("\n".join(lines) + "\n")

    from mcp_migrate.cli import main

    exit_code = main(["check", str(tmp_path)])
    out = capsys.readouterr().out
    assert exit_code in (0, 1)
    assert "more R002 finding" in out


# --- 5. false-positive guards for the new breaking-surface rules (R009-R021) --

def test_r010_does_not_fire_without_any_mcp_request_handlers(tmp_path):
    # Ordinary code that imports something coincidentally called `mcp` but
    # never registers a tool/resource/prompt handler is not an MCP server
    # at all -- R010 must not invent a "missing server/discover" finding
    # for it.
    (tmp_path / "app.py").write_text(
        "import mcp\n\n"
        "def compute(x):\n"
        "    return mcp.helper(x) * 2\n"
    )
    project = load_project(tmp_path)
    assert ServerDiscoverMissing().check(project) == []


def test_r011_ping_does_not_fire_on_an_ordinary_health_check_route(tmp_path):
    # A bare "/ping" health-check endpoint is extremely common in ordinary,
    # non-MCP web servers and has nothing to do with the MCP `ping`
    # request -- must not fire.
    (tmp_path / "app.py").write_text(
        "from flask import Flask\n\n"
        "app = Flask(__name__)\n\n"
        "@app.route(\"/ping\")\n"
        "def ping():\n"
        "    return \"pong\"\n"
    )
    project = load_project(tmp_path)
    assert PingRemoved().check(project) == []


def test_r017_does_not_fire_on_an_unrelated_negative_number(tmp_path):
    # -32002 on its own is just a number (a port, an offset, a sentinel);
    # only paired with resource-not-found language on the same line is it
    # evidence of the old error-code convention.
    (tmp_path / "server.py").write_text(
        "TIMEOUT_SENTINEL = -32002  # arbitrary value used to mean \"no timeout\"\n"
    )
    project = load_project(tmp_path)
    assert ResourceNotFoundCodeChanged().check(project) == []


def test_r020_does_not_fire_on_an_unrelated_register_method(tmp_path):
    # A generic "register a client" method in, say, a CRM or billing
    # system has nothing to do with OAuth Dynamic Client Registration --
    # only the exact SDK-shaped names count.
    (tmp_path / "billing.py").write_text(
        "class CRM:\n"
        "    def register_new_customer(self, info):\n"
        "        return {\"customer_id\": 1, **info}\n"
    )
    project = load_project(tmp_path)
    assert DynamicClientRegistrationDeprecated().check(project) == []


def test_r021_does_not_fire_on_an_unrelated_mention_of_draft_or_schema(tmp_path):
    # Almost no real MCP server declares a JSON Schema dialect at all --
    # absence of "2020-12" must not be the trigger (it would fire on
    # nearly everything). Only an explicit *old* draft reference should.
    (tmp_path / "server.py").write_text(
        '"""This module is still a draft; see the design doc for the schema."""\n'
        "inputSchema = {\"type\": \"object\"}\n"
    )
    project = load_project(tmp_path)
    assert OldJSONSchemaDialect().check(project) == []


# --- 6. R010 detection blind spots (false *negatives*, found on real code) ---
#
# These three servers scored A with zero findings, not because they were
# migrated but because R010 could not see their handlers at all. A grade a
# project did not earn is as damaging to this tool's credibility as a
# finding it does not deserve.

FASTMCP_FUNCTIONAL = FIXTURES / "fastmcp_functional_registration"
DISCOVER_HELPERS = FIXTURES / "discover_named_helpers"


def test_r010_sees_fastmcp_subclass_with_functional_registration():
    # mcp-server-qdrant subclasses FastMCP (so the name is never followed by
    # `(`) and registers with `self.tool(fn, name=...)` rather than a
    # decorator. cloudwatch-mcp-server uses `mcp.tool(name=...)(fn)`. Both
    # escaped R010 completely and were graded A on zero findings.
    project = load_project(FASTMCP_FUNCTIONAL)
    findings = ServerDiscoverMissing().check(project)
    assert findings, (
        "a FastMCP subclass registering tools functionally still registers MCP "
        "request handlers and still lacks server/discover -- R010 must fire"
    )


def test_r010_is_not_suppressed_by_a_helper_whose_name_contains_discover():
    # mcp-atlassian's Jira helpers `_try_discover_fields_from_existing_epic`
    # and `_discover_application_types` matched the old substring pattern and
    # convinced R010 the project implemented server/discover, silencing the
    # rule for the entire project.
    project = load_project(DISCOVER_HELPERS)
    findings = ServerDiscoverMissing().check(project)
    assert findings, (
        "a domain helper that merely contains the word 'discover' is not an "
        "implementation of server/discover and must not suppress R010"
    )


def test_r010_still_respects_a_real_server_discover_implementation(tmp_path):
    # The other direction: tightening the name match must not start firing on
    # projects that genuinely do implement the method.
    (tmp_path / "server.py").write_text(
        "from mcp.server import Server\n"
        "from mcp.types import Tool\n\n"
        "app = Server('demo')\n\n"
        "@app.list_tools()\n"
        "async def list_tools() -> list[Tool]:\n"
        "    return []\n\n"
        "async def discover() -> dict:\n"
        "    return {'protocolVersions': ['2026-07-28']}\n"
    )
    project = load_project(tmp_path)
    assert ServerDiscoverMissing().check(project) == []


def _r010_has_handlers_source() -> str:
    # Enough to satisfy _has_request_handlers on its own, independent of
    # whatever the test appends about server/discover.
    return (
        "from mcp.server import Server\n"
        "from mcp.types import Tool\n\n"
        "app = Server('demo')\n\n"
        "@app.list_tools()\n"
        "async def list_tools() -> list[Tool]:\n"
        "    return []\n\n"
    )


def test_r010_is_not_suppressed_by_a_todo_comment_admitting_the_gap(tmp_path):
    # A `# TODO: server/discover is not implemented yet` used to satisfy the
    # raw `project.search` the Python check ran -- the more clearly a project
    # documented the gap, the more certain R010 was there wasn't one.
    (tmp_path / "server.py").write_text(
        _r010_has_handlers_source() + "# TODO: server/discover is not implemented yet\n"
    )
    project = load_project(tmp_path)
    findings = ServerDiscoverMissing().check(project)
    assert findings, "a TODO admitting the gap must not suppress R010"


def test_r010_is_not_suppressed_by_a_docstring_mentioning_the_gap(tmp_path):
    (tmp_path / "server.py").write_text(
        _r010_has_handlers_source()
        + '"""We do not implement server/discover."""\n'
    )
    project = load_project(tmp_path)
    findings = ServerDiscoverMissing().check(project)
    assert findings, "a docstring mentioning the gap must not suppress R010"


def test_r010_still_suppressed_by_a_real_wire_string_literal(tmp_path):
    # The fix must not overcorrect: a genuine string literal use of the
    # wire name (e.g. a route table, not a comment about it) still counts
    # as evidence the method is implemented.
    (tmp_path / "server.py").write_text(
        _r010_has_handlers_source() + 'ROUTES = {"server/discover": handle_discover}\n'
    )
    project = load_project(tmp_path)
    assert ServerDiscoverMissing().check(project) == []


# --- 7. R015/R016 must not demand fields the framework owns ----------------
#
# The official SDK (mcp 2.0.0) sets `resultType` on every result it
# serializes, and fills ttlMs/cacheScope from cache hints registered on the
# Server. Asking an SDK user to write those into a handler is asking for
# something they cannot do -- a false positive on every SDK-based server.

from mcp_migrate.rules.r015_result_type_required import RequiredResultTypeMissing
from mcp_migrate.rules.r016_cacheable_result_required import (
    CacheableResultMetadataMissing,
)

_LOWLEVEL_HANDLER = (
    "from mcp.server import Server\n"
    "from mcp.types import Tool\n\n"
    "app = Server('demo')\n\n"
    "@app.list_tools()\n"
    "async def list_tools() -> list[Tool]:\n"
    "    return []\n"
)


def test_r015_does_not_fire_when_the_sdk_serializes_the_result(tmp_path):
    # Runner._serialize ends with an unconditional
    #   dumped["resultType"] = "complete"
    # for modern protocol versions, so the field is already on the wire and
    # the handler author has nowhere to put it.
    (tmp_path / "server.py").write_text(_LOWLEVEL_HANDLER)
    project = load_project(tmp_path)
    assert RequiredResultTypeMissing().check(project) == [], (
        "the SDK stamps resultType itself -- telling an SDK user to add it is "
        "a finding they cannot act on"
    )


def test_r015_still_fires_on_a_hand_rolled_jsonrpc_envelope(tmp_path):
    # A server that builds its own JSON-RPC responses owns the envelope, so
    # a missing resultType there is real and its author can fix it.
    (tmp_path / "server.py").write_text(
        "import json\n\n"
        "def handle(request):\n"
        "    if request['method'] == 'tools/list':\n"
        "        return json.dumps({\n"
        "            'jsonrpc': '2.0',\n"
        "            'id': request['id'],\n"
        "            'result': {'tools': []},\n"
        "        })\n"
    )
    project = load_project(tmp_path)
    # No MCP handler decorator here, so R015's own handler gate applies; the
    # point of this test is that the SDK exemption did not swallow the
    # project wholesale -- it must not raise or crash, and must not exempt a
    # project that never imports the SDK.
    from mcp_migrate.rules.r015_result_type_required import _sdk_owns_serialization
    assert not _sdk_owns_serialization(project)


def test_r015_stays_silent_on_a_request_without_a_result_key(tmp_path):
    # `id` + `method` with no `result`/`error` key is a request, not a
    # result -- `resultType` is a result-only field and has nowhere to go
    # on this shape.
    (tmp_path / "client.py").write_text(
        "import json\n\n"
        "def build_request(request_id):\n"
        "    return json.dumps({\n"
        "        'jsonrpc': '2.0',\n"
        "        'method': 'tools/list',\n"
        "        'id': request_id,\n"
        "    })\n"
    )
    project = load_project(tmp_path)
    assert RequiredResultTypeMissing().check(project) == [], (
        "a request has no result field to add resultType to"
    )


def test_r016_is_satisfied_by_cache_hints_configured_on_the_server(tmp_path):
    # `Server(cache_hints={...})` is how the SDK documents this. It is set
    # once at construction, not written into each handler's file.
    (tmp_path / "server.py").write_text(
        "from mcp.server import Server\n"
        "from mcp.server.caching import CacheHint\n"
        "from mcp.types import Tool\n\n"
        "app = Server('demo', cache_hints={'tools/list': CacheHint(ttl_ms=5000)})\n\n"
        "@app.list_tools()\n"
        "async def list_tools() -> list[Tool]:\n"
        "    return []\n"
    )
    project = load_project(tmp_path)
    assert CacheableResultMetadataMissing().check(project) == [], (
        "a server that configures cache hints has handled this -- reporting it "
        "as still missing looks for the field in the wrong place"
    )


def test_r016_still_fires_when_no_cache_metadata_exists_anywhere(tmp_path):
    # Without hints the SDK emits no cache metadata at all, so the finding
    # remains true and the fix (configure cache_hints) is actionable.
    (tmp_path / "server.py").write_text(_LOWLEVEL_HANDLER)
    project = load_project(tmp_path)
    assert CacheableResultMetadataMissing().check(project), (
        "no hints and no literal fields means no cache metadata on the wire"
    )


def test_r016_flags_cache_metadata_named_only_in_python_comment(tmp_path):
    # A comment mentioning ttlMs or cacheScope does not satisfy the rule.
    (tmp_path / "server.py").write_text(
        "# The transport layer adds ttlMs and cacheScope when cache_hints are set.\n"
        "@app.list_tools()\n"
        "async def list_tools():\n"
        "    return []\n"
    )
    project = load_project(tmp_path)
    assert len(CacheableResultMetadataMissing().check(project)) == 1


def test_r016_suppressed_by_cache_metadata_in_python_code(tmp_path):
    # A code mention of ttlMs or cacheScope satisfies the rule.
    (tmp_path / "server.py").write_text(
        "@app.list_tools()\n"
        "async def list_tools():\n"
        "    return [{'ttlMs': 5000}]\n"
    )
    project = load_project(tmp_path)
    assert CacheableResultMetadataMissing().check(project) == []


# --- 8. R007 must not fire on the Anthropic Messages API -------------------
#
# Found by scanning the official registry, not by reading code. R007's
# sampling pattern was `sampling/createMessage|create_message|
# SamplingCapability`. That bare `create_message` has no word boundary and
# no MCP context, so it matched `_create_message` -- the conventional name
# for a wrapper around Anthropic's Messages API, and a very large share of
# the Python AI ecosystem.
#
# browser-use took three `deprecated` findings for its Anthropic client and
# dropped from 79 to 67 for it. None of the three had anything to do with
# MCP Sampling.

def test_r007_does_not_fire_on_an_anthropic_client_wrapper(tmp_path):
    # Reduced from browser_use/llm/anthropic/chat.py.
    (tmp_path / "chat.py").write_text(
        "from anthropic import AsyncAnthropic\n\n\n"
        "class ChatAnthropic:\n"
        "    async def _create_message(self, **params):\n"
        "        client = self.get_client()\n"
        "        return await client.messages.create(**params)\n\n"
        "    async def ainvoke(self, messages):\n"
        "        return await self._create_message(model=self.model, messages=messages)\n"
    )
    findings = DeprecatedCoreFeatures().check(load_project(tmp_path))
    assert findings == [], (
        "wrapping the Anthropic Messages API is not MCP Sampling; this fired "
        f"on real code across the registry: {[f.message for f in findings]}"
    )


def test_r007_still_fires_on_real_mcp_sampling(tmp_path):
    # The shape every true positive takes -- both the SDK's own examples
    # (`ctx.session.create_message`) and the low-level API
    # (`server.request_context.session.create_message`) go through the
    # session object. That qualifier is what makes the rule precise.
    (tmp_path / "server.py").write_text(
        "from mcp.server.fastmcp import Context, FastMCP\n\n"
        "mcp = FastMCP('demo')\n\n\n"
        "@mcp.tool()\n"
        "async def summarize(text: str, ctx: Context) -> str:\n"
        "    result = await ctx.session.create_message(\n"
        "        messages=[], max_tokens=100,\n"
        "    )\n"
        "    return result.content.text\n"
    )
    assert DeprecatedCoreFeatures().check(load_project(tmp_path)), (
        "a real sampling call through the session must still be reported"
    )


def test_r007_still_fires_on_declared_sampling_capability(tmp_path):
    (tmp_path / "server.py").write_text(
        "from mcp.types import SamplingCapability, ServerCapabilities\n\n"
        "caps = ServerCapabilities(sampling=SamplingCapability())\n"
    )
    assert DeprecatedCoreFeatures().check(load_project(tmp_path))


# --- 9. prose is not an implementation -------------------------------------
#
# All three of these came out of hand-auditing 30 findings sampled from a
# 620-server registry scan, which is the only reason they were found: the
# suite was green throughout.
#
# Removed JSON-RPC method names can only appear as string literals, so the
# rules that look for them had to use raw text search -- which also reads
# comments and docstrings, where people *explain* the protocol. A module
# docstring describing a migration is not an implementation of it.

def test_r009_does_not_fire_on_a_docstring_describing_the_handshake(tmp_path):
    # sidney/web-to-markdown-mcp: this docstring alone produced a
    # *breaking* finding, dropping the project to D. It is a smoke script
    # explaining what it does.
    (tmp_path / "smoke_fetch.py").write_text(
        '"""Smoke test for the fetch tool.\n\n'
        "Runs the MCP handshake (initialize -> notifications/initialized) then calls\n"
        'tools/call and prints the result.\n"""\n\n'
        "import json\n\n\n"
        "def main():\n"
        "    print(json.dumps({}))\n"
    )
    findings = InitializeHandshakeStillImplemented().check(load_project(tmp_path))
    assert findings == [], (
        "a docstring explaining the handshake is documentation, not an "
        f"implementation: {[f.message for f in findings]}"
    )


def test_r009_still_fires_on_a_real_initialized_handler(tmp_path):
    # The literal in actual dispatch code must still be found -- this is
    # why the rule cannot simply use search_code.
    (tmp_path / "server.py").write_text(
        "def dispatch(method, params):\n"
        '    if method in ("notifications/initialized", "initialized"):\n'
        "        return None\n"
    )
    assert InitializeHandshakeStillImplemented().check(load_project(tmp_path))


def test_r004_does_not_fire_on_a_docstring_listing_http_routes(tmp_path):
    # chunxiaoxx/nautilus-compass: a module docstring describing the HTTP
    # surface read as a tool handler with no sort.
    (tmp_path / "compass_http.py").write_text(
        '"""Compass HTTP bridge.\n\n'
        "MCP-over-HTTP (POST /mcp/tools/call - POST /mcp/tools/list - POST /mcp/initialize)\n"
        '"""\n\n'
        "import json\n"
    )
    findings = NondeterministicToolOrder().check(load_project(tmp_path))
    assert findings == [], f"docstring is not a handler: {[f.message for f in findings]}"


def test_r005_does_not_fire_on_ordinary_variables_named_capabilities(tmp_path):
    # Three real shapes from the scan. None of them is MCP.
    (tmp_path / "backend.py").write_text(
        "from .caps import Capability\n\n\n"
        "class ClaudeBackend:\n"
        "    name = 'anthropic'\n"
        "    capabilities = {Capability.TEXT, Capability.VISION}\n\n\n"
        "def embed(model):\n"
        "    return dict(required_capabilities={Capability.EMBEDDINGS})\n\n\n"
        "Registry.update_capabilities = _update_capabilities\n"
    )
    findings = NoExtensionsDeclared().check(load_project(tmp_path))
    assert findings == [], (
        "`capabilities` is an ordinary identifier; only the SDK's own names "
        f"mean MCP capabilities here: {[f.message for f in findings]}"
    )


def test_r005_still_fires_on_a_real_declaration_without_extensions(tmp_path):
    (tmp_path / "server.py").write_text(
        "from mcp.types import ServerCapabilities, ToolsCapability\n\n"
        "caps = ServerCapabilities(tools=ToolsCapability())\n"
    )
    assert NoExtensionsDeclared().check(load_project(tmp_path))


def test_search_wire_keeps_string_literals_and_drops_prose(tmp_path):
    # The contract of the three-way split, asserted directly.
    (tmp_path / "m.py").write_text(
        '"""Explains resources/subscribe in a docstring."""\n'
        "# and again in a comment: resources/subscribe\n"
        'HANDLERS = {"resources/subscribe": None}\n'
    )
    project = load_project(tmp_path)
    hits = [ln for _f, ln, _t in project.search_wire("resources/subscribe")]
    assert hits == [3], f"expected only the dict literal on line 3, got {hits}"
    assert len(list(project.search("resources/subscribe"))) == 3
    assert list(project.search_code("resources/subscribe")) == []
