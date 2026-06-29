from __future__ import annotations

from typing import Any

from src.core.instagram_config import InstagramConfig
from src.integrations.instagram.client import InstagramClient


def build_instagram_client_from_credentials(
    credentials: dict[str, Any],
    *,
    client_factory=None,
    rupload_client_factory=None,
) -> InstagramClient:
    config = InstagramConfig.from_credentials(credentials)
    return InstagramClient(
        config,
        client_factory=client_factory,
        rupload_client_factory=rupload_client_factory,
    )
