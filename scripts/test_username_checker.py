from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv

load_dotenv(ROOT / ".env")

from config import Settings
from services.username_checker import build_checker, is_username_available


async def main() -> None:
    usernames = [arg.lstrip("@").lower() for arg in sys.argv[1:]] or ["roman", "angel", "dobro"]
    settings = Settings()
    checker = build_checker(settings)
    start = getattr(checker, "start", None)
    close = getattr(checker, "close", None)

    if start:
        await start()

    try:
        for username in usernames:
            result = await is_username_available(username, checker=checker, redis=None)
            print(f"@{username}: {'FREE / NOT OCCUPIED' if result else 'BUSY / NOT USABLE'}")
    finally:
        if close:
            await close()


if __name__ == "__main__":
    asyncio.run(main())
