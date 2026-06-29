from __future__ import annotations

from urllib.parse import urljoin

from src.core.config import settings


def is_public_url(value: str | None) -> bool:
    if not value:
        return False
    return value.startswith(("http://", "https://"))


def resolve_public_video_url(video_path: str | None) -> str | None:
    """Resolve video_path to a publicly accessible URL.

    Returns the path unchanged when it is already an http(s) URL. When
    ``PUBLIC_MEDIA_BASE_URL`` is configured, local/relative paths are joined
    against that base (e.g. ``/storage/videos/1.mp4`` → CDN URL).
    """
    if not video_path:
        return None
    if is_public_url(video_path):
        return video_path

    base_url = settings.PUBLIC_MEDIA_BASE_URL
    if not base_url:
        return None

    base = base_url.rstrip("/") + "/"
    relative = video_path.lstrip("/")
    return urljoin(base, relative)
