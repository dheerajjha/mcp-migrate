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


# --- which version of the Python SDK a project asks for -------------------
#
# Needed because `server/discover` is not something a 2.x project writes:
# `Server.__init__` registers it, so an absence check against the project's
# own source reports a gap that does not exist. See #257.
#
# This reads the *declared* floor, not the resolved one. A lockfile would be
# authoritative and this is not; the difference is why "undeterminable"
# returns None and callers are expected to stay silent rather than guess.

# `mcp`, optionally with extras, then the first version-like constraint.
# Deliberately not a full PEP 508 parser: the only question is "does this
# project ask for at least 2.0", and anything this cannot answer becomes
# None, which callers treat as "do not fire".
_MCP_REQ_RX = re.compile(
    r"""^\s*mcp                         # the package, exactly
        (?:\[[^\]]*\])?                 # optional extras: mcp[cli]
        \s*(?P<op>==|>=|~=|\^|>)        # the constraint we can read a floor from
        \s*v?(?P<ver>\d+(?:\.\d+)*)     # 2, 2.0, 2.1.1
    """,
    re.VERBOSE | re.IGNORECASE,
)


def _version_tuple(text: str) -> tuple[int, ...]:
    return tuple(int(p) for p in text.split("."))


def _floor_from_requirement(spec: str) -> tuple[int, ...] | None:
    """The lower bound a single requirement string puts on `mcp`, if any.

    `<` and `!=` are deliberately unreadable here: `mcp<3` says nothing
    about the floor, and treating it as one would be inventing a number.
    """
    m = _MCP_REQ_RX.match(spec.strip())
    if not m:
        return None
    try:
        return _version_tuple(m.group("ver"))
    except ValueError:
        return None


def declared_mcp_floor(root: Path) -> tuple[int, ...] | None:
    """The lowest version of the Python `mcp` SDK this project accepts.

    None when the project does not depend on `mcp`, pins it without a
    readable lower bound (`mcp`, `mcp<3`), or cannot be parsed. Callers
    must treat None as "unknown", never as "old".
    """
    if not root.is_dir():
        return None

    candidates: list[str] = []

    pyproject = root / "pyproject.toml"
    if pyproject.is_file():
        try:
            content = pyproject.read_text(encoding="utf-8", errors="replace")
        except OSError:
            content = ""
        if content:
            parsed = False
            if tomllib:
                try:
                    data = tomllib.loads(content)
                    parsed = isinstance(data, dict)
                except Exception:
                    parsed = False
                if parsed:
                    project_table = data.get("project")
                    if isinstance(project_table, dict):
                        deps = project_table.get("dependencies")
                        if isinstance(deps, list):
                            candidates += [d for d in deps if isinstance(d, str)]
                        optional = project_table.get("optional-dependencies")
                        if isinstance(optional, dict):
                            for group in optional.values():
                                if isinstance(group, list):
                                    candidates += [d for d in group if isinstance(d, str)]
                    tool = data.get("tool")
                    if isinstance(tool, dict):
                        poetry = tool.get("poetry")
                        if isinstance(poetry, dict):
                            pdeps = poetry.get("dependencies")
                            if isinstance(pdeps, dict):
                                for name, spec in pdeps.items():
                                    if str(name).strip().lower() != "mcp":
                                        continue
                                    if isinstance(spec, str):
                                        candidates.append(f"mcp{spec}")
                                    elif isinstance(spec, dict) and isinstance(spec.get("version"), str):
                                        candidates.append(f"mcp{spec['version']}")
            if not parsed:
                # No tomllib (3.10 without tomli) or unparseable TOML. Reading
                # requirement-shaped lines out of the raw text is strictly
                # better than answering None for every 3.10 user.
                candidates += re.findall(r'["\']\s*(mcp(?:\[[^\]]*\])?[^"\']*)["\']', content)

    for name in ("requirements.txt", "requirements/base.txt", "requirements-dev.txt"):
        req = root / name
        if req.is_file():
            try:
                candidates += req.read_text(encoding="utf-8", errors="replace").splitlines()
            except OSError:
                pass

    floors = [f for f in (_floor_from_requirement(c) for c in candidates) if f]
    if not floors:
        return None
    # The highest declared floor wins: a project listing `mcp>=1.2` in one
    # place and `mcp>=2.1` in another cannot resolve below 2.1.
    return max(floors)
