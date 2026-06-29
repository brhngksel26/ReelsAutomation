"""seed eonline top stories rss feed

Revision ID: 008_seed_eonline_rss
Revises: 007_add_pipeline_runs
Create Date: 2026-06-29
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "008_seed_eonline_rss"
down_revision: Union[str, None] = "007_add_pipeline_runs"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

SCHEMA = "reels_automation"

EONLINE_FEED_URL = "https://eol-feeds.eonline.com/rssfeed/us/top_stories"


def upgrade() -> None:
    op.execute(
        sa.text(
            f'INSERT INTO "{SCHEMA}".rss_feeds '
            f"(name, url, category, is_active, is_deleted) "
            f"SELECT :name, :url, :category, :is_active, :is_deleted "
            f"WHERE NOT EXISTS ("
            f'SELECT 1 FROM "{SCHEMA}".rss_feeds WHERE url = :url'
            f")"
        ).bindparams(
            name="E! Online - Top Stories",
            url=EONLINE_FEED_URL,
            category="entertainment",
            is_active=True,
            is_deleted=False,
        )
    )


def downgrade() -> None:
    op.execute(
        sa.text(
            f'DELETE FROM "{SCHEMA}".rss_feeds WHERE url = :url'
        ).bindparams(url=EONLINE_FEED_URL)
    )
