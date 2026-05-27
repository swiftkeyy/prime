"""referral events

Revision ID: 0003_referral_events
Revises: 0002_reserved_usernames
Create Date: 2026-05-27
"""
from alembic import op
import sqlalchemy as sa

revision = "0003_referral_events"
down_revision = "0002_reserved_usernames"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "referral_events",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("inviter_id", sa.Integer(), nullable=False),
        sa.Column("referred_user_id", sa.Integer(), nullable=False),
        sa.Column("bonus_attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["inviter_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["referred_user_id"], ["users.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("referred_user_id", name="uq_referral_events_referred_user"),
    )
    op.create_index("ix_referral_events_inviter_id", "referral_events", ["inviter_id"])
    op.create_index("ix_referral_events_referred_user_id", "referral_events", ["referred_user_id"])

    # Backfill audit table for referrals credited by older versions.
    op.execute(
        """
        INSERT INTO referral_events (inviter_id, referred_user_id, bonus_attempts, created_at)
        SELECT invited_by, id, 0, now()
        FROM users
        WHERE invited_by IS NOT NULL
        ON CONFLICT DO NOTHING
        """
    )

    # Keep old counters sane after manual DB edits or previous partial failures.
    op.execute(
        """
        UPDATE users u
        SET referrals_count = COALESCE(x.cnt, 0)
        FROM (
            SELECT inviter_id, COUNT(*) AS cnt
            FROM referral_events
            GROUP BY inviter_id
        ) x
        WHERE u.id = x.inviter_id
        """
    )


def downgrade() -> None:
    op.drop_index("ix_referral_events_referred_user_id", table_name="referral_events")
    op.drop_index("ix_referral_events_inviter_id", table_name="referral_events")
    op.drop_table("referral_events")
