"""username stock

Revision ID: 0004_username_stock
Revises: 0003_referral_events
Create Date: 2026-05-27
"""
from alembic import op
import sqlalchemy as sa

revision = "0004_username_stock"
down_revision = "0003_referral_events"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "username_stock",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("username", sa.String(length=32), nullable=False),
        sa.Column("length", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=24), nullable=False, server_default="available"),
        sa.Column("source", sa.String(length=64), nullable=False, server_default="worker"),
        sa.Column("checked_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("issued_to_user_id", sa.Integer(), nullable=True),
        sa.Column("issued_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["issued_to_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.UniqueConstraint("username", name="uq_username_stock_username"),
    )
    op.create_index("ix_username_stock_username", "username_stock", ["username"])
    op.create_index("ix_username_stock_length", "username_stock", ["length"])
    op.create_index("ix_username_stock_status", "username_stock", ["status"])
    op.create_index("ix_username_stock_expires_at", "username_stock", ["expires_at"])
    op.create_index("ix_username_stock_issued_to_user_id", "username_stock", ["issued_to_user_id"])
    op.create_index("ix_username_stock_issued_until", "username_stock", ["issued_until"])
    op.create_index("ix_username_stock_status_length", "username_stock", ["status", "length"])
    op.create_index("ix_username_stock_available", "username_stock", ["length", "status", "expires_at"])


def downgrade() -> None:
    op.drop_index("ix_username_stock_available", table_name="username_stock")
    op.drop_index("ix_username_stock_status_length", table_name="username_stock")
    op.drop_index("ix_username_stock_issued_until", table_name="username_stock")
    op.drop_index("ix_username_stock_issued_to_user_id", table_name="username_stock")
    op.drop_index("ix_username_stock_expires_at", table_name="username_stock")
    op.drop_index("ix_username_stock_status", table_name="username_stock")
    op.drop_index("ix_username_stock_length", table_name="username_stock")
    op.drop_index("ix_username_stock_username", table_name="username_stock")
    op.drop_table("username_stock")
