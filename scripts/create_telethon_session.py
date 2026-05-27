from __future__ import annotations

import os

from telethon.sync import TelegramClient
from telethon.sessions import StringSession


def main() -> None:
    api_id = int(os.getenv("TELEGRAM_API_ID") or input("TELEGRAM_API_ID: ").strip())
    api_hash = os.getenv("TELEGRAM_API_HASH") or input("TELEGRAM_API_HASH: ").strip()

    print("\nВойди в обычный Telegram-аккаунт, который будет использоваться только для проверки username.")
    print("Сессия нужна, потому что Bot API не умеет надёжно проверять занятые личные username.\n")

    with TelegramClient(StringSession(), api_id, api_hash) as client:
        session = client.session.save()

    print("\nTELEGRAM_STRING_SESSION:\n")
    print(session)
    print("\nСкопируй это значение в Railway Variables как TELEGRAM_STRING_SESSION.")


if __name__ == "__main__":
    main()
