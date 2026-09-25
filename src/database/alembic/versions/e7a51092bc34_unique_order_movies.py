"""Prevent duplicate movies inside one order without altering historical rows."""

from alembic import op


revision = "e7a51092bc34"
down_revision = "c4d90271a6bf"
branch_labels = None
depends_on = None


def upgrade():
    op.create_index("uq_order_items_order_movie", "order_items", ["order_id", "movie_id"], unique=True)


def downgrade():
    op.drop_index("uq_order_items_order_movie", table_name="order_items")
