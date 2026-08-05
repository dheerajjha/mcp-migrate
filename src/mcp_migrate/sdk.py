"""Detection of MCP Protocol SDKs and libraries to prevent category-error grading."""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import NamedTuple

try:
    import tomllib
except ImportError:
    try:
        import tomli as tomllib  # type: ignore
    except ImportError:
        tomllib = None  # Fallback regex parser for Python 3.10 if tomli is absent

KNOWN_SDK_PACKAGES = {
    "mcp",
    "fastmcp",
    "@modelcontextprotocol/sdk",
    "modelcontextprotocol",
}


class SdkInfo(NamedTuple):
    is_sdk: bool
    package_name: str | None = None
    reason: str | None = None


def detect_sdk(root: Path) -> SdkInfo:
    """Check if `root` is a known MCP Protocol SDK or explicitly configured as a library/SDK.

    Fails toward silence: returns SdkInfo(is_sdk=False) if uncertain.
    """
    if not root.is_dir():
        return SdkInfo(is_sdk=False)

    # 1. Check pyproject.toml (Python)
    pyproject_path = root / "pyproject.toml"
    if pyproject_path.is_file():
        try:
            content = pyproject_path.read_text(encoding="utf-8", errors="replace")
            name = None
            is_sdk_config = False

            if tomllib:
                try:
                    data = tomllib.loads(content)
                    if isinstance(data, dict):
                        project_table = data.get("project")
                        if isinstance(project_table, dict):
                            name = project_table.get("name")
                        if not name:
                            tool_table = data.get("tool")
                            if isinstance(tool_table, dict):
                                poetry = tool_table.get("poetry")
                                if isinstance(poetry, dict):
                                    name = poetry.get("name")
                                flit = tool_table.get("flit")
                                if isinstance(flit, dict) and isinstance(flit.get("metadata"), dict):
                                    name = flit["metadata"].get("name")

                        tool_table = data.get("tool")
                        if isinstance(tool_table, dict):
                            mcp_mig = tool_table.get("mcp-migrate") or tool_table.get("mcp_migrate")
                            if isinstance(mcp_mig, dict):
                                is_sdk_config = bool(
                                    mcp_mig.get("is_sdk") or mcp_mig.get("is-sdk") or mcp_mig.get("sdk")
                                )
                except Exception:
                    pass

            if not name:
                m = re.search(r'^\s*name\s*=\s*["\']([^"\']+)["\']', content, re.MULTILINE)
                if m:
                    name = m.group(1)

            if not is_sdk_config:
                m_opt = re.search(r'\[tool\.mcp[-_]migrate\][^\[]*?\bis[-_]?sdk\s*=\s*true', content, re.MULTILINE | re.IGNORECASE)
                if m_opt:
                    is_sdk_config = True

            if is_sdk_config:
                return SdkInfo(is_sdk=True, package_name=name, reason="explicit config in pyproject.toml")

            if name and isinstance(name, str) and name.strip().lower() in KNOWN_SDK_PACKAGES:
                return SdkInfo(is_sdk=True, package_name=name.strip(), reason=f'package name "{name.strip()}"')
        except OSError:
            pass

    # 2. Check package.json (TypeScript / Node.js)
    package_json_path = root / "package.json"
    if package_json_path.is_file():
        try:
            content = package_json_path.read_text(encoding="utf-8", errors="replace")
            data = json.loads(content)
            if isinstance(data, dict):
                name = data.get("name")
                mcp_mig = data.get("mcpMigrate") or data.get("mcp-migrate")
                is_sdk_config = False
                if isinstance(mcp_mig, dict):
                    is_sdk_config = bool(
                        mcp_mig.get("isSdk") or mcp_mig.get("is-sdk") or mcp_mig.get("sdk")
                    )
                elif data.get("isSdk") or data.get("is-sdk"):
                    is_sdk_config = True

                if is_sdk_config:
                    return SdkInfo(is_sdk=True, package_name=name, reason="explicit config in package.json")

                if name and isinstance(name, str) and name.strip().lower() in KNOWN_SDK_PACKAGES:
                    return SdkInfo(is_sdk=True, package_name=name.strip(), reason=f'package name "{name.strip()}"')
        except (OSError, json.JSONDecodeError):
            pass

    return SdkInfo(is_sdk=False)
