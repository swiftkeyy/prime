from __future__ import annotations

import re

VOWELS = set("aeiouy")


def username_score(username: str) -> int:
    raw = username.lower().lstrip("@")
    score = 100

    score -= max(0, len(raw) - 5) * 9
    score -= sum(ch.isdigit() for ch in raw) * 8
    score -= raw.count("_") * 12
    if re.search(r"([a-z0-9])\1", raw):
        score -= 10
    if re.search(r"[bcdfghjklmnpqrstvwxz]{4}", raw):
        score -= 12
    if re.search(r"[aeiouy]{3}", raw):
        score -= 8
    if raw[-1:] in "xzvkr":
        score += 5
    if any(ch in VOWELS for ch in raw) and any(ch not in VOWELS and ch.isalpha() for ch in raw):
        score += 6

    return max(1, min(100, score))


def rarity_label(username: str) -> str:
    score = username_score(username)
    if score >= 88:
        return "legendary"
    if score >= 74:
        return "premium"
    if score >= 58:
        return "rare"
    return "clean"


def rarity_line(username: str) -> str:
    labels = {
        "legendary": "легендарный",
        "premium": "премиальный",
        "rare": "редкий",
        "clean": "чистый",
    }
    label = rarity_label(username)
    return f"{labels[label]} · score {username_score(username)}/100"
