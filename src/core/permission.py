from enum import Enum


class Permission(str, Enum):
    USER_READ = "user:read"
    CHANNEL_CREATE = "channel:create"
    CHANNEL_READ = "channel:read"
    CHANNEL_UPDATE = "channel:update"
    CHANNEL_DELETE = "channel:delete"
    PLATFORM_CONNECT = "platform:connect"
    PLATFORM_READ = "platform:read"
    VIDEO_SCHEDULE = "video:schedule"
    VIDEO_READ = "video:read"
    VIDEO_UPDATE = "video:update"
    VIDEO_DELETE = "video:delete"
    RSS_FEED_READ = "rss:feed:read"
    RSS_FEED_MANAGE = "rss:feed:manage"


DEFAULT_FREE_TIER_PERMISSIONS = [
    Permission.USER_READ,
    Permission.CHANNEL_CREATE,
    Permission.CHANNEL_READ,
    Permission.CHANNEL_UPDATE,
    Permission.CHANNEL_DELETE,
    Permission.PLATFORM_CONNECT,
    Permission.PLATFORM_READ,
    Permission.VIDEO_SCHEDULE,
    Permission.VIDEO_READ,
    Permission.VIDEO_UPDATE,
    Permission.VIDEO_DELETE,
    Permission.RSS_FEED_READ,
    Permission.RSS_FEED_MANAGE,
]
