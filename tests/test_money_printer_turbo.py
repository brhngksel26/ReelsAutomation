from collections.abc import Callable

import httpx
import pytest

from src.core.base_exception import (
    MoneyPrinterRequestError,
    MoneyPrinterTaskError,
    MoneyPrinterTimeoutError,
)
from src.core.enums import MoneyPrinterTaskState
from src.core.http_client import HttpClient
from src.integrations.money_printer_turbo import (
    MoneyPrinterTurboClient,
    _normalize_download_path,
)
from src.schemas.money_printer_turbo import (
    AudioParams,
    GenerateVideoParams,
    MoneyPrinterConfig,
    ScriptParams,
    SocialMetadataParams,
    SubtitleParams,
    TermsParams,
)


def _envelope(
    data: dict | None = None, *, status: int = 200, message: str = "success"
) -> dict:
    return {"status": status, "message": message, "data": data}


def _make_client(
    handlers: dict[str, Callable[[httpx.Request], httpx.Response]],
) -> MoneyPrinterTurboClient:
    def handler(request: httpx.Request) -> httpx.Response:
        route_key = f"{request.method} {request.url.path}"
        if route_key not in handlers:
            return httpx.Response(404, json=_envelope(message="not found", status=404))
        return handlers[route_key](request)

    transport = httpx.MockTransport(handler)
    config = MoneyPrinterConfig(
        base_url="http://mpt.test", poll_interval=0.01, poll_timeout=0.5
    )

    def client_factory() -> HttpClient:
        return HttpClient(base_url=config.base_url, transport=transport, http2=False)

    return MoneyPrinterTurboClient(config, client_factory=client_factory)


@pytest.mark.asyncio
async def test_generate_video_returns_task_id():
    client = _make_client(
        {
            "POST /api/v1/videos": lambda _: httpx.Response(
                200,
                json=_envelope({"task_id": "task-123"}),
            )
        }
    )

    result = await client.generate_video(
        GenerateVideoParams(video_subject="Money habits", video_script="Save first.")
    )

    assert result.task_id == "task-123"


@pytest.mark.asyncio
async def test_generate_subtitle_and_audio():
    client = _make_client(
        {
            "POST /api/v1/subtitle": lambda _: httpx.Response(
                200,
                json=_envelope({"task_id": "subtitle-1"}),
            ),
            "POST /api/v1/audio": lambda _: httpx.Response(
                200,
                json=_envelope({"task_id": "audio-1"}),
            ),
        }
    )

    subtitle = await client.generate_subtitle(
        SubtitleParams(video_script="Hello world")
    )
    audio = await client.generate_audio(AudioParams(video_script="Hello world"))

    assert subtitle.task_id == "subtitle-1"
    assert audio.task_id == "audio-1"


@pytest.mark.asyncio
async def test_get_task_and_list_tasks():
    client = _make_client(
        {
            "GET /api/v1/tasks/task-123": lambda _: httpx.Response(
                200,
                json=_envelope(
                    {
                        "state": MoneyPrinterTaskState.COMPLETE,
                        "progress": 100,
                        "videos": ["http://mpt.test/tasks/task-123/final-1.mp4"],
                        "combined_videos": [],
                    }
                ),
            ),
            "GET /api/v1/tasks": lambda request: httpx.Response(
                200,
                json=_envelope(
                    {
                        "tasks": [{"task_id": "task-123"}],
                        "total": 1,
                        "page": int(request.url.params.get("page", "1")),
                        "page_size": int(request.url.params.get("page_size", "10")),
                    }
                ),
            ),
        }
    )

    task = await client.get_task("task-123")
    tasks = await client.list_tasks(page=1, page_size=10)

    assert task.is_complete
    assert task.videos == ["http://mpt.test/tasks/task-123/final-1.mp4"]
    assert tasks.total == 1
    assert tasks.tasks[0]["task_id"] == "task-123"


@pytest.mark.asyncio
async def test_delete_task():
    client = _make_client(
        {
            "DELETE /api/v1/tasks/task-123": lambda _: httpx.Response(
                200,
                json=_envelope({}),
            )
        }
    )

    await client.delete_task("task-123")


@pytest.mark.asyncio
async def test_llm_helper_endpoints():
    client = _make_client(
        {
            "POST /api/v1/scripts": lambda _: httpx.Response(
                200,
                json=_envelope({"video_script": "Generated script"}),
            ),
            "POST /api/v1/terms": lambda _: httpx.Response(
                200,
                json=_envelope({"video_terms": ["money", "finance"]}),
            ),
            "POST /api/v1/social-metadata": lambda _: httpx.Response(
                200,
                json=_envelope(
                    {
                        "title": "Title",
                        "caption": "Caption",
                        "hashtags": ["#fyp"],
                    }
                ),
            ),
        }
    )

    script = await client.generate_script(ScriptParams(video_subject="Finance"))
    terms = await client.generate_terms(
        TermsParams(video_subject="Finance", video_script="Save more.")
    )
    metadata = await client.generate_social_metadata(
        SocialMetadataParams(video_subject="Finance", video_script="Save more.")
    )

    assert script.video_script == "Generated script"
    assert terms.video_terms == ["money", "finance"]
    assert metadata.title == "Title"
    assert metadata.hashtags == ["#fyp"]


@pytest.mark.asyncio
async def test_wait_for_completion_success():
    poll_count = {"value": 0}

    def get_task(_: httpx.Request) -> httpx.Response:
        poll_count["value"] += 1
        state = (
            MoneyPrinterTaskState.COMPLETE
            if poll_count["value"] >= 2
            else MoneyPrinterTaskState.PROCESSING
        )
        return httpx.Response(
            200,
            json=_envelope({"state": state, "progress": 100, "videos": ["final.mp4"]}),
        )

    client = _make_client({"GET /api/v1/tasks/task-123": get_task})

    task = await client.wait_for_completion("task-123")

    assert task.is_complete
    assert poll_count["value"] >= 2


@pytest.mark.asyncio
async def test_wait_for_completion_failed_task():
    client = _make_client(
        {
            "GET /api/v1/tasks/task-123": lambda _: httpx.Response(
                200,
                json=_envelope({"state": MoneyPrinterTaskState.FAILED, "progress": 0}),
            )
        }
    )

    with pytest.raises(MoneyPrinterTaskError):
        await client.wait_for_completion("task-123")


@pytest.mark.asyncio
async def test_wait_for_completion_timeout():
    client = _make_client(
        {
            "GET /api/v1/tasks/task-123": lambda _: httpx.Response(
                200,
                json=_envelope(
                    {"state": MoneyPrinterTaskState.PROCESSING, "progress": 10}
                ),
            )
        }
    )

    with pytest.raises(MoneyPrinterTimeoutError):
        await client.wait_for_completion("task-123", poll_interval=0.01, timeout=0.05)


@pytest.mark.asyncio
async def test_download_video():
    client = _make_client(
        {
            "GET /api/v1/download/task-123/final-1.mp4": lambda _: httpx.Response(
                200,
                content=b"video-bytes",
                headers={"content-type": "video/mp4"},
            )
        }
    )

    content = await client.download_video("task-123/final-1.mp4")

    assert content == b"video-bytes"


def test_normalize_download_path_strips_tasks_prefix():
    task_id = "1ab677f7-ca59-49c1-b441-fed8f89fa708"
    assert (
        _normalize_download_path(f"tasks/{task_id}/final-1.mp4")
        == f"{task_id}/final-1.mp4"
    )
    assert (
        _normalize_download_path(f"/tasks/{task_id}/final-1.mp4")
        == f"{task_id}/final-1.mp4"
    )
    assert (
        _normalize_download_path(f"http://localhost:8080/tasks/{task_id}/final-1.mp4")
        == f"{task_id}/final-1.mp4"
    )


@pytest.mark.asyncio
async def test_download_video_with_tasks_prefix_path():
    task_id = "1ab677f7-ca59-49c1-b441-fed8f89fa708"
    client = _make_client(
        {
            f"GET /api/v1/download/{task_id}/final-1.mp4": lambda _: httpx.Response(
                200,
                content=b"video-bytes",
                headers={"content-type": "video/mp4"},
            )
        }
    )

    content = await client.download_video(f"tasks/{task_id}/final-1.mp4")

    assert content == b"video-bytes"


@pytest.mark.asyncio
async def test_list_musics_and_materials():
    client = _make_client(
        {
            "GET /api/v1/musics": lambda _: httpx.Response(
                200,
                json=_envelope(
                    {"files": [{"name": "song.mp3", "size": 100, "file": "song.mp3"}]}
                ),
            ),
            "GET /api/v1/video_materials": lambda _: httpx.Response(
                200,
                json=_envelope(
                    {"files": [{"name": "clip.mp4", "size": 200, "file": "clip.mp4"}]}
                ),
            ),
        }
    )

    musics = await client.list_musics()
    materials = await client.list_video_materials()

    assert musics.files[0].name == "song.mp3"
    assert materials.files[0].name == "clip.mp4"
    assert await client.health_check() is True


@pytest.mark.asyncio
async def test_http_error_is_mapped():
    client = _make_client(
        {
            "POST /api/v1/videos": lambda _: httpx.Response(
                400,
                json={"message": "invalid params"},
            )
        }
    )

    with pytest.raises(MoneyPrinterRequestError) as exc_info:
        await client.generate_video(GenerateVideoParams(video_subject="Test"))

    assert exc_info.value.status_code == 400
    assert "invalid params" in str(exc_info.value)


@pytest.mark.asyncio
async def test_envelope_error_status_raises():
    client = _make_client(
        {
            "POST /api/v1/videos": lambda _: httpx.Response(
                200,
                json=_envelope(message="queue full", status=429),
            )
        }
    )

    with pytest.raises(MoneyPrinterRequestError) as exc_info:
        await client.generate_video(GenerateVideoParams(video_subject="Test"))

    assert exc_info.value.status_code == 429
