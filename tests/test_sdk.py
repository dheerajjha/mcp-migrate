"""Tests for SDK detection and graceful no-grade handling in mcp-migrate."""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

from mcp_migrate.cli import cmd_check
from mcp_migrate.sdk import SdkInfo, detect_sdk


def test_detect_sdk_python_mcp(tmp_path: Path):
    pyproject = tmp_path / "pyproject.toml"
    pyproject.write_text('[project]\nname = "mcp"\nversion = "1.0.0"\n', encoding="utf-8")
    info = detect_sdk(tmp_path)
    assert info.is_sdk is True
    assert info.package_name == "mcp"
    assert "mcp" in info.reason


def test_detect_sdk_fastmcp(tmp_path: Path):
    pyproject = tmp_path / "pyproject.toml"
    pyproject.write_text('[project]\nname = "fastmcp"\nversion = "0.2.0"\n', encoding="utf-8")
    info = detect_sdk(tmp_path)
    assert info.is_sdk is True
    assert info.package_name == "fastmcp"


def test_detect_sdk_typescript(tmp_path: Path):
    pkg_json = tmp_path / "package.json"
    pkg_json.write_text('{"name": "@modelcontextprotocol/sdk", "version": "1.0.0"}', encoding="utf-8")
    info = detect_sdk(tmp_path)
    assert info.is_sdk is True
    assert info.package_name == "@modelcontextprotocol/sdk"


def test_detect_sdk_opt_out_pyproject(tmp_path: Path):
    pyproject = tmp_path / "pyproject.toml"
    pyproject.write_text('[project]\nname = "custom-lib"\n\n[tool.mcp-migrate]\nis_sdk = true\n', encoding="utf-8")
    info = detect_sdk(tmp_path)
    assert info.is_sdk is True


def test_detect_sdk_opt_out_package_json(tmp_path: Path):
    pkg_json = tmp_path / "package.json"
    pkg_json.write_text('{"name": "custom-ts-lib", "mcpMigrate": {"isSdk": true}}', encoding="utf-8")
    info = detect_sdk(tmp_path)
    assert info.is_sdk is True


def test_detect_sdk_normal_server(tmp_path: Path):
    pyproject = tmp_path / "pyproject.toml"
    pyproject.write_text('[project]\nname = "mcp_server_postgres"\nversion = "1.0.0"\n', encoding="utf-8")
    info = detect_sdk(tmp_path)
    assert info.is_sdk is False


class DummyArgs:
    def __init__(self, path: Path, json_output: bool = False, include_tests: bool = False):
        self.path = str(path)
        self.json = json_output
        self.include_tests = include_tests


def test_cli_check_sdk_json_output(tmp_path: Path, capsys):
    pyproject = tmp_path / "pyproject.toml"
    pyproject.write_text('[project]\nname = "mcp"\n', encoding="utf-8")
    server_file = tmp_path / "server.py"
    server_file.write_text('import logging\nlogging.basicConfig()\n', encoding="utf-8")

    args = DummyArgs(tmp_path, json_output=True)
    exit_code = cmd_check(args)

    assert exit_code == 0
    captured = capsys.readouterr()
    data = json.loads(captured.out)
    assert data["scannable"] is True
    assert data["is_sdk"] is True
    assert data["grade"] is None
    assert data["score"] is None


def test_cli_check_normal_server_graded(tmp_path: Path, capsys):
    pyproject = tmp_path / "pyproject.toml"
    pyproject.write_text('[project]\nname = "my_mcp_server"\n', encoding="utf-8")
    server_file = tmp_path / "server.py"
    server_file.write_text('import logging\nlogging.basicConfig()\n', encoding="utf-8")

    args = DummyArgs(tmp_path, json_output=True)
    exit_code = cmd_check(args)

    assert exit_code == 0
    captured = capsys.readouterr()
    data = json.loads(captured.out)
    assert data["scannable"] is True
    assert "is_sdk" not in data or data.get("is_sdk") is not True
    assert data["grade"] == "A"
    assert data["score"] == 100


def test_cli_check_sdk_terminal_output(tmp_path: Path, capsys):
    pyproject = tmp_path / "pyproject.toml"
    pyproject.write_text('[project]\nname = "mcp"\n', encoding="utf-8")
    server_file = tmp_path / "server.py"
    server_file.write_text('import logging\nlogging.basicConfig()\n', encoding="utf-8")

    args = DummyArgs(tmp_path, json_output=False)
    exit_code = cmd_check(args)

    assert exit_code == 0
    captured = capsys.readouterr()
    assert "No grade:" in captured.out
    assert "protocol SDK" in captured.out
    assert 'package name "mcp"' in captured.out
