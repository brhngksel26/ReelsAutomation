"""fix rss feed urls and add scrape status columns

Revision ID: 006_fix_rss_feed_urls
Revises: 005_channel_rss_scheduling
Create Date: 2026-06-27
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "006_fix_rss_feed_urls"
down_revision: Union[str, None] = "005_channel_rss_scheduling"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

SCHEMA = "reels_automation"

FEED_URL_FIXES = [
    (
        "https://openai.com/blog/rss.xml",
        "https://openai.com/news/rss.xml",
    ),
    (
        "https://theverge.com/rss/index.xml",
        "https://www.theverge.com/rss/index.xml",
    ),
    (
        "https://www.coindesk.com/arc/outboundfeeds/rss/",
        "https://www.coindesk.com/arc/outboundfeeds/rss",
    ),
]

PHYS_ORG_FEED_URL = "https://phys.org/rss-feed/"


def upgrade() -> None:
    op.add_column(
        "rss_feeds",
        sa.Column("last_scrape_at", sa.DateTime(timezone=True), nullable=True),
        schema=SCHEMA,
    )
    op.add_column(
        "rss_feeds",
        sa.Column("last_scrape_error", sa.Text(), nullable=True),
        schema=SCHEMA,
    )
    op.add_column(
        "rss_feeds",
        sa.Column("last_item_count", sa.Integer(), nullable=True),
        schema=SCHEMA,
    )

    for old_url, new_url in FEED_URL_FIXES:
        op.execute(
            sa.text(
                f'UPDATE "{SCHEMA}".rss_feeds SET url = :new_url WHERE url = :old_url'
            ).bindparams(old_url=old_url, new_url=new_url)
        )

    op.execute(
        sa.text(
            f'UPDATE "{SCHEMA}".rss_feeds '
            f"SET is_active = false "
            f"WHERE url = :url"
        ).bindparams(url=PHYS_ORG_FEED_URL)
    )


def downgrade() -> None:
    op.execute(
        sa.text(
            f'UPDATE "{SCHEMA}".rss_feeds '
            f"SET is_active = true "
            f"WHERE url = :url"
        ).bindparams(url=PHYS_ORG_FEED_URL)
    )

    for old_url, new_url in reversed(FEED_URL_FIXES):
        op.execute(
            sa.text(
                f'UPDATE "{SCHEMA}".rss_feeds SET url = :old_url WHERE url = :new_url'
            ).bindparams(old_url=old_url, new_url=new_url)
        )

    op.drop_column("rss_feeds", "last_item_count", schema=SCHEMA)
    op.drop_column("rss_feeds", "last_scrape_error", schema=SCHEMA)
    op.drop_column("rss_feeds", "last_scrape_at", schema=SCHEMA)
