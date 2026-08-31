"""The composition root: `python -m half` or `half run`.

Everything else in this package is a library. This is the one place that reads
the environment, builds the real transport, and wires the pieces into a running
program — the piece whose absence meant story 2's adapter could not actually be
started.

Credentials are read here and nowhere else, and never written into a store tree
(AD-11): a store is exportable and replayable, so a token inside one would be
handed to the main in an archive and resurrected on every replay.
"""

from __future__ import annotations

import asyncio
import logging
import os
import sys

from half.actor.registry import ActorRegistry, validate_main_id
from half.actor.runtime import Runtime
from half.channel.telegram import TelegramChannel
from half.channel.telegram_transport import PTBTransport
from half.config import TELEGRAM_TOKEN_ENV, Config, load
from half.errors import HalfError
from half.store.store import Store

logger = logging.getLogger("half")


def build(config: Config, token: str) -> tuple[TelegramChannel, ActorRegistry]:
    """Wire the object graph. Separate from ``main`` so it is testable."""
    for main_id in config.mains.values():
        validate_main_id(main_id)

    channel = TelegramChannel(transport=PTBTransport(token), mains=dict(config.mains))
    registry = ActorRegistry(config.root)

    # Restore reachability from each main's log, or a restart reports everyone
    # as never-contacted and nothing unprompted can be sent until they write.
    for main_id in config.mains.values():
        with Store(config.root / main_id) as store:
            channel.reach.rebuild_from(main_id, store.log)

    return channel, registry


async def serve(config: Config, token: str) -> None:
    channel, registry = build(config, token)
    logger.info("serving %d main(s) from %s", len(config.mains), config.root)
    try:
        await Runtime(channel=channel, registry=registry).run()
    finally:
        registry.close()


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(
        level=os.environ.get("HALF_LOG_LEVEL", "INFO"),
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    try:
        config = load()
        if not config.mains:
            raise HalfError(
                "no mains configured; set HALF_MAINS='<chat_id>:<main_id>'"
            )
        token = os.environ.get(TELEGRAM_TOKEN_ENV, "")
        asyncio.run(serve(config, token))
    except HalfError as exc:
        print(f"half: {exc}", file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        return 0
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
