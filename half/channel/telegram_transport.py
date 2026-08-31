"""The concrete Telegram transport — the only module that touches the network.

Kept apart from ``telegram.py`` on purpose. The adapter holds every rule that
matters (reachability, splitting, third-party refusal) and is exercised
offline against a fake; this file is the thin edge that turns those decisions
into HTTP, and has no logic worth testing without a live bot.

Long-polling, so no public URL is required — the reason AD-16 makes Telegram
the self-host default.
"""

from __future__ import annotations

from typing import AsyncIterator

from half.errors import ChannelError

#: Seconds a long-poll waits before returning empty. Telegram allows up to 50.
POLL_TIMEOUT = 30


class PTBTransport:
    """``Transport`` implemented over python-telegram-bot."""

    def __init__(self, token: str) -> None:
        if not token:
            raise ChannelError(
                "no Telegram bot token; set TELEGRAM_BOT_TOKEN in the environment "
                "(never in a store tree — AD-11)"
            )
        try:
            from telegram import Bot
        except ModuleNotFoundError as exc:  # pragma: no cover - packaging fault
            raise ChannelError(
                "python-telegram-bot is not installed; run `uv sync`"
            ) from exc
        self._bot = Bot(token)
        self._offset: int | None = None

    async def poll(self) -> AsyncIterator[dict]:
        """Yield normalized updates forever.

        The offset is advanced past each processed update so Telegram stops
        redelivering it — the only piece of state this class keeps.
        """
        while True:
            updates = await self._bot.get_updates(
                offset=self._offset, timeout=POLL_TIMEOUT
            )
            for update in updates:
                self._offset = update.update_id + 1
                message = update.message
                if message is None or message.text is None:
                    continue
                yield {
                    "chat_id": str(message.chat_id),
                    "text": message.text,
                    "message_id": str(message.message_id),
                    "date": message.date.timestamp(),
                }

    async def send_message(self, chat_id: str, text: str) -> str:
        sent = await self._bot.send_message(chat_id=chat_id, text=text)
        return str(sent.message_id)
