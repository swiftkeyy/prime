from __future__ import annotations

import re

USERNAME_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_]{4,31}$")
PROMO_RE = re.compile(r"^[A-Z0-9_-]{3,32}$")


def is_valid_username(username: str) -> bool:
    if not 5 <= len(username) <= 32:
        return False
    if not USERNAME_RE.match(username):
        return False
    if username.startswith("_") or username.endswith("_"):
        return False
    if "__" in username:
        return False
    return True


def normalize_promo(code: str) -> str:
    return code.strip().upper()


def is_valid_promo(code: str) -> bool:
    return bool(PROMO_RE.match(normalize_promo(code)))
