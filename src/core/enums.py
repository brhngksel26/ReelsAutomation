from enum import Enum


class ProfileTier(str, Enum):
    FREE = "free"
    PREMIUM = "premium"


class PlatformType(str, Enum):
    INSTAGRAM = "instagram"
    YOUTUBE_SHORTS = "youtube_shorts"
    TIKTOK = "tiktok"


class PlatformStatus(str, Enum):
    CONNECTED = "connected"
    EXPIRED = "expired"
    ERROR = "error"


class GenerationStatus(str, Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


class PublishStatus(str, Enum):
    SCHEDULED = "scheduled"
    UPLOADING = "uploading"
    PUBLISHED = "published"
    FAILED = "failed"


class LLMProviderType(str, Enum):
    OLLAMA = "ollama"
    OPENAI = "openai"
    ANTHROPIC = "anthropic"
    GOOGLE = "google"


class VideoAspect(str, Enum):
    LANDSCAPE = "16:9"
    PORTRAIT = "9:16"
    SQUARE = "1:1"


class VideoConcatMode(str, Enum):
    RANDOM = "random"
    SEQUENTIAL = "sequential"


class VideoTransitionMode(str, Enum):
    SHUFFLE = "Shuffle"
    FADE_IN = "FadeIn"
    FADE_OUT = "FadeOut"
    SLIDE_IN = "SlideIn"
    SLIDE_OUT = "SlideOut"


class MoneyPrinterTaskState(int, Enum):
    FAILED = -1
    COMPLETE = 1
    PROCESSING = 4


class NewsConsumptionStatus(str, Enum):
    SELECTED = "selected"
    PRODUCED = "produced"
    PUBLISHED = "published"
    FAILED = "failed"


class SchedulingMode(str, Enum):
    FIXED_HOURS = "fixed_hours"
    RSS_NEWS = "rss_news"


class PipelineRunStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    STALE = "stale"
