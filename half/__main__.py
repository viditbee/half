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
from dataclasses import dataclass

from half.actor.registry import ActorRegistry, validate_main_id
from half.actor.runtime import Runtime
from half.channel.telegram import TelegramChannel
from half.channel.telegram_transport import PTBTransport
from half.config import TELEGRAM_TOKEN_ENV, Config, load
from half.crisis.classifier import (
    PER_CALL_MICRO_USD,
    PER_PASS_MICRO_USD,
    SecondOpinion,
)
from half.errors import HalfError, ModelError
from half.model.anthropic import AnthropicProvider
from half.model.anthropic_transport import SDKTransport
from half.model.budget import Budget
from half.model.port import Classifier
from half.model.tier import Tiers
from half.schedule.tick import Scheduler
from half.secrets import FileSecretStore
from half.store.sources import LocalSourceStore
from half.store.store import Store

logger = logging.getLogger("half")


@dataclass(frozen=True, slots=True)
class Wiring:
    """Everything a running Half needs, constructed once."""

    channel: TelegramChannel
    registry: ActorRegistry
    secrets: FileSecretStore
    sources: dict[str, LocalSourceStore]
    #: The due-time queue (AD-9). Constructed here rather than inside ``serve``
    #: so that "the tick runs in the shipped composition" is something a test
    #: can assert without starting a process — the failure this story exists to
    #: end is a surface reachable only from tests.
    scheduler: Scheduler
    #: The crisis classifier's holders, one per main that has both a tier and a
    #: key (story 6d). Always constructed and possibly empty: a deployment with
    #: neither gets story 6a's offline gate, which is a supported shape rather
    #: than a broken one.
    second: SecondOpinion


def build(config: Config, token: str) -> Wiring:
    """Wire the object graph. Separate from ``main`` so it is testable.

    Three stories have now shipped a surface reachable only from tests, so the
    credential store and the per-main source stores are constructed here even
    though ingestion is not yet scheduled — an object graph nothing builds is
    an object graph nobody has run.
    """
    for main_id in config.mains.values():
        validate_main_id(main_id)

    channel = TelegramChannel(transport=PTBTransport(token), mains=dict(config.mains))
    registry = ActorRegistry(config.root)

    # Credentials sit beside the tree holding every main, never inside it, so
    # export and replay cannot carry them (AD-11).
    secrets = FileSecretStore.beside(config.root)

    # One source store per main. Bodies are never kept; these hold receipts.
    sources = {
        main_id: LocalSourceStore(config.root / main_id / "sources")
        for main_id in config.mains.values()
    }

    # Restore reachability from each main's log, or a restart reports everyone
    # as never-contacted and nothing unprompted can be sent until they write.
    for main_id in config.mains.values():
        with Store(config.root / main_id) as store:
            channel.reach.rebuild_from(main_id, store.log)

    # The due-time queue (AD-9). Every main carries their own ``next_pass_at``
    # at their local pre-dawn with jitter; the tick drains what is due under
    # bounded concurrency, holding a file lock so a second worker cannot drain
    # the same queue. The pass body is a later story, so what it runs today is
    # ``Nothing`` — which is a first-class outcome, not a placeholder (AD-27).
    #
    # The lock lives in ``config.root``, beside the mains rather than inside any
    # one of them: what it excludes is a second drain of this queue, not a
    # second write to one main — that is still the actor's mutex, and the tick
    # goes through it like everything else.
    scheduler = Scheduler(
        registry=registry,
        mains=tuple(config.mains.values()),
        root=config.root,
    )

    return Wiring(channel=channel, registry=registry, secrets=secrets,
                  sources=sources, scheduler=scheduler,
                  second=second_opinion(config, secrets))


def second_opinion(config: Config, secrets: FileSecretStore) -> SecondOpinion:
    """The crisis classifier, for the mains a deployment has equipped (6d).

    **Nothing here can fail the boot, and nothing here can fail a turn.** A main
    with no tier, no key, or a tier this build has no model for simply gets no
    second opinion — which is story 6a's behaviour: the phrase table decides
    alone, offline, and the safe word still works with the provider down. The
    alternative is a crisis subsystem that refuses to start because a key is
    missing, which is the omission headline arriving at boot time.

    **The narrow holder, never the provider.** ``classifier()`` hands back an
    object with one method that returns a label — no generation, no batch, no
    ledger to reset. ``SecondOpinion`` refuses a wider one, so this is checked
    rather than merely intended.

    **One ledger per main**, because a provider's ``Spend`` is shared by
    everything it hands out and a ceiling shared across mains would be one
    main's quiet turn spending another main's.

    The key comes from the ``SecretStore``, which lives beside the store tree
    and never inside it, so it cannot reach an export or a replay (AD-11).
    """
    holders: dict[str, Classifier] = {}
    for main_id in config.mains.values():
        tier = config.tier_for(main_id)
        if tier is None:
            logger.info(
                "main=%s has no model tier; the crisis phrase table decides "
                "alone for them", main_id
            )
            continue
        try:
            provider = AnthropicProvider(
                SDKTransport.from_secrets(secrets, main_id),
                tiers=Tiers.parse({main_id: tier}),
                budget=Budget(
                    per_call_micro_usd=PER_CALL_MICRO_USD,
                    per_pass_micro_usd=PER_PASS_MICRO_USD,
                ),
            )
        except ModelError:
            # No key, an unknown tier, a missing SDK. Each is a deployment that
            # has not equipped this main, and none of them is a reason to hold
            # up a Half that can still detect a disclosure offline. The class
            # only — a provider's own message can quote what it was sent
            # (AD-22).
            logger.warning(
                "main=%s has no usable model; the crisis phrase table decides "
                "alone for them", main_id
            )
            continue
        holders[main_id] = provider.classifier()
    return SecondOpinion(holders)


async def serve(config: Config, token: str) -> None:
    """Run the inbound loop and the due-time queue together, until cancelled.

    A ``TaskGroup`` rather than a bare ``gather``: if either half dies the
    other is cancelled and the process exits, instead of a Half that answers
    messages but has silently stopped being scheduled — or the reverse, which
    is worse, because a scheduler running against a dead inbound path is a Half
    nobody can reach and that still thinks about them.
    """
    wiring = build(config, token)
    logger.info("serving %d main(s) from %s", len(config.mains), config.root)
    try:
        async with asyncio.TaskGroup() as group:
            ticker = group.create_task(wiring.scheduler.run_forever())
            try:
                await Runtime(
                    channel=wiring.channel,
                    registry=wiring.registry,
                    # The crisis classifier reaches the shipped product here
                    # and nowhere else. A surface reachable only from a test is
                    # a surface nobody has run, and this one exists to catch
                    # the disclosures the phrase table cannot (story 6d).
                    second=wiring.second,
                ).run()
            finally:
                # The inbound loop is the process's life; the ticker is not
                # allowed to outlive it. Without this, a receive loop that
                # ended would leave a Half nobody can reach still thinking
                # about people on a schedule.
                ticker.cancel()
    finally:
        wiring.registry.close()


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
