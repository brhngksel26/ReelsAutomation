from typing import Any

from pydantic import BaseModel, Field

from src.core.enums import (
    MoneyPrinterTaskState,
    VideoAspect,
    VideoConcatMode,
    VideoTransitionMode,
)


class MoneyPrinterConfig(BaseModel):
    base_url: str = "http://localhost:8080"
    api_token: str | None = None
    request_timeout: float = 120.0
    poll_interval: float = 5.0
    poll_timeout: float = 600.0


class MaterialInfo(BaseModel):
    provider: str = "pexels"
    url: str = ""
    duration: int = 0


class GenerateVideoParams(BaseModel):
    video_subject: str
    video_script: str = ""
    video_terms: str | list[str] | None = None
    video_aspect: VideoAspect = VideoAspect.PORTRAIT
    video_concat_mode: VideoConcatMode = VideoConcatMode.RANDOM
    video_transition_mode: VideoTransitionMode | None = None
    video_clip_duration: int = 5
    match_materials_to_script: bool = False
    video_count: int = 1
    video_source: str = "pexels"
    video_materials: list[MaterialInfo] | None = None
    custom_audio_file: str | None = None
    video_language: str = ""
    voice_name: str = ""
    voice_volume: float = 1.0
    voice_rate: float = 1.0
    bgm_type: str = "random"
    bgm_file: str = ""
    bgm_volume: float = 0.2
    subtitle_enabled: bool = True
    subtitle_position: str = "bottom"
    custom_position: float = 70.0
    font_name: str = "STHeitiMedium.ttc"
    text_fore_color: str = "#FFFFFF"
    text_background_color: bool | str = True
    rounded_subtitle_background: bool = False
    font_size: int = 60
    stroke_color: str = "#000000"
    stroke_width: float = 1.5
    n_threads: int = 2
    paragraph_number: int = Field(default=1, ge=1, le=10)
    video_script_prompt: str = Field(default="", max_length=2000)
    custom_system_prompt: str = Field(default="", max_length=8000)


class SubtitleParams(BaseModel):
    video_script: str
    video_language: str = ""
    voice_name: str = "zh-CN-XiaoxiaoNeural-Female"
    voice_volume: float = 1.0
    voice_rate: float = 1.2
    bgm_type: str = "random"
    bgm_file: str = ""
    bgm_volume: float = 0.2
    subtitle_position: str = "bottom"
    font_name: str = "STHeitiMedium.ttc"
    text_fore_color: str = "#FFFFFF"
    text_background_color: bool | str = True
    rounded_subtitle_background: bool = False
    font_size: int = 60
    stroke_color: str = "#000000"
    stroke_width: float = 1.5
    video_source: str = "local"
    subtitle_enabled: str = "true"


class AudioParams(BaseModel):
    video_script: str
    video_language: str = ""
    voice_name: str = "zh-CN-XiaoxiaoNeural-Female"
    voice_volume: float = 1.0
    voice_rate: float = 1.2
    bgm_type: str = "random"
    bgm_file: str = ""
    bgm_volume: float = 0.2
    video_source: str = "local"


class ScriptParams(BaseModel):
    video_subject: str
    video_language: str = ""
    paragraph_number: int = Field(default=1, ge=1, le=10)
    video_script_prompt: str = Field(default="", max_length=2000)
    custom_system_prompt: str = Field(default="", max_length=8000)


class TermsParams(BaseModel):
    video_subject: str
    video_script: str
    amount: int = 5


class SocialMetadataParams(BaseModel):
    video_subject: str
    video_script: str = ""
    language: str = "auto"
    platform: str = "tiktok"


class TaskCreated(BaseModel):
    task_id: str


class TaskStatus(BaseModel):
    state: int
    progress: int = 0
    videos: list[str] = Field(default_factory=list)
    combined_videos: list[str] = Field(default_factory=list)

    @property
    def is_complete(self) -> bool:
        return self.state == MoneyPrinterTaskState.COMPLETE

    @property
    def is_failed(self) -> bool:
        return self.state == MoneyPrinterTaskState.FAILED

    @property
    def is_processing(self) -> bool:
        return self.state == MoneyPrinterTaskState.PROCESSING


class TaskListResult(BaseModel):
    tasks: list[dict[str, Any]] = Field(default_factory=list)
    total: int = 0
    page: int = 1
    page_size: int = 10


class ScriptResult(BaseModel):
    video_script: str


class TermsResult(BaseModel):
    video_terms: list[str]


class SocialMetadataResult(BaseModel):
    title: str
    caption: str
    hashtags: list[str]


class FileInfo(BaseModel):
    name: str
    size: int
    file: str


class FileListResult(BaseModel):
    files: list[FileInfo] = Field(default_factory=list)
