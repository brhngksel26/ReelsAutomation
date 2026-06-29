"""add rss feeds and news

Revision ID: 003_add_rss_feeds
Revises: 002_seed_permissions
Create Date: 2026-06-24
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "003_add_rss_feeds"
down_revision: Union[str, None] = "002_seed_permissions"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

SCHEMA = "reels_automation"


def upgrade() -> None:
    op.create_table(
        "rss_feeds",
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("url", sa.String(length=1000), nullable=False),
        sa.Column("category", sa.String(length=100), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column(
            "created_date",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("is_deleted", sa.Boolean(), nullable=False),
        sa.Column(
            "updated_date",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("url"),
        schema=SCHEMA,
    )
    op.create_index(
        op.f("ix_reels_automation_rss_feeds_id"),
        "rss_feeds",
        ["id"],
        unique=False,
        schema=SCHEMA,
    )

    op.create_table(
        "rss_news_items",
        sa.Column("feed_id", sa.Integer(), nullable=False),
        sa.Column("guid", sa.String(length=1000), nullable=False),
        sa.Column("title", sa.String(length=500), nullable=False),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("link", sa.String(length=1000), nullable=False),
        sa.Column("author", sa.String(length=255), nullable=False),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("fetched_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column(
            "created_date",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("is_deleted", sa.Boolean(), nullable=False),
        sa.Column(
            "updated_date",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["feed_id"],
            [f"{SCHEMA}.rss_feeds.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("feed_id", "guid", name="uq_rss_feed_guid"),
        schema=SCHEMA,
    )
    op.create_index(
        op.f("ix_reels_automation_rss_news_items_feed_id"),
        "rss_news_items",
        ["feed_id"],
        unique=False,
        schema=SCHEMA,
    )
    op.create_index(
        op.f("ix_reels_automation_rss_news_items_id"),
        "rss_news_items",
        ["id"],
        unique=False,
        schema=SCHEMA,
    )

    op.create_table(
        "channel_rss_feeds",
        sa.Column("channel_id", sa.Integer(), nullable=False),
        sa.Column("feed_id", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(
            ["channel_id"],
            [f"{SCHEMA}.channels.id"],
        ),
        sa.ForeignKeyConstraint(
            ["feed_id"],
            [f"{SCHEMA}.rss_feeds.id"],
        ),
        sa.PrimaryKeyConstraint("channel_id", "feed_id"),
        schema=SCHEMA,
    )

    op.create_table(
        "channel_news_consumption",
        sa.Column("channel_id", sa.Integer(), nullable=False),
        sa.Column("news_item_id", sa.Integer(), nullable=False),
        sa.Column("video_metadata_id", sa.Integer(), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column(
            "created_date",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("is_deleted", sa.Boolean(), nullable=False),
        sa.Column(
            "updated_date",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["channel_id"],
            [f"{SCHEMA}.channels.id"],
        ),
        sa.ForeignKeyConstraint(
            ["news_item_id"],
            [f"{SCHEMA}.rss_news_items.id"],
        ),
        sa.ForeignKeyConstraint(
            ["video_metadata_id"],
            [f"{SCHEMA}.video_metadata.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("channel_id", "news_item_id", name="uq_channel_news_item"),
        schema=SCHEMA,
    )
    op.create_index(
        op.f("ix_reels_automation_channel_news_consumption_channel_id"),
        "channel_news_consumption",
        ["channel_id"],
        unique=False,
        schema=SCHEMA,
    )
    op.create_index(
        op.f("ix_reels_automation_channel_news_consumption_id"),
        "channel_news_consumption",
        ["id"],
        unique=False,
        schema=SCHEMA,
    )
    op.create_index(
        op.f("ix_reels_automation_channel_news_consumption_news_item_id"),
        "channel_news_consumption",
        ["news_item_id"],
        unique=False,
        schema=SCHEMA,
    )


def downgrade() -> None:
    op.drop_table("channel_news_consumption", schema=SCHEMA)
    op.drop_table("channel_rss_feeds", schema=SCHEMA)
    op.drop_table("rss_news_items", schema=SCHEMA)
    op.drop_table("rss_feeds", schema=SCHEMA)
