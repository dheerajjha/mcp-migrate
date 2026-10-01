from pathlib import Path

import pytest

from mcp_migrate.rules.base import Fires, Project, Silent, SourceFile
from mcp_migrate.rules import all_rules


def _project(snippet: str, language: str) -> Project:
    extension = {
        "python": ".py",
        "javascript": ".js",
        "typescript": ".ts",
    }[language]

    return Project(
        root=Path("."),
        files=[
            SourceFile(
                path=Path(f"server{extension}"),
                text=snippet,
                language=language,
            )
        ],
    )


@pytest.mark.parametrize(
    "rule",
    [rule for rule in all_rules() if rule.boundaries],
    ids=lambda rule: rule.id,
)
def test_rule_boundaries(rule):
    for boundary in rule.boundaries:
        project = _project(boundary.snippet, boundary.language)
        findings = rule.check(project)

        if isinstance(boundary, Fires):
            assert findings, (
                f"{rule.id} should fire for: {boundary.snippet!r}"
            )
        elif isinstance(boundary, Silent):
            assert not findings, (
                f"{rule.id} should remain silent for: {boundary.snippet!r}"
            )