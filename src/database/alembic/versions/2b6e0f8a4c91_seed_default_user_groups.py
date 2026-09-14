"""Seed default user groups.

Revision ID: 2b6e0f8a4c91
Revises: 0117b21577ed
"""

from alembic import op
import sqlalchemy as sa


revision: str = "2b6e0f8a4c91"
down_revision: str = "0117b21577ed"
branch_labels = None
depends_on = None

user_groups = sa.table(
    "user_groups",
    sa.column("id", sa.Integer()),
    sa.column("name", sa.String(length=50)),
)


def upgrade() -> None:
    op.bulk_insert(user_groups, [
        {"name": "USER"},
        {"name": "MODERATOR"},
        {"name": "ADMIN"},
    ])


def downgrade() -> None:
    users = sa.table("users", sa.column("group_id", sa.Integer()))
    group_names = ("USER", "MODERATOR", "ADMIN")
    group_ids = sa.select(user_groups.c.id).where(
        user_groups.c.name.in_(group_names),
    )
    users_count = op.get_bind().scalar(
        sa.select(sa.func.count()).select_from(users).where(
            users.c.group_id.in_(group_ids),
        ),
    )
    if users_count:
        raise RuntimeError("Cannot remove groups assigned to existing users.")

    op.execute(user_groups.delete().where(user_groups.c.name.in_(group_names)))
