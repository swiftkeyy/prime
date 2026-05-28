from __future__ import annotations

import re

VOWELS = set("aeiouy")


def username_score(username: str) -> int:
    raw = username.lower().lstrip("@")
    score = 58

    if len(raw) == 5:
        score += 22
    elif len(raw) == 6:
        score += 10
    elif len(raw) == 7:
        score += 4
    else:
        score -= max(0, len(raw) - 7) * 6

    digit_count = sum(ch.isdigit() for ch in raw)
    score -= digit_count * 18
    score -= raw.count("_") * 22
    if re.search(r"([a-z0-9])\1", raw):
        score -= 14
    if re.search(r"[bcdfghjklmnpqrstvwxz]{4}", raw):
        score -= 12
    if re.search(r"[aeiouy]{3}", raw):
        score -= 10
    if raw[-1:] in "xzvkr" and digit_count == 0:
        score += 2
    if any(ch in VOWELS for ch in raw) and any(ch not in VOWELS and ch.isalpha() for ch in raw):
        score += 6
    if raw.isalpha():
        score += 12
    if len(set(raw)) == len(raw):
        score += 4
    if raw.startswith(("x", "z")) and digit_count > 0:
        score -= 4

    return max(1, min(100, score))


def rarity_label(username: str) -> str:
    score = username_score(username)
    if score >= 95:
        return "legendary"
    if score >= 82:
        return "premium"
    if score >= 66:
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
