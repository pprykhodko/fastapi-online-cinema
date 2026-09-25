"""Persist Stripe checkout requests and deduplicate provider payments."""

from alembic import op
import sqlalchemy as sa


revision = "c4d90271a6bf"
down_revision = "7a92c1d4e608"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("payments", sa.Column("currency", sa.String(3), nullable=False, server_default="usd"))
    op.create_index("ix_payments_external_payment_id_unique", "payments", ["external_payment_id"], unique=True)
    op.create_table(
        "payment_checkouts",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("order_id", sa.Integer(), sa.ForeignKey("orders.id", ondelete="RESTRICT"), nullable=False, unique=True),
        sa.Column("request_key", sa.String(36), nullable=False, unique=True),
        sa.Column("request_data", sa.JSON(), nullable=False),
        sa.Column("session_id", sa.String(255), unique=True),
        sa.Column("checkout_url", sa.String(2048)),
        sa.Column("expires_at", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("payment_id", sa.Integer(), sa.ForeignKey("payments.id", ondelete="RESTRICT"), unique=True),
        sa.Column("email_queued", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("refund_id", sa.String(255), unique=True),
    )


def downgrade():
    op.drop_table("payment_checkouts")
    op.drop_index("ix_payments_external_payment_id_unique", table_name="payments")
    with op.batch_alter_table("payments") as batch:
        batch.drop_column("currency")
