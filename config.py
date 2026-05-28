from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    BOT_TOKEN: str
    BOT_USERNAME: str = "PRIME_NICK_BOT"
    ADMIN_IDS: str = ""

    DATABASE_URL: str
    REDIS_URL: str

    RAILWAY_PUBLIC_URL: str
    PORT: int = 8080
    WEBHOOK_SECRET: str = Field(default="", min_length=0)

    SUPPORT_USERNAME: str = ""

    FREE_ATTEMPTS: int = 3
    ATTEMPTS_COOLDOWN_HOURS: int = 12
    REFERRAL_BONUS_ATTEMPTS: int = 2

    PRIME_1_DAY_PRICE_RUB: int = 99
    PRIME_7_DAYS_PRICE_RUB: int = 299
    PRIME_30_DAYS_PRICE_RUB: int = 699
    PRIME_FOREVER_PRICE_RUB: int = 1990

    PRIME_1_DAY_PRICE_STARS: int = 100
    PRIME_7_DAYS_PRICE_STARS: int = 300
    PRIME_30_DAYS_PRICE_STARS: int = 700
    PRIME_FOREVER_PRICE_STARS: int = 2000

    TELEGRAM_STARS_PROVIDER_TOKEN: str = ""

    ROBOKASSA_LOGIN: str = ""
    ROBOKASSA_PASSWORD_1: str = ""
    ROBOKASSA_PASSWORD_2: str = ""
    ROBOKASSA_TEST_MODE: bool = True

    LEGAL_INFO_LINK: str = ""
    USER_AGREEMENT_LINK: str = "https://telegra.ph/Polzovatelskoe-soglashenie-PRIME-NICK-05-27"
    PRIVACY_POLICY_LINK: str = "https://telegra.ph/Politika-konfidencialnosti-PRIME-NICK-05-27"
    PRIME_TERMS_LINK: str = ""

    USERNAME_CHECK_MODE: Literal["http", "mock", "fragment", "mtproto"] = "mtproto"
    USERNAME_CHECK_TIMEOUT: int = 7
    FRAGMENT_CHECK_DELAY_SECONDS: float = 0.8
    MTPROTO_CHECK_DELAY_SECONDS: float = 3.0
    TELEGRAM_API_ID: int = 0
    TELEGRAM_API_HASH: str = ""
    TELEGRAM_STRING_SESSION: str = ""
    TELEGRAM_STRING_SESSIONS: str = ""
    MTPROTO_SESSION_MAX_COOLDOWN_SECONDS: int = 86400
    SEARCH_MAX_CANDIDATES: int = 4
    PRIME_SEARCH_MAX_CANDIDATES: int = 7
    PRIME_5_SEARCH_MAX_CANDIDATES: int = 8
    SEARCH_TOTAL_TIMEOUT_SECONDS: int = 22
    PRIME_5_SEARCH_TOTAL_TIMEOUT_SECONDS: int = 36

    FREE_RESERVED_USERNAMES_LIMIT: int = 10
    PRIME_RESERVED_USERNAMES_LIMIT: int = 30

    USERNAME_SUGGESTIONS_COUNT: int = 5
    USERNAME_SUGGESTIONS_MAX_CANDIDATES: int = 5
    PRIME_USERNAME_SUGGESTIONS_MAX_CANDIDATES: int = 8

    # Production-safe username delivery. Live Telegram username checks are
    # extremely rate-limited, so user-facing search should use a slowly
    # pre-verified stock instead of burning MTProto requests on every click.
    USERNAME_STOCK_ENABLED: bool = True
    USERNAME_STOCK_WORKER_ENABLED: bool = True
    USERNAME_LIVE_CHECK_ENABLED: bool = False
    USERNAME_CUSTOM_LIVE_CHECK_ENABLED: bool = False
    USERNAME_STOCK_TTL_HOURS: int = 6
    USERNAME_STOCK_HOLD_MINUTES: int = 15
    USERNAME_STOCK_CHECK_INTERVAL_SECONDS: float = 15.0
    USERNAME_STOCK_MIN_5: int = 10
    USERNAME_STOCK_MIN_6: int = 12
    USERNAME_STOCK_MIN_7: int = 12

    @field_validator("RAILWAY_PUBLIC_URL")
    @classmethod
    def trim_public_url(cls, value: str) -> str:
        return value.rstrip("/")

    @property
    def admin_id_set(self) -> set[int]:
        result: set[int] = set()
        for item in self.ADMIN_IDS.replace(";", ",").split(","):
            item = item.strip()
            if item:
                result.add(int(item))
        return result

    @property
    def webhook_url(self) -> str:
        return f"{self.RAILWAY_PUBLIC_URL}/telegram/webhook"

    def rub_price(self, tariff: str) -> int:
        return {
            "1d": self.PRIME_1_DAY_PRICE_RUB,
            "7d": self.PRIME_7_DAYS_PRICE_RUB,
            "30d": self.PRIME_30_DAYS_PRICE_RUB,
            "forever": self.PRIME_FOREVER_PRICE_RUB,
        }[tariff]

    def stars_price(self, tariff: str) -> int:
        return {
            "1d": self.PRIME_1_DAY_PRICE_STARS,
            "7d": self.PRIME_7_DAYS_PRICE_STARS,
            "30d": self.PRIME_30_DAYS_PRICE_STARS,
            "forever": self.PRIME_FOREVER_PRICE_STARS,
        }[tariff]


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
