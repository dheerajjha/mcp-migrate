"""Validate real `check --json` output against the checked-in JSON Schema."""
from __future__ import annotations

import json
from pathlib import Path

import jsonschema

from mcp_migrate.cli import main

ROOT = Path(__file__).resolve().parent.parent
SCHEMA = json.loads((ROOT / "schemas" / "check-json.schema.json").read_text(encoding="utf-8"))
FIXTURES = ROOT / "tests" / "fixtures"


def _validate(capsys, root: Path) -> dict:
    exit_code = main(["check", str(root), "--json"])
    payload = json.loads(capsys.readouterr().out)
    jsonschema.validate(payload, SCHEMA)
    return payload


def test_schema_validates_clean_output(capsys):
    payload = _validate(capsys, FIXTURES / "clean_server")
    assert payload["grade"] == "A"
    assert payload["findings"] == []


def test_schema_validates_finding_output(capsys):
    payload = _validate(capsys, FIXTURES / "legacy_server")
    assert payload["findings"]
    assert all("fix" not in finding or finding["fix"] for finding in payload["findings"])


def test_schema_validates_unscannable_output(capsys, tmp_path: Path):
    payload = _validate(capsys, tmp_path)
    assert payload["scannable"] is False
    assert payload["reason"]


def test_schema_validates_sdk_output(capsys, tmp_path: Path):
    (tmp_path / "pyproject.toml").write_text('[project]\nname = "mcp"\n', encoding="utf-8")
    (tmp_path / "server.py").write_text("import logging\nlogging.basicConfig()\n", encoding="utf-8")
    payload = _validate(capsys, tmp_path)
    assert payload["is_sdk"] is True
    assert payload["sdk_reason"]
