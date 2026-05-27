from __future__ import annotations

import os

from telethon.sync import TelegramClient
from telethon.sessions import StringSession


def main() -> None:
    api_id = int(os.getenv("TELEGRAM_API_ID") or input("TELEGRAM_API_ID: ").strip())
    api_hash = os.getenv("TELEGRAM_API_HASH") or input("TELEGRAM_API_HASH: ").strip()

    print("\nPRIME NICK · генератор MTProto StringSession")
    print("Войди в отдельный Telegram-аккаунт, который будет использоваться только для проверки username.")
    print("Для production лучше создать 3–5 сессий и вставить их в TELEGRAM_STRING_SESSIONS через запятую.\n")

    with TelegramClient(StringSession(), api_id, api_hash) as client:
        session = client.session.save()

    print("\nTELEGRAM_STRING_SESSION:\n")
    print(session)
    print("\nДля одного аккаунта вставь в Railway как TELEGRAM_STRING_SESSION.")
    print("Для пула аккаунтов добавь эту строку к TELEGRAM_STRING_SESSIONS через запятую.")


if __name__ == "__main__":
    main()
