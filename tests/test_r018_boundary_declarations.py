from mcp_migrate.rules.base import Fires, Silent
from mcp_migrate.rules.r018_multi_round_trip_replaces_server_initiated import (
    MultiRoundTripReplacesServerInitiated,
)


def test_r018_declares_executable_boundaries_for_each_supported_language():
    boundaries = MultiRoundTripReplacesServerInitiated().boundaries

    assert boundaries
    for language in MultiRoundTripReplacesServerInitiated.languages:
        language_boundaries = [
            boundary for boundary in boundaries if boundary.language == language
        ]
        assert any(isinstance(boundary, Fires) for boundary in language_boundaries)
        assert any(isinstance(boundary, Silent) for boundary in language_boundaries)
