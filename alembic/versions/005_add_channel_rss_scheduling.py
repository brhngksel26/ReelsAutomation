"""add channel rss scheduling fields

Revision ID: 005_channel_rss_scheduling
Revises: 004_seed_rss
Create Date: 2026-06-24
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "005_channel_rss_scheduling"
down_revision: Union[str, None] = "004_seed_rss"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

SCHEMA = "reels_automation"


def upgrade() -> None:
    op.add_column(
        "channels",
        sa.Column("scheduling_mode", sa.String(length=20), nullable=False, server_default="fixed_hours"),
        schema=SCHEMA,
    )
    op.add_column(
        "channels",
        sa.Column("rss_interval_minutes", sa.Integer(), nullable=False, server_default="30"),
        schema=SCHEMA,
    )
    op.add_column(
        "channels",
        sa.Column("rss_max_videos_per_day", sa.Integer(), nullable=False, server_default="20"),
        schema=SCHEMA,
    )
    op.add_column(
        "channels",
        sa.Column("rss_last_scheduled_date", sa.Date(), nullable=True),
        schema=SCHEMA,
    )


def downgrade() -> None:
    op.drop_column("channels", "rss_last_scheduled_date", schema=SCHEMA)
    op.drop_column("channels", "rss_max_videos_per_day", schema=SCHEMA)
    op.drop_column("channels", "rss_interval_minutes", schema=SCHEMA)
    op.drop_column("channels", "scheduling_mode", schema=SCHEMA)
