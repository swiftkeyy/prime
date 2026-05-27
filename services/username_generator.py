from __future__ import annotations

import random
import string
from collections import deque

RECENT: deque[str] = deque(maxlen=512)
LETTERS = string.ascii_lowercase
DIGITS = string.digits


def _valid_candidate(candidate: str) -> bool:
    if candidate[0].isdigit() or candidate[0] == "_":
        return False
    if candidate.endswith("_"):
        return False
    if "__" in candidate:
        return False
    return True


def generate_username(length: int, digits_enabled: bool, underscore_enabled: bool, style_mode: str) -> str:
    if length not in (5, 6, 7):
        raise ValueError("PRIME NICK supports username length 5, 6 or 7 only")

    alphabet = LETTERS
    if digits_enabled or style_mode == "mixed":
        alphabet += DIGITS
    if underscore_enabled:
        alphabet += "_"

    # First char must be a Latin letter. This also improves availability quality.
    for _ in range(200):
        chars = [random.choice(LETTERS)]
        chars.extend(random.choice(alphabet) for _ in range(length - 1))
        candidate = "".join(chars)
        if candidate not in RECENT and _valid_candidate(candidate):
            RECENT.append(candidate)
            return candidate

    # Fallback with deterministic first char; practically unreachable.
    candidate = random.choice(LETTERS) + "".join(random.choice(LETTERS) for _ in range(length - 1))
    RECENT.append(candidate)
    return candidate
