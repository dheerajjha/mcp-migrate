from mcp_migrate.rules.base import Fires, Silent
from mcp_migrate.rules.r012_logging_set_level_removed import LoggingSetLevelRemoved


def test_r012_declares_executable_boundaries_for_each_supported_language():
    boundaries = LoggingSetLevelRemoved().boundaries

    assert boundaries
    for language in LoggingSetLevelRemoved.languages:
        language_boundaries = [
            boundary for boundary in boundaries if boundary.language == language
        ]
        assert any(isinstance(boundary, Fires) for boundary in language_boundaries)
        assert any(isinstance(boundary, Silent) for boundary in language_boundaries)
