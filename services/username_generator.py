from __future__ import annotations

import random
import re
import string
from collections import deque

RECENT: deque[str] = deque(maxlen=4096)
LETTERS = string.ascii_lowercase
DIGITS = string.digits

VOWELS = "aeiouy"
CONSONANTS = "bcdfghjklmnprstvwz"
RARE_CONSONANTS = "vzkwxqprslmn"

# These short words are nice, but they are almost always occupied or not settable.
# Keep them out of automatic 5-symbol scan so PRIME mode does not waste checks on
# obvious dead usernames like roman/angel/dobro.
COMMON_TAKEN_5 = {
    "admin", "angel", "apple", "audio", "black", "bravo", "cloud", "dobro", "demon",
    "green", "house", "joker", "login", "magic", "media", "money", "music", "night",
    "prime", "queen", "roman", "sport", "super", "titan", "video", "world", "zapor",
}

# Curated word-like pool. For 6/7 symbols it gives brand-style names. For 5 symbols
# it is used only as a small accent; procedural generation below does the real work.
WORD_BANK: dict[int, list[str]] = {
    5: [
        "bolen", "miron", "sever", "veter", "sonar", "orbit", "kvant", "lumen",
        "nolan", "vital", "kredo", "nevan", "solen", "moral", "davor", "levin",
        "novak", "radon", "zoran", "valor", "raven", "rival", "venom", "vesta",
        "liver", "dorin", "karat", "buran", "lunar", "sokol", "volna", "iskra",
        "ozera", "dobar", "zavir", "kovir", "nurex", "vazir", "loren", "darel",
        "zolen", "virex", "kavor", "lazir", "zomir", "narox", "velix", "zorix",
    ],
    6: [
        "vektor", "neuron", "zvezda", "severo", "dobrov", "lurion", "solven", "radion",
        "moreno", "vostok", "safari", "lancer", "veltor", "kosmos", "mirage", "novara",
        "varian", "kursor", "legion", "frozen", "aurion", "zenith", "nordic", "vector",
        "vertex", "monaco", "satori", "orionx", "dorian", "zefiro", "bravoq", "karelo",
    ],
    7: [
        "skyline", "solaris", "neoflow", "zorovan", "veloria", "nordway", "luminor", "dobrony",
        "krypton", "varline", "miravel", "soulver", "voltair", "astrion", "moravia", "novaline",
        "radovel", "zetvora", "lorevan", "nikavor", "vostera", "santori", "lazurio", "korveta",
        "lumiere", "oriento", "vetrilo", "dobrava", "bolivar", "zarento", "ronavel", "severin",
    ],
}

STARTS = ["b", "br", "d", "dr", "f", "g", "k", "kr", "l", "m", "n", "p", "pr", "r", "s", "st", "v", "vr", "z", "zn"]
MIDDLES = ["a", "e", "i", "o", "u", "y", "ar", "er", "ir", "or", "ur", "av", "ev", "ov", "an", "en", "on", "el", "al", "ol"]
ENDS = ["n", "r", "v", "l", "s", "t", "m", "x", "en", "er", "or", "ar", "on", "ov", "in", "io", "is"]

SYLLABLES = [
    "ba", "be", "bi", "bo", "bu", "va", "ve", "vi", "vo", "da", "de", "di", "do",
    "za", "ze", "zi", "zo", "ka", "ke", "ki", "ko", "la", "le", "li", "lo",
    "ma", "me", "mi", "mo", "na", "ne", "ni", "no", "ra", "re", "ri", "ro",
    "sa", "se", "si", "so", "ta", "te", "ti", "to", "fa", "fi", "fo", "xy", "xo", "xe",
]
SOFT_ENDS_1 = ["n", "r", "v", "l", "s", "t", "m", "x", "z", "k"]
SOFT_ENDS_2 = ["en", "er", "or", "ar", "on", "ov", "in", "io", "el", "al", "ix", "ex"]
LEET_MAP = {"a": "4", "e": "3", "i": "1", "o": "0", "s": "5", "t": "7"}

CYR_TO_LAT = {
    "а": "a", "б": "b", "в": "v", "г": "g", "д": "d", "е": "e", "ё": "e",
    "ж": "zh", "з": "z", "и": "i", "й": "y", "к": "k", "л": "l", "м": "m",
    "н": "n", "о": "o", "п": "p", "р": "r", "с": "s", "т": "t", "у": "u",
    "ф": "f", "х": "h", "ц": "c", "ч": "ch", "ш": "sh", "щ": "sch", "ъ": "",
    "ы": "y", "ь": "", "э": "e", "ю": "yu", "я": "ya",
}


def transliterate_to_latin(value: str) -> str:
    result: list[str] = []
    for char in value.lower():
        result.append(CYR_TO_LAT.get(char, char))
    return "".join(result)


def normalize_username_seed(value: str) -> str:
    value = transliterate_to_latin(value)
    value = value.strip().lower()
    value = value.replace("https://t.me/", "").replace("http://t.me/", "").replace("t.me/", "")
    value = value.replace("@", "")
    value = re.sub(r"\s+", "", value)
    value = re.sub(r"[^a-z0-9_]", "", value)
    value = re.sub(r"_+", "_", value)
    value = value.strip("_")
    if value and not value[0].isalpha():
        value = "n" + value
    return value[:24]


def _valid_candidate(candidate: str) -> bool:
    if not 5 <= len(candidate) <= 32:
        return False
    if candidate[0].isdigit() or candidate[0] == "_":
        return False
    if candidate.endswith("_"):
        return False
    if "__" in candidate:
        return False
    return bool(re.fullmatch(r"[a-z][a-z0-9_]{4,31}", candidate))


def _looks_smooth(candidate: str) -> bool:
    if len(candidate) < 5:
        return False
    if re.search(r"([a-z0-9])\1", candidate):
        return False
    if re.search(r"[bcdfghjklmnpqrstvwxz]{4}", candidate):
        return False
    if re.search(r"[aeiouy]{3}", candidate):
        return False
    return True


def _five_letter_brand() -> str:
    """Generate many clean 5-char pseudo-words instead of replaying occupied words."""
    templates = [
        "cvcvc", "cvvcc", "cvccv", "ccvcv", "cvcvx", "cvvcv", "vcvcv",
    ]
    for _ in range(160):
        template = random.choice(templates)
        chars: list[str] = []
        for idx, token in enumerate(template):
            if token == "c":
                pool = RARE_CONSONANTS if idx in (0, 4) and random.random() < 0.55 else CONSONANTS
                chars.append(random.choice(pool))
            elif token == "v":
                chars.append(random.choice(VOWELS))
            elif token == "x":
                chars.append(random.choice("xzkv"))
            else:
                chars.append(random.choice(LETTERS))
        candidate = "".join(chars)
        candidate = re.sub(r"([aeiouy])\1+", r"\1", candidate)
        candidate = re.sub(r"([bcdfghjklmnprstvwzxq])\1+", r"\1", candidate)
        if len(candidate) != 5:
            continue
        if candidate in COMMON_TAKEN_5:
            continue
        if _valid_candidate(candidate) and _looks_smooth(candidate):
            return candidate

    # Fallback is still pronounceable and avoids famous occupied examples.
    bank = [item for item in WORD_BANK[5] if item not in COMMON_TAKEN_5]
    return random.choice(bank)


def _syllable_word(length: int) -> str:
    for _ in range(160):
        if length == 5:
            raw = _five_letter_brand()
        elif length == 6:
            raw = random.choice(SYLLABLES) + random.choice(SYLLABLES) + random.choice(SOFT_ENDS_2)
        elif length == 7:
            raw = random.choice(SYLLABLES) + random.choice(SYLLABLES) + random.choice(SYLLABLES) + random.choice(SOFT_ENDS_1)
        else:
            raw = random.choice(SYLLABLES) + random.choice(SYLLABLES) + random.choice(SOFT_ENDS_2)

        raw = re.sub(r"([aeiouy])\1+", r"\1", raw)
        raw = re.sub(r"([bcdfghjklmnprstvwzxq])\1+", r"\1", raw)
        if len(raw) == length and _valid_candidate(raw) and _looks_smooth(raw):
            return raw

    bank = [item for item in WORD_BANK.get(length, WORD_BANK[5]) if item not in COMMON_TAKEN_5]
    return random.choice(bank)


def _word_like(length: int) -> str:
    bank = [item for item in WORD_BANK.get(length, []) if item not in COMMON_TAKEN_5]
    if length == 5:
        # Real 5-letter words are usually reserved/collectible or already taken.
        # Use generated brand-like pseudo-words instead of showing fake hopes like
        # sever/kvant/novak that Telegram refuses in the username screen.
        return _five_letter_brand()

    if bank and random.random() < 0.82:
        return random.choice(bank)
    return _syllable_word(length)


def _maybe_leet(word: str, chance: float) -> str:
    if random.random() > chance:
        return word
    indexes = [idx for idx, char in enumerate(word) if idx > 0 and char in LEET_MAP]
    if not indexes:
        return word
    idx = random.choice(indexes)
    return word[:idx] + LEET_MAP[word[idx]] + word[idx + 1 :]


def _maybe_digit_suffix(word: str, length: int) -> str:
    if length < 5:
        return word
    if len(word) == length:
        pos = random.randint(max(1, length - 2), length - 1)
        return word[:pos] + random.choice(DIGITS) + word[pos + 1 :]
    return word[: length - 1] + random.choice(DIGITS)


def _maybe_underscore(length: int) -> str | None:
    if length < 6:
        return None
    left_len = random.randint(2, length - 3)
    right_len = length - left_len - 1
    left = _syllable_word(max(5, left_len + 3))[:left_len]
    right = _syllable_word(max(5, right_len + 3))[:right_len]
    candidate = f"{left}_{right}"
    return candidate if _valid_candidate(candidate) and len(candidate) == length else None


def generate_username(length: int, digits_enabled: bool, underscore_enabled: bool, style_mode: str) -> str:
    if length not in (5, 6, 7):
        raise ValueError("PRIME NICK supports username length 5, 6 or 7 only")

    for _ in range(500):
        if underscore_enabled and random.random() < 0.12:
            candidate = _maybe_underscore(length) or _word_like(length)
        else:
            candidate = _word_like(length)

        if style_mode == "brutal":
            candidate = candidate[:-1] + random.choice("xzvk")
        elif style_mode == "soft":
            candidate = re.sub(r"[xzq]", random.choice("lnr"), candidate)
        elif style_mode == "brand" and length >= 6 and random.random() < 0.35:
            candidate = random.choice(["neo", "nova", "lumi", "velo", "nord"] + WORD_BANK.get(length, []))[:length]
        elif style_mode == "techno":
            candidate = _maybe_leet(candidate, 0.45)

        if digits_enabled or style_mode in {"mixed", "techno"}:
            if length == 5 and random.random() < 0.72:
                candidate = _maybe_digit_suffix(candidate, length)
            else:
                candidate = _maybe_leet(candidate, 0.22 if style_mode != "mixed" else 0.35)

        if candidate in COMMON_TAKEN_5:
            continue
        if candidate not in RECENT and len(candidate) == length and _valid_candidate(candidate) and _looks_smooth(candidate):
            RECENT.append(candidate)
            return candidate

    candidate = _five_letter_brand() if length == 5 else _syllable_word(length)
    RECENT.append(candidate)
    return candidate


def _append_if_valid(result: list[str], seen: set[str], value: str) -> None:
    value = normalize_username_seed(value)
    if _valid_candidate(value) and value not in seen:
        seen.add(value)
        result.append(value)


def generate_username_variants(seed: str, limit: int = 160) -> list[str]:
    """Generate ordered, good-looking nickname ideas from user's desired nickname.

    The function does not check availability. It returns valid Telegram usernames
    that can later be checked through strict Telegram MTProto and reservations.
    """
    base = normalize_username_seed(seed)
    if not base:
        return []

    result: list[str] = []
    seen: set[str] = set()

    def add(value: str) -> None:
        if len(result) < limit:
            _append_if_valid(result, seen, value)

    # Direct and clean options first. They will be filtered by the strict checker.
    add(base)
    add(base.replace("0", "o").replace("1", "i").replace("3", "e").replace("4", "a"))

    endings = [
        "x", "y", "io", "go", "ov", "ev", "off", "one", "on", "er", "or", "id",
        "ly", "to", "me", "way", "flow", "line", "wave", "net", "hub", "lab", "zone",
        "sky", "prime", "nick", "real", "core", "nova", "max", "pro", "ix", "ex", "rx",
    ]
    prefixes = ["i", "x", "go", "my", "the", "neo", "mr", "dr", "top", "one", "hey", "iam"]

    for suffix in endings:
        add(base + suffix)
    for prefix in prefixes:
        add(prefix + base)

    if base.endswith(("a", "e", "i", "o", "u", "y")):
        stem = base[:-1]
        for suffix in ["o", "a", "y", "io", "ov", "en", "er", "on", "ix", "ex"]:
            add(stem + suffix)
    else:
        for suffix in ["a", "o", "y", "io", "ov", "en", "er", "on", "ix", "ex"]:
            add(base + suffix)

    swaps = [("a", "o"), ("o", "a"), ("e", "i"), ("i", "e"), ("y", "i")]
    for src, dst in swaps:
        if src in base:
            add(base.replace(src, dst, 1))

    compact = re.sub(r"[aeiouy]", "", base)
    if len(compact) >= 3:
        if not compact[0].isalpha():
            compact = "n" + compact
        for suffix in ["io", "ov", "on", "er", "x", "y", "ix", "ex"]:
            add(compact + suffix)

    stem = base[:12]
    for suffix in ["nova", "luna", "vibe", "wave", "flow", "core", "line", "space", "gram"]:
        add(stem + suffix)

    if len(base) < 5:
        for suffix in ["nick", "flow", "line", "zone", "prime", "wave", "core"]:
            add(base + suffix)

    return result[:limit]
