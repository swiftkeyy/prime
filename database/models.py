from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import BigInteger, Boolean, DateTime, ForeignKey, Index, Integer, Numeric, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.asyncio import AsyncAttrs
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(AsyncAttrs, DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    telegram_id: Mapped[int] = mapped_column(BigInteger, unique=True, index=True, nullable=False)
    username: Mapped[str | None] = mapped_column(String(64), index=True)
    first_name: Mapped[str | None] = mapped_column(String(128))
    is_prime: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    prime_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    attempts_left: Mapped[int] = mapped_column(Integer, default=3, nullable=False)
    bonus_attempts: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    total_searches: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    referrals_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    invited_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    referral_code: Mapped[str] = mapped_column(String(64), unique=True, index=True, nullable=False)
    digits_enabled: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    underscore_enabled: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    style_mode: Mapped[str] = mapped_column(String(24), default="clean", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)
    last_attempts_reset: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    searches: Mapped[list["Search"]] = relationship(back_populates="user")
    payments: Mapped[list["Payment"]] = relationship(back_populates="user")
    promo_activations: Mapped[list["PromoActivation"]] = relationship(back_populates="user")
    reserved_usernames: Mapped[list["ReservedUsername"]] = relationship(back_populates="user")
    referral_events_created: Mapped[list["ReferralEvent"]] = relationship(
        back_populates="inviter",
        foreign_keys="ReferralEvent.inviter_id",
    )
    referral_event_received: Mapped["ReferralEvent"] = relationship(
        back_populates="referred_user",
        foreign_keys="ReferralEvent.referred_user_id",
        uselist=False,
    )


class ReferralEvent(Base):
    __tablename__ = "referral_events"
    __table_args__ = (UniqueConstraint("referred_user_id", name="uq_referral_events_referred_user"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    inviter_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False)
    referred_user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False)
    bonus_attempts: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    inviter: Mapped[User] = relationship(
        back_populates="referral_events_created",
        foreign_keys=[inviter_id],
    )
    referred_user: Mapped[User] = relationship(
        back_populates="referral_event_received",
        foreign_keys=[referred_user_id],
    )


class Search(Base):
    __tablename__ = "searches"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False)
    username_result: Mapped[str | None] = mapped_column(String(32), index=True)
    length: Mapped[int] = mapped_column(Integer, nullable=False)
    filters: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, nullable=False)
    status: Mapped[str] = mapped_column(String(24), default="found", index=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    user: Mapped[User] = relationship(back_populates="searches")


class ReservedUsername(Base):
    __tablename__ = "reserved_usernames"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False)
    username: Mapped[str] = mapped_column(String(32), index=True, nullable=False)
    length: Mapped[int] = mapped_column(Integer, nullable=False)
    source_search_id: Mapped[int | None] = mapped_column(ForeignKey("searches.id", ondelete="SET NULL"), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    released_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    __table_args__ = (
        Index(
            "uq_reserved_usernames_active_username",
            "username",
            unique=True,
            postgresql_where=(is_active.is_(True)),
        ),
    )

    user: Mapped[User] = relationship(back_populates="reserved_usernames")
    source_search: Mapped[Search | None] = relationship()




class UsernameStock(Base):
    __tablename__ = "username_stock"
    __table_args__ = (
        UniqueConstraint("username", name="uq_username_stock_username"),
        Index("ix_username_stock_status_length", "status", "length"),
        Index("ix_username_stock_available", "length", "status", "expires_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    username: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    length: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(24), default="available", nullable=False, index=True)
    source: Mapped[str] = mapped_column(String(64), default="worker", nullable=False)
    checked_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    issued_to_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    issued_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)


class Payment(Base):
    __tablename__ = "payments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False)
    amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    currency: Mapped[str] = mapped_column(String(8), nullable=False)
    method: Mapped[str] = mapped_column(String(32), index=True, nullable=False)
    status: Mapped[str] = mapped_column(String(24), default="created", index=True, nullable=False)
    invoice_id: Mapped[str | None] = mapped_column(String(128), unique=True, index=True)
    tariff: Mapped[str] = mapped_column(String(24), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    paid_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    user: Mapped[User] = relationship(back_populates="payments")


class PromoCode(Base):
    __tablename__ = "promo_codes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    code: Mapped[str] = mapped_column(String(64), unique=True, index=True, nullable=False)
    prime_days: Mapped[int] = mapped_column(Integer, nullable=False)
    max_uses: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    used_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    activations: Mapped[list["PromoActivation"]] = relationship(back_populates="promo_code")


class PromoActivation(Base):
    __tablename__ = "promo_activations"
    __table_args__ = (UniqueConstraint("user_id", "promo_code_id", name="uq_promo_activation_user_code"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False)
    promo_code_id: Mapped[int] = mapped_column(ForeignKey("promo_codes.id", ondelete="CASCADE"), index=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    user: Mapped[User] = relationship(back_populates="promo_activations")
    promo_code: Mapped[PromoCode] = relationship(back_populates="activations")


class Setting(Base):
    __tablename__ = "settings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    key: Mapped[str] = mapped_column(String(128), unique=True, index=True, nullable=False)
    value: Mapped[str] = mapped_column(Text, nullable=False)
