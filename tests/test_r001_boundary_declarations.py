from mcp_migrate.rules.base import Fires, Silent
from mcp_migrate.rules.r001_session_id_removed import SessionIdRemoved


def test_r001_declares_executable_boundaries_for_each_supported_language():
    rule = SessionIdRemoved()

    assert rule.boundaries
    for language in rule.languages:
        language_boundaries = [
            boundary for boundary in rule.boundaries if boundary.language == language
        ]
        assert any(isinstance(boundary, Fires) for boundary in language_boundaries)
        assert any(isinstance(boundary, Silent) for boundary in language_boundaries)
