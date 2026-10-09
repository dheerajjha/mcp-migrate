from mcp_migrate.rules.base import Fires, Silent
from mcp_migrate.rules.r013_subscriptions_replaced import (
    ResourceSubscriptionsReplaced,
)


def test_r013_declares_executable_boundaries_for_each_supported_language():
    boundaries = ResourceSubscriptionsReplaced().boundaries

    assert boundaries
    for language in ResourceSubscriptionsReplaced.languages:
        language_boundaries = [
            boundary for boundary in boundaries if boundary.language == language
        ]
        assert any(isinstance(boundary, Fires) for boundary in language_boundaries)
        assert any(isinstance(boundary, Silent) for boundary in language_boundaries)
