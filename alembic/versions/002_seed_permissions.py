"""seed permissions

Revision ID: 002_seed_permissions
Revises: edb492ee76fb
Create Date: 2026-06-23
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

from src.core.permission import Permission

revision: str = "002_seed_permissions"
down_revision: Union[str, None] = "edb492ee76fb"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

SCHEMA = "reels_automation"

PERMISSIONS = [
    {
        "name": perm.value.replace(":", "_"),
        "description": perm.value,
        "permission": perm.value,
        "is_deleted": False,
    }
    for perm in Permission
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
    op.bulk_insert(permissions_table, PERMISSIONS)


def downgrade() -> None:
    permission_values = ", ".join(f"'{perm.value}'" for perm in Permission)
    op.execute(
        sa.text(
            f'DELETE FROM "{SCHEMA}".permissions '
            f"WHERE permission IN ({permission_values})"
        )
    )
