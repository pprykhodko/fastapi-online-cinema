"""Create empty profiles for existing users without a profile.

Revision ID: 7a92c1d4e608
Revises: 2b6e0f8a4c91
"""

from alembic import op
import sqlalchemy as sa


revision: str = "7a92c1d4e608"
down_revision: str = "2b6e0f8a4c91"
branch_labels = None
depends_on = None


def upgrade() -> None:
    users = sa.table("users", sa.column("id", sa.Integer()))
    profiles = sa.table(
        "user_profiles", sa.column("user_id", sa.Integer()),
    )
    missing_profiles = sa.select(users.c.id).where(
        ~sa.exists().where(profiles.c.user_id == users.c.id),
    )
    op.execute(profiles.insert().from_select(["user_id"], missing_profiles))


def downgrade() -> None:
    # Keep profiles: users may have filled them in since the upgrade.
    pass
