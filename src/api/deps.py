"""FastAPI dependency wrappers around core.deps factories."""

from src.core import deps as core_deps
from src.cruds.auth import AuthPermissionCrud, ProfileCrud, UserCrud
from src.cruds.channel import ChannelCrud, PlatformConfigCrud
from src.cruds.pipeline_run import PipelineRunCrud
from src.cruds.rss import ChannelNewsConsumptionCrud, RssFeedCrud, RssNewsItemCrud
from src.cruds.video import VideoMetadataCrud, VideoPublishStatusCrud
from src.services.uploaders.base import PlatformUploader


def get_channel_crud() -> ChannelCrud:
    return core_deps.get_channel_crud()


def get_profile_crud() -> ProfileCrud:
    return core_deps.get_profile_crud()


def get_user_crud() -> UserCrud:
    return core_deps.get_user_crud()


def get_auth_permission_crud() -> AuthPermissionCrud:
    return core_deps.get_auth_permission_crud()


def get_video_metadata_crud() -> VideoMetadataCrud:
    return core_deps.get_video_metadata_crud()


def get_video_publish_status_crud() -> VideoPublishStatusCrud:
    return core_deps.get_video_publish_status_crud()


def get_platform_config_crud() -> PlatformConfigCrud:
    return core_deps.get_platform_config_crud()


def get_rss_feed_crud() -> RssFeedCrud:
    return core_deps.get_rss_feed_crud()


def get_rss_news_item_crud() -> RssNewsItemCrud:
    return core_deps.get_rss_news_item_crud()


def get_channel_news_consumption_crud() -> ChannelNewsConsumptionCrud:
    return core_deps.get_channel_news_consumption_crud()


def get_pipeline_run_crud() -> PipelineRunCrud:
    return core_deps.get_pipeline_run_crud()


def get_uploader(platform_type: str) -> PlatformUploader:
    return core_deps.get_uploader(platform_type)
