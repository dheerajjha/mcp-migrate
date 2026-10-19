from mcp_migrate.rules.base import Fires, Silent
from mcp_migrate.rules.r002_connection_state import PerConnectionState


def test_r002_declares_executable_boundaries_for_each_supported_language():
    boundaries = PerConnectionState().boundaries

    assert boundaries
    for language in PerConnectionState.languages:
        language_boundaries = [
            boundary for boundary in boundaries if boundary.language == language
        ]
        assert any(isinstance(boundary, Fires) for boundary in language_boundaries)
        assert any(isinstance(boundary, Silent) for boundary in language_boundaries)
