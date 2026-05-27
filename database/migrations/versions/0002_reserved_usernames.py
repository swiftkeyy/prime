"""reserved usernames

Revision ID: 0002_reserved_usernames
Revises: 0001_initial
Create Date: 2026-05-27
"""
from alembic import op
import sqlalchemy as sa

revision = "0002_reserved_usernames"
down_revision = "0001_initial"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "reserved_usernames",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("username", sa.String(length=32), nullable=False),
        sa.Column("length", sa.Integer(), nullable=False),
        sa.Column("source_search_id", sa.Integer(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("released_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["source_search_id"], ["searches.id"], ondelete="SET NULL"),
    )
    op.create_index("ix_reserved_usernames_user_id", "reserved_usernames", ["user_id"])
    op.create_index("ix_reserved_usernames_username", "reserved_usernames", ["username"])
    op.create_index("ix_reserved_usernames_is_active", "reserved_usernames", ["is_active"])
    op.create_index(
        "uq_reserved_usernames_active_username",
        "reserved_usernames",
        ["username"],
        unique=True,
        postgresql_where=sa.text("is_active = true"),
    )


def downgrade() -> None:
    op.drop_index("uq_reserved_usernames_active_username", table_name="reserved_usernames")
    op.drop_index("ix_reserved_usernames_is_active", table_name="reserved_usernames")
    op.drop_index("ix_reserved_usernames_username", table_name="reserved_usernames")
    op.drop_index("ix_reserved_usernames_user_id", table_name="reserved_usernames")
    op.drop_table("reserved_usernames")
