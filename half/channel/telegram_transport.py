"""The concrete Telegram transport — the only module that touches the network.

Kept apart from ``telegram.py`` on purpose. The adapter holds every rule that
matters (reachability, splitting, third-party refusal) and is exercised
offline against a fake; this file is the thin edge that turns those decisions
into HTTP, and has no logic worth testing without a live bot.

Long-polling, so no public URL is required — the reason AD-16 makes Telegram
the self-host default.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any, AsyncIterator

from half.errors import ChannelError

logger = logging.getLogger(__name__)

#: Ceiling on the reconnect backoff.
MAX_BACKOFF = 60.0

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

        **At-least-once.** The offset is committed only *after* the consumer
        finishes with an update — ``yield`` hands control away, so advancing
        first meant a crash mid-turn told Telegram the message was delivered
        while Half had never stored it. Committing after redelivers instead,
        and the turn is idempotent.

        A transient fault must not end the loop: an exception here used to kill
        the generator, so one network blip stopped the bot permanently.
        """
        backoff = 1.0
        while True:
            try:
                updates = await self._bot.get_updates(
                    offset=self._offset, timeout=POLL_TIMEOUT
                )
                backoff = 1.0
            except asyncio.CancelledError:
                raise
            except Exception:  # noqa: BLE001 - a blip must not end polling
                logger.warning("get_updates failed; retrying in %.0fs", backoff)
                await asyncio.sleep(backoff)
                backoff = min(backoff * 2, MAX_BACKOFF)
                continue

            for update in updates:
                payload = normalize(update)
                if payload is not None:
                    yield payload
                # Committed only once the consumer has finished with it.
                self._offset = update.update_id + 1

    async def send_message(self, chat_id: str, text: str) -> str:
        sent = await self._bot.send_message(chat_id=chat_id, text=text)
        return str(sent.message_id)


def normalize(update: Any) -> dict | None:
    """One Telegram update to the dict the adapter reads, or None to skip.

    Module-level and pure so the contract between this file and
    ``TelegramChannel.receive`` is testable without a network — renaming a key
    here used to leave every test green while Half silently discarded all
    inbound.

    Edited messages count: a main correcting themselves is still the main
    speaking. Captions count too, so a photo with words is not dropped.
    """
    message = getattr(update, "message", None) or getattr(update, "edited_message", None)
    if message is None:
        return None
    text = getattr(message, "text", None) or getattr(message, "caption", None)
    if not text:
        return None
    return {
        "chat_id": str(message.chat_id),
        "text": text,
        "message_id": str(message.message_id),
        "date": message.date.timestamp(),
    }
