"""add pipeline_runs registry table

Revision ID: 007_add_pipeline_runs
Revises: 006_fix_rss_feed_urls
Create Date: 2026-06-27
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "007_add_pipeline_runs"
down_revision: Union[str, None] = "006_fix_rss_feed_urls"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

SCHEMA = "reels_automation"


def upgrade() -> None:
    op.create_table(
        "pipeline_runs",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("channel_id", sa.Integer(), nullable=False),
        sa.Column("thread_id", sa.String(length=255), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="pending"),
        sa.Column("current_step", sa.String(length=100), nullable=True),
        sa.Column("celery_task_id", sa.String(length=255), nullable=True),
        sa.Column("video_metadata_id", sa.Integer(), nullable=True),
        sa.Column("news_consumption_id", sa.Integer(), nullable=True),
        sa.Column("retry_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["channel_id"], [f"{SCHEMA}.channels.id"]),
        sa.ForeignKeyConstraint(["video_metadata_id"], [f"{SCHEMA}.video_metadata.id"]),
        sa.ForeignKeyConstraint(
            ["news_consumption_id"],
            [f"{SCHEMA}.channel_news_consumption.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("thread_id"),
        schema=SCHEMA,
    )
    op.create_index(
        op.f("ix_reels_automation_pipeline_runs_channel_id"),
        "pipeline_runs",
        ["channel_id"],
        unique=False,
        schema=SCHEMA,
    )
    op.create_index(
        op.f("ix_reels_automation_pipeline_runs_status"),
        "pipeline_runs",
        ["status"],
        unique=False,
        schema=SCHEMA,
    )


def downgrade() -> None:
    op.drop_index(
        op.f("ix_reels_automation_pipeline_runs_status"),
        table_name="pipeline_runs",
        schema=SCHEMA,
    )
    op.drop_index(
        op.f("ix_reels_automation_pipeline_runs_channel_id"),
        table_name="pipeline_runs",
        schema=SCHEMA,
    )
    op.drop_table("pipeline_runs", schema=SCHEMA)
