"""initial schema

Revision ID: 0001_initial
Revises:
Create Date: 2026-05-27
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0001_initial"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("telegram_id", sa.BigInteger(), nullable=False),
        sa.Column("username", sa.String(length=64), nullable=True),
        sa.Column("first_name", sa.String(length=128), nullable=True),
        sa.Column("is_prime", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("prime_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("attempts_left", sa.Integer(), nullable=False, server_default="3"),
        sa.Column("bonus_attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("total_searches", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("referrals_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("invited_by", sa.Integer(), nullable=True),
        sa.Column("referral_code", sa.String(length=64), nullable=False),
        sa.Column("digits_enabled", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("underscore_enabled", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("style_mode", sa.String(length=24), nullable=False, server_default="clean"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("last_attempts_reset", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["invited_by"], ["users.id"], ondelete="SET NULL"),
        sa.UniqueConstraint("telegram_id"),
        sa.UniqueConstraint("referral_code"),
    )
    op.create_index("ix_users_telegram_id", "users", ["telegram_id"])
    op.create_index("ix_users_username", "users", ["username"])
    op.create_index("ix_users_referral_code", "users", ["referral_code"])

    op.create_table(
        "searches",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("username_result", sa.String(length=32), nullable=True),
        sa.Column("length", sa.Integer(), nullable=False),
        sa.Column("filters", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("status", sa.String(length=24), nullable=False, server_default="found"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_searches_user_id", "searches", ["user_id"])
    op.create_index("ix_searches_username_result", "searches", ["username_result"])
    op.create_index("ix_searches_status", "searches", ["status"])

    op.create_table(
        "payments",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("amount", sa.Numeric(12, 2), nullable=False),
        sa.Column("currency", sa.String(length=8), nullable=False),
        sa.Column("method", sa.String(length=32), nullable=False),
        sa.Column("status", sa.String(length=24), nullable=False, server_default="created"),
        sa.Column("invoice_id", sa.String(length=128), nullable=True),
        sa.Column("tariff", sa.String(length=24), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("paid_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("invoice_id"),
    )
    op.create_index("ix_payments_user_id", "payments", ["user_id"])
    op.create_index("ix_payments_method", "payments", ["method"])
    op.create_index("ix_payments_status", "payments", ["status"])
    op.create_index("ix_payments_invoice_id", "payments", ["invoice_id"])

    op.create_table(
        "promo_codes",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("code", sa.String(length=64), nullable=False),
        sa.Column("prime_days", sa.Integer(), nullable=False),
        sa.Column("max_uses", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("used_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("code"),
    )
    op.create_index("ix_promo_codes_code", "promo_codes", ["code"])

    op.create_table(
        "promo_activations",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("promo_code_id", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["promo_code_id"], ["promo_codes.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("user_id", "promo_code_id", name="uq_promo_activation_user_code"),
    )
    op.create_index("ix_promo_activations_user_id", "promo_activations", ["user_id"])
    op.create_index("ix_promo_activations_promo_code_id", "promo_activations", ["promo_code_id"])

    op.create_table(
        "settings",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("key", sa.String(length=128), nullable=False),
        sa.Column("value", sa.Text(), nullable=False),
        sa.UniqueConstraint("key"),
    )
    op.create_index("ix_settings_key", "settings", ["key"])


def downgrade() -> None:
    op.drop_index("ix_settings_key", table_name="settings")
    op.drop_table("settings")
    op.drop_index("ix_promo_activations_promo_code_id", table_name="promo_activations")
    op.drop_index("ix_promo_activations_user_id", table_name="promo_activations")
    op.drop_table("promo_activations")
    op.drop_index("ix_promo_codes_code", table_name="promo_codes")
    op.drop_table("promo_codes")
    op.drop_index("ix_payments_invoice_id", table_name="payments")
    op.drop_index("ix_payments_status", table_name="payments")
    op.drop_index("ix_payments_method", table_name="payments")
    op.drop_index("ix_payments_user_id", table_name="payments")
    op.drop_table("payments")
    op.drop_index("ix_searches_status", table_name="searches")
    op.drop_index("ix_searches_username_result", table_name="searches")
    op.drop_index("ix_searches_user_id", table_name="searches")
    op.drop_table("searches")
    op.drop_index("ix_users_referral_code", table_name="users")
    op.drop_index("ix_users_username", table_name="users")
    op.drop_index("ix_users_telegram_id", table_name="users")
    op.drop_table("users")
