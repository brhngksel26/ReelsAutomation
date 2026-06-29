#!/usr/bin/env python3
"""Ensure permissions exist in the DB and assign missing ones to users.

Use when new permissions are added to the codebase but existing users
still get 403 (e.g. after RSS endpoints were introduced).

Examples:
  uv run python scripts/add_permissions.py
  uv run python scripts/add_permissions.py --email user@example.com
  uv run python scripts/add_permissions.py --permission rss:feed:read rss:feed:manage

Docker:
  docker exec reels_automation python scripts/add_permissions.py
"""

from __future__ import annotations

import argparse
import sys

from sqlalchemy import and_, insert, select

from src.core.database import sync_engine
from src.core.permission import DEFAULT_FREE_TIER_PERMISSIONS, Permission
from src.models.auth import AuthPermission, User, user_permissions


def _parse_permissions(values: list[str] | None) -> list[Permission]:
    if not values:
        return list(DEFAULT_FREE_TIER_PERMISSIONS)

    parsed: list[Permission] = []
    valid = {perm.value: perm for perm in Permission}
    for value in values:
        if value not in valid:
            raise ValueError(f"Unknown permission: {value}")
        parsed.append(valid[value])
    return parsed


def _ensure_permissions(conn, permissions: list[Permission]) -> dict[str, int]:
    permission_ids: dict[str, int] = {}

    for perm in permissions:
        row = conn.execute(
            select(AuthPermission.id).where(
                and_(
                    AuthPermission.permission == perm.value,
                    AuthPermission.is_deleted.is_(False),
                )
            )
        ).scalar_one_or_none()

        if row is None:
            inserted = conn.execute(
                insert(AuthPermission)
                .values(
                    name=perm.value.replace(":", "_"),
                    description=perm.value,
                    permission=perm.value,
                    is_deleted=False,
                )
                .returning(AuthPermission.id)
            )
            permission_ids[perm.value] = inserted.scalar_one()
            print(f"Created permission row: {perm.value}")
        else:
            permission_ids[perm.value] = row

    conn.commit()
    return permission_ids


def _load_users(conn, email: str | None) -> list[tuple[int, str]]:
    query = select(User.id, User.email).where(User.is_deleted.is_(False))
    if email:
        query = query.where(User.email == email)
    rows = conn.execute(query).all()
    return [(row.id, row.email) for row in rows]


def _assign_missing_permissions(
    conn,
    user_id: int,
    permission_ids: list[int],
) -> int:
    if not permission_ids:
        return 0

    existing = set(
        conn.execute(
            select(user_permissions.c.permission_id).where(
                user_permissions.c.user_id == user_id
            )
        ).scalars()
    )
    missing_ids = [pid for pid in permission_ids if pid not in existing]
    if not missing_ids:
        return 0

    conn.execute(
        insert(user_permissions),
        [{"user_id": user_id, "permission_id": pid} for pid in missing_ids],
    )
    conn.commit()
    return len(missing_ids)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Seed missing permissions and assign them to users.",
    )
    parser.add_argument(
        "--email",
        help="Only update a single user by email",
    )
    parser.add_argument(
        "--permission",
        action="append",
        dest="permissions",
        metavar="PERM",
        help="Permission value to sync (repeatable). Default: all free-tier permissions.",
    )
    args = parser.parse_args()

    try:
        permissions = _parse_permissions(args.permissions)
    except ValueError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    with sync_engine.connect() as conn:
        permission_id_by_value = _ensure_permissions(conn, permissions)
        permission_ids = list(permission_id_by_value.values())

        users = _load_users(conn, args.email)
        if not users:
            target = args.email or "any active user"
            print(f"No users found for: {target}")
            return 1

        total_assigned = 0
        for user_id, user_email in users:
            assigned = _assign_missing_permissions(conn, user_id, permission_ids)
            total_assigned += assigned
            if assigned:
                print(
                    f"Assigned {assigned} permission(s) to {user_email} (id={user_id})"
                )
            else:
                print(f"No missing permissions for {user_email} (id={user_id})")

    print(
        f"Done. Synced {len(permission_ids)} permission(s) "
        f"across {len(users)} user(s); {total_assigned} new assignment(s)."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
