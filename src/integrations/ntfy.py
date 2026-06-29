from __future__ import annotations

import json
import logging
from typing import Any

import httpx

from src.core.config import settings
from src.core.enums import PlatformType
from src.models.pipeline_run import PipelineRun
from src.pipeline.state import PipelineState
from src.schemas.channel_digest import ChannelDigestOut
from src.services.media_url import resolve_public_video_url

logger = logging.getLogger(__name__)

_PLATFORM_LABELS: dict[str, str] = {
    PlatformType.YOUTUBE_SHORTS.value: "YouTube Shorts",
    PlatformType.TIKTOK.value: "TikTok",
    PlatformType.INSTAGRAM.value: "Instagram",
}


def _ascii_header(value: str) -> str:
    return value.encode("ascii", "replace").decode("ascii")


def _is_configured() -> bool:
    return bool(
        settings.NTFY_ENABLED
        and settings.NTFY_BASE_URL.strip()
        and settings.NTFY_TOPIC.strip()
    )


def _resolve_channel_name(state: PipelineState) -> str:
    channel_context = state.get("channel_context")
    if isinstance(channel_context, dict):
        name = channel_context.get("name")
        if isinstance(name, str) and name.strip():
            return name.strip()
    channel_id = state.get("channel_id")
    if channel_id is not None:
        return f"channel-{channel_id}"
    return "unknown"


def _resolve_video_title(state: PipelineState) -> str | None:
    for key in ("video_script", "video_idea"):
        payload = state.get(key)
        if isinstance(payload, dict):
            title = payload.get("title")
            if isinstance(title, str) and title.strip():
                return title.strip()
    return None


def _resolve_hook(state: PipelineState) -> str | None:
    idea = state.get("video_idea")
    if isinstance(idea, dict):
        hook = idea.get("hook")
        if isinstance(hook, str) and hook.strip():
            return hook.strip()
    return None


def _normalize_platform(platform: str) -> str:
    return platform.lower().replace("-", "_")


def _build_platform_url(platform: str, platform_video_id: str) -> str | None:
    if not platform_video_id.strip():
        return None

    normalized = _normalize_platform(platform)
    if normalized in {PlatformType.YOUTUBE_SHORTS.value, "youtube"}:
        return f"https://youtube.com/shorts/{platform_video_id}"
    if normalized == PlatformType.TIKTOK.value:
        return f"https://www.tiktok.com/video/{platform_video_id}"
    if normalized == PlatformType.INSTAGRAM.value:
        return f"https://www.instagram.com/reel/{platform_video_id}/"
    return None


def _platform_label(platform: str) -> str:
    normalized = _normalize_platform(platform)
    return _PLATFORM_LABELS.get(normalized, platform)


def _format_publish_line(result: dict[str, Any]) -> str:
    platform = str(result.get("platform", "unknown"))
    label = _platform_label(platform)
    if result.get("success"):
        platform_video_id = result.get("platform_video_id")
        if platform_video_id:
            url = _build_platform_url(platform, str(platform_video_id))
            if url:
                return f"{label}: {url}"
        return f"{label}: OK"
    error = result.get("error") or "failed"
    return f"{label}: FAIL ({error})"


def _resolve_notification_tag(
    state: PipelineState,
    *,
    pipeline_error: str | None,
) -> str:
    if pipeline_error:
        return "x"
    if state.get("errors"):
        return "warning"
    publish_results = state.get("publish_results") or []
    if publish_results and any(not item.get("success") for item in publish_results):
        return "warning"
    if _is_full_success(state, pipeline_error=pipeline_error):
        return "white_check_mark"
    return "warning"


def _is_full_success(
    state: PipelineState,
    *,
    pipeline_error: str | None,
) -> bool:
    if pipeline_error:
        return False
    if state.get("errors"):
        return False
    if state.get("current_step") != "publish":
        return False
    if state.get("video_metadata_id") is None:
        return False
    publish_results = state.get("publish_results") or []
    if publish_results and any(not item.get("success") for item in publish_results):
        return False
    return True


def should_send_pipeline_notification(
    state: PipelineState,
    *,
    pipeline_error: str | None,
) -> bool:
    if pipeline_error:
        return True
    if state.get("errors"):
        return True
    return not _is_full_success(state, pipeline_error=pipeline_error)


def _resolve_title(
    state: PipelineState,
    *,
    pipeline_error: str | None,
) -> str:
    video_title = _resolve_video_title(state)
    channel_name = _resolve_channel_name(state)
    if pipeline_error:
        return f"Error: {channel_name}"
    if _is_full_success(state, pipeline_error=pipeline_error):
        if video_title:
            return f"Complete: {video_title}"
        return f"Complete: {channel_name}"
    if video_title:
        return f"Partial: {video_title}"
    return f"Partial: {channel_name}"


def _resolve_click_url(state: PipelineState) -> str | None:
    for result in state.get("publish_results") or []:
        if not isinstance(result, dict) or not result.get("success"):
            continue
        platform_video_id = result.get("platform_video_id")
        platform = result.get("platform")
        if not platform or not platform_video_id:
            continue
        url = _build_platform_url(str(platform), str(platform_video_id))
        if url:
            return url
    return resolve_public_video_url(state.get("video_path"))


def _build_actions_header(state: PipelineState) -> str | None:
    actions: list[dict[str, str]] = []
    for result in state.get("publish_results") or []:
        if not isinstance(result, dict) or not result.get("success"):
            continue
        platform = result.get("platform")
        platform_video_id = result.get("platform_video_id")
        if not platform or not platform_video_id:
            continue
        url = _build_platform_url(str(platform), str(platform_video_id))
        if not url:
            continue
        actions.append(
            {
                "action": "view",
                "label": _platform_label(str(platform)),
                "url": url,
            }
        )

    public_video_url = resolve_public_video_url(state.get("video_path"))
    if public_video_url and not any(
        action["url"] == public_video_url for action in actions
    ):
        actions.append(
            {"action": "view", "label": "Video file", "url": public_video_url}
        )

    if not actions:
        return None
    return json.dumps(actions)


def _format_pipeline_message(
    state: PipelineState,
    *,
    pipeline_error: str | None,
) -> str:
    lines = [f"Kanal: {_resolve_channel_name(state)}"]

    video_title = _resolve_video_title(state)
    if video_title:
        lines.append(f"Video: {video_title}")

    hook = _resolve_hook(state)
    if hook:
        lines.append(f"Hook: {hook}")

    idea_score = state.get("idea_score")
    if idea_score is not None:
        lines.append(f"Fikir skoru: {idea_score}/10")

    video_metadata_id = state.get("video_metadata_id")
    if video_metadata_id is not None:
        lines.append(f"Video ID: {video_metadata_id}")

    video_path = state.get("video_path")
    if video_path:
        public_url = resolve_public_video_url(video_path)
        if public_url:
            lines.append(f"Video dosyası: {public_url}")
        else:
            lines.append(f"Dosya: {video_path}")

    publish_results = state.get("publish_results") or []
    if publish_results:
        lines.append("")
        lines.append("Yayın:")
        for result in publish_results:
            if isinstance(result, dict):
                lines.append(_format_publish_line(result))

    lines.extend(
        [
            "",
            f"Run ID: {state.get('run_id', '-')}",
            f"Adım: {state.get('current_step', '-')}",
        ]
    )

    state_errors = state.get("errors") or []
    for error in state_errors:
        lines.append(f"Hata: {error}")

    if pipeline_error:
        lines.append(f"Exception: {pipeline_error}")

    return "\n".join(lines)


def _build_notification_headers(
    state: PipelineState,
    *,
    pipeline_error: str | None,
) -> dict[str, str]:
    headers = {
        "Title": _ascii_header(_resolve_title(state, pipeline_error=pipeline_error)),
        "Tags": _ascii_header(
            _resolve_notification_tag(state, pipeline_error=pipeline_error)
        ),
        "Priority": "default",
    }

    click_url = _resolve_click_url(state)
    if click_url:
        headers["Click"] = click_url

    actions = _build_actions_header(state)
    if actions:
        headers["Actions"] = actions

    return headers


async def send_pipeline_notification(
    state: PipelineState,
    *,
    pipeline_error: str | None = None,
) -> None:
    if not _is_configured():
        return

    base_url = settings.NTFY_BASE_URL.rstrip("/")
    topic = settings.NTFY_TOPIC.strip()
    url = f"{base_url}/{topic}"
    message = _format_pipeline_message(state, pipeline_error=pipeline_error)
    headers = _build_notification_headers(state, pipeline_error=pipeline_error)

    try:
        async with httpx.AsyncClient(timeout=settings.NTFY_REQUEST_TIMEOUT) as client:
            response = await client.post(
                url,
                content=message.encode("utf-8"),
                headers=headers,
            )
            response.raise_for_status()
        logger.info(
            "ntfy notification sent channel=%s step=%s",
            _resolve_channel_name(state),
            state.get("current_step"),
        )
    except Exception:
        logger.warning(
            "ntfy notification failed channel=%s step=%s",
            _resolve_channel_name(state),
            state.get("current_step"),
            exc_info=True,
        )


def _pipeline_run_channel_label(run: PipelineRun) -> str:
    return f"channel-{run.channel_id}"


def _format_pipeline_run_message(run: PipelineRun, *, headline: str) -> str:
    lines = [
        headline,
        f"Kanal: {_pipeline_run_channel_label(run)}",
        f"Run ID: {run.id}",
        f"Durum: {run.status}",
        f"Adım: {run.current_step or '-'}",
        f"Retry: {run.retry_count}",
    ]
    if run.last_error:
        lines.append(f"Hata: {run.last_error}")
    return "\n".join(lines)


async def _send_pipeline_ops_alert(
    *,
    title: str,
    message: str,
    tags: str,
    priority: str = "high",
) -> None:
    if not _is_configured():
        return

    url = f"{settings.NTFY_BASE_URL.rstrip('/')}/{settings.NTFY_TOPIC.strip()}"
    try:
        async with httpx.AsyncClient(timeout=settings.NTFY_REQUEST_TIMEOUT) as client:
            response = await client.post(
                url,
                content=message.encode("utf-8"),
                headers={
                    "Title": _ascii_header(title),
                    "Tags": tags,
                    "Priority": priority,
                },
            )
            response.raise_for_status()
    except Exception:
        logger.warning("ntfy pipeline ops alert failed title=%s", title, exc_info=True)


async def send_pipeline_stale_alert(run: PipelineRun) -> None:
    message = _format_pipeline_run_message(
        run,
        headline=(
            f"Pipeline stale: no heartbeat for {settings.PIPELINE_STALE_AFTER_MINUTES}+ minutes"
        ),
    )
    await _send_pipeline_ops_alert(
        title=f"Pipeline stale: {_pipeline_run_channel_label(run)}",
        message=message,
        tags="warning,rotating_light",
    )


async def send_pipeline_max_retry_alert(run: PipelineRun) -> None:
    message = _format_pipeline_run_message(
        run,
        headline=f"Pipeline max retries exceeded ({settings.PIPELINE_MAX_RETRIES})",
    )
    await _send_pipeline_ops_alert(
        title=f"Pipeline exhausted: {_pipeline_run_channel_label(run)}",
        message=message,
        tags="x,skull",
        priority="urgent",
    )


def _format_channel_digest_message(digest: ChannelDigestOut) -> str:
    lines = [
        f"Günlük özet — {digest.channel_name}",
        f"Tarih: {digest.digest_date.isoformat()} (UTC)",
        "",
        f"Yayınlanan: {len(digest.published)} video",
    ]
    for item in digest.published:
        label = item.hook_text
        if item.platform_url:
            lines.append(f"• {label} — {item.platform_label}: {item.platform_url}")
        else:
            lines.append(f"• {label} — {item.platform_label}")

    lines.extend(["", f"Bugün başarısız yayın: {len(digest.failed_publishes)}"])
    for item in digest.failed_publishes:
        error = item.error_log or "failed"
        lines.append(f"• Video {item.video_id} — {item.platform_label}: {error}")

    lines.extend(["", f"Bugün başarısız pipeline: {len(digest.failed_pipelines)}"])
    for item in digest.failed_pipelines:
        error = item.last_error or "failed"
        lines.append(f"• Run {item.run_id} — {error}")

    lines.extend(
        [
            "",
            (
                "Retry kuyruğu (şu an): "
                f"{digest.retry_pending_publishes} publish, "
                f"{digest.retry_pending_pipelines} pipeline"
            ),
        ]
    )

    if digest.profile_links:
        lines.extend(["", "Kanal linkleri:"])
        for link in digest.profile_links:
            lines.append(f"• {link.platform_label}: {link.profile_url}")

    return "\n".join(lines)


def _resolve_digest_click_url(digest: ChannelDigestOut) -> str | None:
    for link in digest.profile_links:
        if link.profile_url:
            return link.profile_url
    for item in digest.published:
        if item.platform_url:
            return item.platform_url
    return None


async def send_channel_daily_digest(digest: ChannelDigestOut) -> None:
    if not _is_configured():
        return

    base_url = settings.NTFY_BASE_URL.rstrip("/")
    topic = settings.NTFY_TOPIC.strip()
    url = f"{base_url}/{topic}"
    message = _format_channel_digest_message(digest)
    headers = {
        "Title": _ascii_header(f"Günlük özet: {digest.channel_name}"),
        "Tags": "bar_chart",
        "Priority": "low",
    }
    click_url = _resolve_digest_click_url(digest)
    if click_url:
        headers["Click"] = click_url

    try:
        async with httpx.AsyncClient(timeout=settings.NTFY_REQUEST_TIMEOUT) as client:
            response = await client.post(
                url,
                content=message.encode("utf-8"),
                headers=headers,
            )
            response.raise_for_status()
        logger.info(
            "ntfy daily digest sent channel_id=%s channel=%s",
            digest.channel_id,
            digest.channel_name,
        )
    except Exception:
        logger.warning(
            "ntfy daily digest failed channel_id=%s channel=%s",
            digest.channel_id,
            digest.channel_name,
            exc_info=True,
        )
