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

    USER_AGREEMENT_LINK: str = ""
    PRIVACY_POLICY_LINK: str = ""
    PRIME_TERMS_LINK: str = ""

    USERNAME_CHECK_MODE: Literal["http", "mock", "fragment"] = "fragment"
    USERNAME_CHECK_TIMEOUT: int = 7
    FRAGMENT_CHECK_DELAY_SECONDS: float = 0.8
    SEARCH_MAX_CANDIDATES: int = 35
    PRIME_SEARCH_MAX_CANDIDATES: int = 70

    FREE_RESERVED_USERNAMES_LIMIT: int = 10
    PRIME_RESERVED_USERNAMES_LIMIT: int = 30

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
