from __future__ import annotations

import re
from urllib.parse import unquote_plus

from database.models import User

_REF_PREFIX_RE = re.compile(r"^(ref|r|invite|start)[_\-:=]", re.IGNORECASE)


def normalize_referral_payload(payload: str | None) -> str | None:
    if not payload:
        return None

    value = unquote_plus(payload).strip()
    if not value:
        return None

    if "start=" in value:
        value = value.split("start=", 1)[1].split("&", 1)[0].strip()

    value = value.strip().lstrip("@").strip()
    value = _REF_PREFIX_RE.sub("", value).strip()

    if not re.fullmatch(r"[A-Za-z0-9_\-]{3,64}", value):
        return None
    if value.lower() in {"admin", "start", "promo", "prime", "menu"}:
        return None
    return value


def make_referral_payload(user: User) -> str:
    return f"ref_{user.referral_code}"


def make_referral_link(bot_username: str, user: User) -> str:
    username = bot_username.strip().lstrip("@")
    return f"https://t.me/{username}?start={make_referral_payload(user)}"
