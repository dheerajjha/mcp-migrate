from mcp_migrate.rules.base import Fires, Silent
from mcp_migrate.rules.r016_cacheable_result_required import (
    CacheableResultMetadataMissing,
)


def test_r016_declares_executable_boundaries_for_each_supported_language():
    boundaries = CacheableResultMetadataMissing().boundaries

    assert boundaries
    for language in CacheableResultMetadataMissing.languages:
        language_boundaries = [
            boundary for boundary in boundaries if boundary.language == language
        ]
        assert any(isinstance(boundary, Fires) for boundary in language_boundaries)
        assert any(isinstance(boundary, Silent) for boundary in language_boundaries)
