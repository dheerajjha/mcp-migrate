from mcp_migrate.rules.base import Fires, Silent
from mcp_migrate.rules.r014_sse_resumability_removed import (
    SSEResumabilityRemoved,
)


def test_r014_declares_executable_boundaries_for_each_supported_language():
    boundaries = SSEResumabilityRemoved().boundaries

    assert boundaries
    for language in SSEResumabilityRemoved.languages:
        language_boundaries = [
            boundary for boundary in boundaries if boundary.language == language
        ]
        assert any(isinstance(boundary, Fires) for boundary in language_boundaries)
        assert any(isinstance(boundary, Silent) for boundary in language_boundaries)
