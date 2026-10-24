"""R018's quoted correlation field is wire text, not an identifier."""
import json

import pytest

from mcp_migrate.cli import main
from mcp_migrate.rules.r018_multi_round_trip_replaces_server_initiated import (
    MultiRoundTripReplacesServerInitiated,
)
from mcp_migrate.scan import load_project


@pytest.mark.parametrize("language,source", [
    ("python", 'HELP = "elicitationId" + " is a removed correlation field."\n'),
    ("python", 'value = payload["elicitationId" + "Suffix"]\n'),
    ("python", 'value = payload["prefix" + "elicitationId"]\n'),
    ("python", 'value = payload["elicitationId" * 2]\n'),
    ("typescript", 'const help = "elicitationId" + " is a removed correlation field.";\n'),
    ("typescript", 'const value = params["elicitationId" + "Suffix"];\n'),
    ("typescript", 'const value = params["prefix" + "elicitationId"];\n'),
    ("typescript", 'const value = params[\n  "elicitationId"\n  + "Suffix"\n];\n'),
    ("typescript", 'const value = params["elicitationId" /* longer key */ + "Suffix"];\n'),
    ("typescript", 'const help = ("elicitationId") + " is old";\n'),
    ("typescript", 'const value = params["prefix" + ("elicitationId")];\n'),
    ("typescript", 'const value = params["prefix" + ((("elicitationId")))];\n'),
    ("typescript", 'const help = (("elicitationId")) /* fragment */ + " is old";\n'),
    ("typescript", 'const help = ("elicitationId" as const) + " is old";\n'),
    ("typescript", 'const value = params[("elicitationId" as string) + "Suffix"];\n'),
    ("typescript", 'const help = "elicitationId".concat(" is old");\n'),
    ("typescript", 'const help = "elicitationId" as string + " is old";\n'),
])
def test_concatenated_fragments_are_not_exact_wire_literals(tmp_path, language, source):
    suffix = ".py" if language == "python" else ".ts"
    (tmp_path / f"server{suffix}").write_text(source, encoding="utf-8")
    assert MultiRoundTripReplacesServerInitiated().check(
        load_project(tmp_path).for_language(language)
    ) == []


def test_concatenation_does_not_hide_a_separate_exact_key(tmp_path):
    (tmp_path / "server.ts").write_text(
        'const help = "elicitationId" + " is old"; params["elicitationId"];\n',
        encoding="utf-8",
    )
    findings = MultiRoundTripReplacesServerInitiated().check(
        load_project(tmp_path).for_language("typescript")
    )
    assert [(f.line, f.feature) for f in findings] == [(1, "elicitationId")]


def test_typescript_real_key_read_is_not_hidden_by_result_concatenation(tmp_path):
    (tmp_path / "server.ts").write_text(
        'const value = params.get("elicitationId") + ":suffix";\n', encoding="utf-8",
    )
    findings = MultiRoundTripReplacesServerInitiated().check(
        load_project(tmp_path).for_language("typescript")
    )
    assert [(f.line, f.feature) for f in findings] == [(1, "elicitationId")]


@pytest.mark.parametrize("language,source", [
    ("python", 'HELP = "elicitationId".join(["Use ", " for correlation."])\n'),
    ("python", 'value = payload["elicitationId".upper()]\n'),
    ("python", 'value = payload["elicitationId"[1:]]\n'),
    ("typescript", 'function help() { return ("elicitationId") + " is old"; }\n'),
    ("typescript", 'function help() { throw ("elicitationId") + " is old"; }\n'),
    ("typescript", 'function* help() { yield ("elicitationId") + " is old"; }\n'),
])
def test_transformed_literals_and_keyword_groups_are_not_wire_keys(tmp_path, language, source):
    suffix = ".py" if language == "python" else ".ts"
    (tmp_path / f"server{suffix}").write_text(source, encoding="utf-8")
    assert MultiRoundTripReplacesServerInitiated().check(
        load_project(tmp_path).for_language(language)
    ) == []


def test_python_real_key_transform_is_still_a_read(tmp_path):
    (tmp_path / "server.py").write_text(
        'value = payload["elicitationId"].upper()\n', encoding="utf-8",
    )
    findings = MultiRoundTripReplacesServerInitiated().check(
        load_project(tmp_path).for_language("python")
    )
    assert [(f.line, f.feature) for f in findings] == [(1, "elicitationId")]


@pytest.mark.parametrize("method", ["set", "has", "delete"])
def test_typescript_key_methods_still_fire(tmp_path, method):
    (tmp_path / "server.ts").write_text(
        f'params.{method}("elicitationId", value);\n', encoding="utf-8",
    )
    findings = MultiRoundTripReplacesServerInitiated().check(
        load_project(tmp_path).for_language("typescript")
    )
    assert [(f.line, f.feature) for f in findings] == [(1, "elicitationId")]


@pytest.mark.parametrize("language,quote", [
    ("python", '"'),
    ("python", "'"),
    ("typescript", '"'),
    ("typescript", "'"),
    ("typescript", "`"),
])
def test_quoted_elicitation_id_fires_without_an_mcp_context_gate(tmp_path, language, quote):
    suffix = ".py" if language == "python" else ".ts"
    source = (
        f"pending.pop(payload[{quote}elicitationId{quote}])\n"
        if language == "python"
        else f"const eid = params[{quote}elicitationId{quote}];\n"
    )
    (tmp_path / f"server{suffix}").write_text(source, encoding="utf-8")

    findings = MultiRoundTripReplacesServerInitiated().check(
        load_project(tmp_path).for_language(language)
    )

    assert [(f.path.name, f.line, f.feature) for f in findings] == [
        (f"server{suffix}", 1, "elicitationId")
    ]
    assert findings[0].rule_id == "R018"
    assert findings[0].snippet == source.strip()


@pytest.mark.parametrize("language", ["python", "typescript"])
def test_identifier_and_quoted_key_are_deduplicated_per_file_and_line(tmp_path, language):
    suffix = ".py" if language == "python" else ".ts"
    source = (
        'elicitationId = payload["elicitationId"]\n'
        "pending.pop(payload['elicitationId'])\n"
        if language == "python"
        else 'const elicitationId = params["elicitationId"];\n'
        "const eid = params['elicitationId'];\n"
    )
    for stem in ("one", "two"):
        (tmp_path / f"{stem}{suffix}").write_text(source, encoding="utf-8")

    findings = MultiRoundTripReplacesServerInitiated().check(
        load_project(tmp_path).for_language(language)
    )

    assert sorted((f.path.name, f.line) for f in findings) == [
        (f"{stem}{suffix}", line) for stem in ("one", "two") for line in (1, 2)
    ]
    assert all(f.feature == "elicitationId" for f in findings)


@pytest.mark.parametrize("language,source", [
    ("python", '# payload["elicitationId"]\n'),
    ("python", '\'\'\'Read payload["elicitationId"] before migrating.\'\'\'\n'),
    ("python", 'HELP = "Use elicitationId to correlate responses."\n'),
    ("python", 'value = payload["elicitationIdSuffix"]\n'),
    ("python", 'value = payload["prefixelicitationId"]\n'),
    ("python", 'value = payload["ElicitationId"]\n'),
    ("python", 'HELP = "Use \'elicitationId\' to correlate responses."\n'),
    ("python", 'HELP = "Read payload[\'elicitationId\'] before migrating."\n'),
    ("python", 'value = payload["elicitationId\'s"]\n'),
    ("python", 'value = payload[\'elicitationId"suffix\']\n'),
    ("python", 'def describe():\n    "elicitationId"\n    pass\n'),
    ("python", 'class Description:\n    "elicitationId"\n    pass\n'),
    ("python", 'def describe():\n    ("elicitationId")\n    pass\n'),
    ("python", 'def describe():\n    (\n        "elicitationId"\n    )\n    pass\n'),
    ("python", 'class Description:\n    ("elicitationId")\n    pass\n'),
    ("python", '("elicitationId")\n'),
    ("python", '\'elici\' "tationId"\n'),
    ("python", 'HELP = f"elicitationId{suffix}"\n'),
    ("python", 'HELP = f"{prefix}elicitationId"\n'),
    ("typescript", '// params["elicitationId"]\n'),
    ("typescript", '/* params["elicitationId"] */\n'),
    ("typescript", 'const help = "Use elicitationId to correlate responses.";\n'),
    ("typescript", 'const help = `Use elicitationId to correlate responses.`;\n'),
    ("typescript", 'const value = params["elicitationIdSuffix"];\n'),
    ("typescript", 'const value = params["prefixelicitationId"];\n'),
    ("typescript", 'const value = params["ElicitationId"];\n'),
    ("typescript", 'const help = "Use \'elicitationId\' to correlate responses.";\n'),
    ("typescript", 'const help = "Read params[\'elicitationId\'] before migrating.";\n'),
    ("typescript", 'const value = params["elicitationId\'s"];\n'),
    ("typescript", 'const value = params[\'elicitationId"suffix\'];\n'),
])
def test_prose_and_other_keys_stay_silent(tmp_path, language, source):
    suffix = ".py" if language == "python" else ".ts"
    (tmp_path / f"server{suffix}").write_text(source, encoding="utf-8")
    assert MultiRoundTripReplacesServerInitiated().check(
        load_project(tmp_path).for_language(language)
    ) == []


@pytest.mark.parametrize("language,source,line", [
    ("python", 'payload = {"elicitationId": value}\n', 1),
    ("python", 'value = payload.get("elicitationId")\n', 1),
    ("python", 'value = payload[\n    "elicitationId"\n]\n', 2),
    ("python", 'value = payload[r"elicitationId"]\n', 1),
    ("python", 'value = payload[\n"elicitationId"\n]\n', 2),
    ("python", 'value = f"{payload[\'elicitationId\']}"\n', 1),
    ("typescript", 'const payload = {"elicitationId": value};\n', 1),
    ("typescript", 'const value = params.get("elicitationId");\n', 1),
    ("typescript", 'const value = params[\n    "elicitationId"\n];\n', 2),
    ("typescript", 'const value = params[\n"elicitationId"\n];\n', 2),
])
def test_quoted_keys_and_arguments_in_code(tmp_path, language, source, line):
    suffix = ".py" if language == "python" else ".ts"
    (tmp_path / f"server{suffix}").write_text(source, encoding="utf-8")
    findings = MultiRoundTripReplacesServerInitiated().check(
        load_project(tmp_path).for_language(language)
    )
    assert [(f.line, f.feature) for f in findings] == [(line, "elicitationId")]


@pytest.mark.parametrize("language", ["python", "typescript"])
def test_distinct_features_on_the_same_line_are_preserved(tmp_path, language):
    suffix = ".py" if language == "python" else ".ts"
    source = (
        'CreateMessageRequest; payload["elicitationId"]\n'
        if language == "python"
        else 'CreateMessageRequestSchema; params["elicitationId"];\n'
    )
    (tmp_path / f"server{suffix}").write_text(source, encoding="utf-8")

    findings = MultiRoundTripReplacesServerInitiated().check(
        load_project(tmp_path).for_language(language)
    )

    assert [(f.line, f.feature) for f in findings] == [
        (1, "Server-initiated sampling/createMessage"),
        (1, "elicitationId"),
    ]


@pytest.mark.parametrize("language", ["python", "typescript"])
def test_quoted_elicitation_id_is_reported_by_the_actual_cli(tmp_path, capsys, language):
    suffix = ".py" if language == "python" else ".ts"
    source = (
        'from mcp.server.lowlevel import Server\n'
        'server = Server("demo")\n'
        'pending = {}\n'
        'def on_complete(payload):\n'
        '    return pending.pop(payload["elicitationId"])\n'
        if language == "python"
        else 'import { Server } from "@modelcontextprotocol/sdk/server/index.js";\n'
        'const server = new Server({ name: "demo", version: "1.0.0" });\n'
        'const eid = params["elicitationId"];\n'
    )
    (tmp_path / f"server{suffix}").write_text(source, encoding="utf-8")

    assert main(["check", str(tmp_path), "--json"]) == 1
    report = json.loads(capsys.readouterr().out)
    if language == "python":
        assert (report["grade"], report["score"]) == ("C", 75)
    else:
        # TypeScript grading is deliberately withheld pending the #172 decision.
        assert (report["grade"], report["score"]) == (None, None)
        assert report["scannable"] is False
        assert "172" in report["reason"]
    assert report["counts"]["breaking"] == 1
    assert [(f["rule"], f["line"]) for f in report["findings"]] == [
        ("R018", 5 if language == "python" else 3)
    ]
