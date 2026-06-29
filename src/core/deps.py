"""Composition root — factory functions for CRUDs and uploaders."""

from typing import TYPE_CHECKING

from src.cruds.auth import AuthPermissionCrud, ProfileCrud, UserCrud
from src.cruds.channel import ChannelCrud, PlatformConfigCrud
from src.cruds.pipeline_run import PipelineRunCrud
from src.cruds.rss import ChannelNewsConsumptionCrud, RssFeedCrud, RssNewsItemCrud
from src.cruds.video import VideoMetadataCrud, VideoPublishStatusCrud

if TYPE_CHECKING:
    from src.services.uploaders.base import PlatformUploader


def get_channel_crud() -> ChannelCrud:
    return ChannelCrud()


def get_profile_crud() -> ProfileCrud:
    return ProfileCrud()


def get_user_crud() -> UserCrud:
    return UserCrud()


def get_auth_permission_crud() -> AuthPermissionCrud:
    return AuthPermissionCrud()


def get_video_metadata_crud() -> VideoMetadataCrud:
    return VideoMetadataCrud()


def get_video_publish_status_crud() -> VideoPublishStatusCrud:
    return VideoPublishStatusCrud()


def get_platform_config_crud() -> PlatformConfigCrud:
    return PlatformConfigCrud()


def get_rss_feed_crud() -> RssFeedCrud:
    return RssFeedCrud()


def get_rss_news_item_crud() -> RssNewsItemCrud:
    return RssNewsItemCrud()


def get_channel_news_consumption_crud() -> ChannelNewsConsumptionCrud:
    return ChannelNewsConsumptionCrud()


def get_pipeline_run_crud() -> PipelineRunCrud:
    return PipelineRunCrud()


def get_uploader(platform_type: str) -> "PlatformUploader":
    from src.services.uploaders.base import get_uploader as _get_uploader

    return _get_uploader(platform_type)
