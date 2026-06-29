"""seed rss feeds and new permissions

Revision ID: 004_seed_rss
Revises: 003_add_rss_feeds
Create Date: 2026-06-24
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

from src.core.permission import Permission

revision: str = "004_seed_rss"
down_revision: Union[str, None] = "003_add_rss_feeds"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

SCHEMA = "reels_automation"

NEW_PERMISSIONS = [
    Permission.RSS_FEED_READ,
    Permission.RSS_FEED_MANAGE,
]

RSS_FEEDS = [
    {
        "name": "MIT Technology Review",
        "url": "https://www.technologyreview.com/feed/",
        "category": "tech",
        "is_active": True,
        "is_deleted": False,
    },
    {
        "name": "OpenAI Blog",
        "url": "https://openai.com/blog/rss.xml",
        "category": "ai",
        "is_active": True,
        "is_deleted": False,
    },
    {
        "name": "The Verge",
        "url": "https://theverge.com/rss/index.xml",
        "category": "tech",
        "is_active": True,
        "is_deleted": False,
    },
    {
        "name": "Ars Technica",
        "url": "https://feeds.arstechnica.com/arstechnica/index",
        "category": "tech",
        "is_active": True,
        "is_deleted": False,
    },
    {
        "name": "CoinDesk",
        "url": "https://www.coindesk.com/arc/outboundfeeds/rss/",
        "category": "crypto",
        "is_active": True,
        "is_deleted": False,
    },
    {
        "name": "Phys.org",
        "url": "https://phys.org/rss-feed/",
        "category": "science",
        "is_active": True,
        "is_deleted": False,
    },
]


def upgrade() -> None:
    permissions_table = sa.table(
        "permissions",
        sa.column("name", sa.String),
        sa.column("description", sa.String),
        sa.column("permission", sa.String),
        sa.column("is_deleted", sa.Boolean),
        schema=SCHEMA,
    )
    op.bulk_insert(
        permissions_table,
        [
            {
                "name": perm.value.replace(":", "_"),
                "description": perm.value,
                "permission": perm.value,
                "is_deleted": False,
            }
            for perm in NEW_PERMISSIONS
        ],
    )

    feeds_table = sa.table(
        "rss_feeds",
        sa.column("name", sa.String),
        sa.column("url", sa.String),
        sa.column("category", sa.String),
        sa.column("is_active", sa.Boolean),
        sa.column("is_deleted", sa.Boolean),
        schema=SCHEMA,
    )
    op.bulk_insert(feeds_table, RSS_FEEDS)


def downgrade() -> None:
    feed_urls = ", ".join(f"'{feed['url']}'" for feed in RSS_FEEDS)
    op.execute(
        sa.text(f'DELETE FROM "{SCHEMA}".rss_feeds WHERE url IN ({feed_urls})')
    )

    permission_values = ", ".join(f"'{perm.value}'" for perm in NEW_PERMISSIONS)
    op.execute(
        sa.text(
            f'DELETE FROM "{SCHEMA}".permissions '
            f"WHERE permission IN ({permission_values})"
        )
    )
