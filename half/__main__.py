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
from half.consolidate.judge import (
    CLASSIFY_TIER as JUDGE_TIER,
    PER_CALL_MICRO_USD as JUDGE_PER_CALL_MICRO_USD,
    PER_PASS_MICRO_USD as JUDGE_PER_PASS_MICRO_USD,
    Judges,
)
from half.consolidate.pass_ import TensionPass
from half.correction.candidate import (
    CLASSIFY_TIER as CORRECTION_TIER,
    PER_CALL_MICRO_USD as CORRECTION_PER_CALL_MICRO_USD,
    PER_PASS_MICRO_USD as CORRECTION_PER_PASS_MICRO_USD,
    Widening,
)
from half.crisis.classifier import (
    CLASSIFY_TIER,
    PER_CALL_MICRO_USD,
    PER_PASS_MICRO_USD,
    SecondOpinion,
)
from half.errors import HalfError, ModelError
from half.model.anthropic import AnthropicProvider
from half.model.anthropic_transport import SDKTransport
from half.model.budget import Budget
from half.model.port import Classifier, Generator
from half.model.tier import Tiers
from half.questions.engine import QuestionEngine
from half.schedule.tick import Scheduler
from half.surface.morning import MorningPass, Mornings, MorningSurface
from half.secrets import FileSecretStore
from half.voice.gate import (
    PER_CALL_MICRO_USD as VOICE_PER_CALL_MICRO_USD,
    PER_PASS_MICRO_USD as VOICE_PER_PASS_MICRO_USD,
    Voice,
)
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
    #: What the mornings did — counts by reason, never content (AD-22, AD-32).
    #: Owned here rather than inside the surface so that the outcome of every
    #: morning has somewhere to go in the shipped process: before review each
    #: one was discarded, which made a permanently silent main indistinguishable
    #: from a main with a quiet life.
    mornings: Mornings
    #: The crisis classifier's holders, one per main that has both a tier and a
    #: key (story 6d). Always constructed and possibly empty: a deployment with
    #: neither gets story 6a's offline gate, which is a supported shape rather
    #: than a broken one.
    second: SecondOpinion
    #: Who buys the question (CAP-4, story 11). Constructed here rather than
    #: inside ``serve`` for the reason the scheduler is: *"the favour buys the
    #: question, in the shipped product"* has to be assertable by **value**
    #: rather than by finding a keyword in the source, which is how story 6d's
    #: identical claim passed with the value set to ``None``. Handed to the
    #: ``Runtime`` below and to nothing else — the morning surface has no field
    #: for one.
    questions: QuestionEngine
    #: Who widens correction recognition past the offline table (CAP-11, story
    #: 12). Always constructed and possibly empty: a deployment with no key
    #: recognises explicit corrections offline and proposes none, which is a
    #: supported shape rather than a broken one — the table acts alone and no
    #: model is anywhere on the path that removes a belief.
    corrections: Widening
    #: Who writes the morning's sentence (CAP-8, story 13a). Always constructed
    #: and possibly empty — and here an empty one has a **visible** consequence,
    #: which the other two do not: a main with no generator receives no
    #: unprompted message at all. That is deliberate. Before this story the
    #: morning put ``Context.render()`` on the wire, so an unequipped deployment
    #: sent its own internal serialization; sending nothing is the honest
    #: version of the same state (AD-27), and a template is the one fallback
    #: this product cannot ship worldwide.
    voice: Voice
    #: Who decides whether two entries disagree where neither of them is wrong
    #: (CAP-7, story 9e). Always constructed and possibly empty, and an empty
    #: one is exactly the state story 9d shipped: the comparison bound, the
    #: couple ceiling, the cheap filter and the per-main budget run on every
    #: pass, nobody is consulted, and no tension is minted.
    #:
    #: Held here rather than inside the pass so that the counts have somewhere
    #: to go in the shipped process — a week of judgements that all failed would
    #: otherwise end with nothing anywhere saying so, which looks exactly like a
    #: week in which nobody's life pulled in two directions.
    judges: Judges


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
    # the same queue.
    #
    # **What it runs is the consolidation pass and then the morning surface**
    # (CAP-7, CAP-8). Story 9a shipped the thing that runs a pass before any
    # pass existed and story 9c hung the pass on it; this is the first wiring in
    # which Half can speak first. ``TensionPass`` re-evaluates each main's
    # tensions against the instant the tick read and appends the transitions
    # that follow; ``MorningSurface`` then chooses at most one of them, proves
    # it may be said, and sends it — or, on most mornings, sends nothing, which
    # is the ordinary outcome and not a degraded one (AD-27).
    #
    # **Half speaks here** (story 13a). Until then this path put
    # ``Context.render()`` on the wire — ``content[b_1]: has not walked that
    # plot since March`` — so the last launch blocker that could be closed by
    # building was open in the shipped composition. ``voices`` below equips each
    # main with the port's narrow generator; the surface composes through it
    # after asking the platform and before claiming the day, and says nothing at
    # all when it cannot.
    #
    # Wired **by value**: the surface is handed this wiring's own registry and
    # this wiring's own channel, so that "the morning surface reaches the
    # shipped product" is something a test can assert by identity rather than
    # by finding a keyword's name in the source — which is how story 6d's
    # identical claim passed with the value set to ``None``.
    #
    # The lock lives in ``config.root``, beside the mains rather than inside any
    # one of them: what it excludes is a second drain of this queue, not a
    # second write to one main — that is still the actor's mutex, and the tick
    # goes through it like everything else.
    mornings = Mornings()
    # Who writes the sentence (story 13a). Built before the scheduler because
    # the surface holds it, and wired **by value** for the reason everything
    # else here is: *"Half speaks in the shipped product"* has to be assertable
    # by identity rather than by finding a keyword in the source, which is how
    # story 6d's identical claim passed with the value set to ``None``.
    voice = voices(config, secrets)
    # Who decides whether two entries disagree (story 9e). Built before the
    # scheduler because the pass holds it, and wired **by value** for the reason
    # the composer is: *"a tension is minted in the shipped product"* has to be
    # assertable by identity rather than by finding a keyword in the source.
    #
    # **A bench rather than a judge**, because ``Disagreement.disagree`` carries
    # no ``main_id`` and the key, the provider and the tier are all per main
    # (AD-11, AD-20). ``TensionPass`` asks it for one main's judge once per pass.
    bench = judges(config, secrets)
    scheduler = Scheduler(
        registry=registry,
        mains=tuple(config.mains.values()),
        root=config.root,
        work=MorningPass(
            consolidate=TensionPass(ledger=registry, bench=bench),
            # **The morning surface does not ask** (CAP-4, story 11). It is
            # given no question engine and has no field for one: a question is
            # attached to a conversation that already touches its topic, and a
            # scheduler tick is not a conversation. Delivery is the runtime's,
            # below.
            surface=MorningSurface(
                ledger=registry, channel=channel, mornings=mornings,
                # **The composer reaches the shipped product here and nowhere
                # else.** Without it the surface holds a ``Voice`` with no
                # holders and is silent for everybody — the fail-closed default,
                # and the right one: a Half that cannot compose must not fall
                # back to putting its own scaffolding on the wire.
                voice=voice,
            ),
        ),
    )

    return Wiring(channel=channel, registry=registry, secrets=secrets,
                  sources=sources, scheduler=scheduler, mornings=mornings,
                  second=second_opinion(config, secrets),
                  questions=QuestionEngine(ledger=registry),
                  corrections=widening(config, secrets), voice=voice,
                  judges=bench)


def judges(config: Config, secrets: FileSecretStore) -> Judges:
    """The disagreement judges, for the mains a deployment has equipped (9e).

    Built beside ``second_opinion``, ``widening`` and ``voices`` and on exactly
    their terms — a per-main narrow holder, its own budget, every failure
    leaving that main unequipped and the process running — with three
    differences worth stating.

    **The narrow holder is a ``Classifier``**, the object with no method that
    returns text. Nothing on this path may author a word: a tension is a link
    between two entries, and a sentence written about it would be one no
    correction to either entry could ever take back. ``Judges`` refuses anything
    wider, so this is checked rather than intended.

    **The tier is pinned for everybody**, as it is on the crisis and correction
    paths and unlike the morning voice's. SPEC's constraint is that the nightly
    pass runs on a cheaper tier than conversation *because the free tier depends
    on that gap*, and this pass is the only recurring spend in the product — it
    happens every night whether or not anybody writes, ``JUDGEMENTS`` times per
    main. Following the main's conversation tier here would make the one cost
    the free tier is sized against follow what a deployment pays for
    conversation, which is that gap closed. And there is nothing here for a
    better tier to buy on a main's behalf: a judgement is one label from a closed
    set and nobody reads it.

    **A main is equipped by having a key, not by having been assigned a tier**,
    which is the crisis path's rule for the crisis path's reason one rung over.
    A main with no credential is skipped by the handler below — that is the
    *"skipped rather than defaulted"* this loop still does — and nothing is
    minted for them, which is story 9d's shipped behaviour exactly.

    **Its own provider, and therefore its own ledger.** A provider's spend is
    shared by everything it hands out, so reusing the crisis one would let a
    night of judgements draw down the budget the crisis path runs on.

    **This is the fourth copy of this loop in this file, and it is recorded
    rather than hidden.** ``voices`` above already names the shape —
    ``equipped(config, secrets, *, tier_for, budget, take, unequipped)`` — and
    deferred it on the ground that it belonged beside the consultation
    extraction rather than in front of it. Story 14 did the extraction, so that
    reason has expired and the remaining one is that the loop's fourth member
    arrived in a story whose subject is the judgement, not the composition root,
    and that folding ``second_opinion`` into a shared helper is a behaviour
    change in the crisis path. It stays Ask-First and it now has four callers
    rather than three.
    """
    holders: dict[str, Classifier] = {}
    for main_id in config.mains.values():
        try:
            provider = AnthropicProvider(
                SDKTransport.from_secrets(secrets, main_id),
                tiers=Tiers.parse({main_id: JUDGE_TIER}),
                budget=Budget(
                    per_call_micro_usd=JUDGE_PER_CALL_MICRO_USD,
                    per_pass_micro_usd=JUDGE_PER_PASS_MICRO_USD,
                ),
            )
            holders[main_id] = provider.classifier()
        except Exception as exc:  # noqa: BLE001 - a boot must not die here
            # No key, an unreadable credential file, an unknown tier, a missing
            # SDK. Each is a deployment that has not equipped this main for a
            # nightly judgement, and none is a reason to hold up a Half that
            # still answers everything they say. The class only — a provider's
            # own message can quote what it was sent (AD-22).
            logger.warning(
                "main=%s has no usable model (%s); nothing is minted for them",
                main_id, type(exc).__name__,
            )
    try:
        return Judges(holders)
    except Exception as exc:  # noqa: BLE001 - nor here
        logger.error(
            "the disagreement judge could not be assembled (%s); no tension is "
            "minted for any main", type(exc).__name__,
        )
        return Judges()


def voices(config: Config, secrets: FileSecretStore) -> Voice:
    """The morning composer, for the mains a deployment has equipped (13a).

    Built beside ``second_opinion`` and ``widening`` and on exactly their terms
    — a per-main narrow holder, its own budget, every failure leaving that main
    unequipped and the process running — with three differences worth stating.

    **The narrow holder is a ``Generator``, and it is the widest holder in this
    file.** ``generator()`` hands back an object with one method that returns
    text: no ledger to reset, no batcher to reach, no classifier to borrow.
    ``Voice`` refuses anything wider, so this is checked rather than intended.
    The crisis path takes an object that *cannot* produce text; this one takes
    the object that can, and nothing beyond it.

    **The tier is the main's own** (AD-20), where crisis pins one tier for
    everybody and correction pins the cheap one. Those two are detection
    quality, which CAP-12 forbids gating on payment and which is the same
    question for every main. This is the sentence the main reads, and what a
    deployment pays for a main's conversation is exactly the decision AD-20 puts
    on the main.

    **A main with no tier is refused rather than defaulted**, which is AD-20's
    own rule and has a consequence worth being explicit about: a deployment that
    sets ``HALF_MAINS`` and not ``HALF_MODEL_TIERS`` sends no unprompted
    mornings. A silent fallback tier is either a bill nobody authorised or a
    quality regression nobody sees, and a silent fallback *template* is the
    thing this story exists to refuse.

    **Its own provider, and therefore its own ledger.** A provider's spend is
    shared by everything it hands out, so reusing the crisis one would let a
    morning draw down the budget the crisis path runs on.

    **This is the third copy of this loop in this file, and that is recorded
    rather than hidden.** ``second_opinion``, ``widening`` and this one differ in
    four things: which narrow holder is taken off the provider, which budget
    constants are used, how the tier is chosen, and what the log line says when a
    main cannot be equipped. Everything else — the per-main iteration, the
    construction, the catch that must never fail a boot, the outer catch around
    the holder object itself — is the same twenty lines written out three times.

    A fourth consumer should not write a fourth. The shape is
    ``equipped(config, secrets, *, tier_for, budget, take, unequipped)``, and it
    belongs beside the consultation extraction recorded in
    ``half.voice.gate``'s docstring rather than in front of it: both are the same
    observation about the same three subsystems, and doing one without the other
    would leave a composition root that shares a loop with a crisis path whose
    behaviour must stay byte-identical. Recorded here, and Ask-First for the same
    reason that one is.
    """
    holders: dict[str, Generator] = {}
    for main_id in config.mains.values():
        tier = config.tier_for(main_id)
        if tier is None:
            logger.warning(
                "main=%s has no model tier configured; Half will not send them "
                "an unprompted morning. There is no default tier by design "
                "(AD-20), and no written fallback message by design (AD-27)",
                main_id,
            )
            continue
        try:
            provider = AnthropicProvider(
                SDKTransport.from_secrets(secrets, main_id),
                tiers=Tiers.parse({main_id: tier}),
                budget=Budget(
                    per_call_micro_usd=VOICE_PER_CALL_MICRO_USD,
                    per_pass_micro_usd=VOICE_PER_PASS_MICRO_USD,
                ),
            )
            holders[main_id] = provider.generator()
        except Exception as exc:  # noqa: BLE001 - a boot must not die here
            # No key, an unreadable credential file, an unknown tier, a missing
            # SDK. Each is a deployment that has not equipped this main for an
            # unprompted message, and none is a reason to hold up a Half that
            # still answers everything they say. The class only — a provider's
            # own message can quote what it was sent (AD-22).
            logger.warning(
                "main=%s has no usable model (%s); they receive no unprompted "
                "morning", main_id, type(exc).__name__,
            )
    try:
        return Voice(holders)
    except Exception as exc:  # noqa: BLE001 - nor here
        logger.error(
            "the morning composer could not be assembled (%s); no main "
            "receives an unprompted morning", type(exc).__name__,
        )
        return Voice()


def widening(config: Config, secrets: FileSecretStore) -> Widening:
    """The correction classifier, for the mains a deployment has equipped (12).

    Built beside ``second_opinion`` and on exactly its terms — a per-main narrow
    holder, its own budget, every failure leaving that main unequipped and the
    process running — with two differences worth stating.

    **Its own provider, and therefore its own ledger.** A provider's spend is
    shared by everything it hands out, so reusing the crisis one would let a
    correction consult draw down the budget the crisis path runs on. The two
    subsystems have separate caps because they answer different questions with
    different consequences, and a shared ceiling is one silently spending the
    other's.

    **Unequipped is a much smaller loss here.** A main with no key still has
    every explicit correction recognised, acted on and shown, because the table
    is offline and the model only widens. That is the opposite of the crisis
    path, where the table is the fallback and the model is the reach.
    """
    holders: dict[str, Classifier] = {}
    for main_id in config.mains.values():
        try:
            provider = AnthropicProvider(
                SDKTransport.from_secrets(secrets, main_id),
                tiers=Tiers.parse({main_id: CORRECTION_TIER}),
                budget=Budget(
                    per_call_micro_usd=CORRECTION_PER_CALL_MICRO_USD,
                    per_pass_micro_usd=CORRECTION_PER_PASS_MICRO_USD,
                ),
            )
            holders[main_id] = provider.classifier()
        except Exception as exc:  # noqa: BLE001 - a boot must not die here
            # The class only — a provider's own message can quote what it was
            # sent (AD-22).
            logger.warning(
                "main=%s has no usable model (%s); correction recognition is "
                "the offline table alone for them", main_id, type(exc).__name__,
            )
    try:
        return Widening(holders)
    except Exception as exc:  # noqa: BLE001 - nor here
        logger.error(
            "the correction widening could not be assembled (%s); the table "
            "decides alone for every main", type(exc).__name__,
        )
        return Widening()


def second_opinion(config: Config, secrets: FileSecretStore) -> SecondOpinion:
    """The crisis classifier, for the mains a deployment has equipped (6d).

    **Nothing here can fail the boot** — which is a rule this function broke
    before review round 1 caught it. It caught ``ModelError`` only, and the
    first read of the secret store happens here: a truncated or hand-edited
    ``.credentials/<main>.json`` raises ``StoreError``, which is a ``HalfError``
    and not a ``ModelError``, so one unreadable file took down the channel, the
    gate and the offline safe word for *every* main in the deployment. A crisis
    subsystem that refuses to start is the omission headline arriving at boot
    time, so every failure here leaves that main unequipped and the process
    running.

    A main with no key gets story 6a's behaviour: the phrase table decides
    alone, offline, and the safe word still works with the provider down.

    **Equipped by a key, not by a tier.** Every main is classified on
    ``CLASSIFY_TIER`` whatever they pay, because CAP-12 is never gated by tier
    and making detection quality follow a paid plan is that gate however it is
    spelled. Requiring a ``HALF_MODEL_TIERS`` entry was the same gate wearing
    configuration's clothes.

    **The narrow holder, never the provider.** ``classifier()`` hands back an
    object with one method that returns a label — no generation, no batch, no
    ledger to reset. ``SecondOpinion`` refuses anything wider, so this is
    checked rather than merely intended.

    **One ledger per main**, because a provider's ``Spend`` is shared by
    everything it hands out and a ceiling shared across mains would be one
    main's quiet turn spending another main's.

    The key comes from the ``SecretStore``, which lives beside the store tree
    and never inside it, so it cannot reach an export or a replay (AD-11).
    """
    holders: dict[str, Classifier] = {}
    for main_id in config.mains.values():
        try:
            provider = AnthropicProvider(
                SDKTransport.from_secrets(secrets, main_id),
                tiers=Tiers.parse({main_id: CLASSIFY_TIER}),
                budget=Budget(
                    per_call_micro_usd=PER_CALL_MICRO_USD,
                    per_pass_micro_usd=PER_PASS_MICRO_USD,
                ),
            )
            holders[main_id] = provider.classifier()
        except Exception as exc:  # noqa: BLE001 - a boot must not die here
            # No key, an unreadable credential file, an unknown tier, a missing
            # SDK, a holder the crisis path will not take. Each is a deployment
            # that has not equipped this main, and none of them is a reason to
            # hold up a Half that can still detect a disclosure offline. The
            # class only — a provider's own message can quote what it was sent
            # (AD-22).
            logger.warning(
                "main=%s has no usable model (%s); the crisis phrase table "
                "decides alone for them", main_id, type(exc).__name__,
            )
    try:
        return SecondOpinion(holders)
    except Exception as exc:  # noqa: BLE001 - nor here
        logger.error(
            "the crisis classifier could not be assembled (%s); the phrase "
            "table decides alone for every main", type(exc).__name__,
        )
        return SecondOpinion()


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
                    # The bought question reaches the shipped product here and
                    # nowhere else (CAP-4, story 11). Without it the runtime
                    # never asks — the fail-closed default, and the state story
                    # 5b shipped in, where the gates had no production caller at
                    # all. Wired **by value** for the reason the classifier is.
                    questions=wiring.questions,
                    # Correction recognition reaches the shipped product here
                    # and nowhere else (CAP-11, story 12). Wired **by value**
                    # for the reason the classifier and the question engine
                    # are: a surface reachable only from a test is a surface
                    # nobody has run.
                    corrections=wiring.corrections,
                    # **The turn speaks here** (story 13b). It is the *same*
                    # ``Voice`` the morning surface holds, wired by value, so
                    # there is one composer, one gate, one leak check and one
                    # tally across both surfaces — two of each is two renderings
                    # of one thing, which is how a guard that scans one string
                    # ends up admitting another. Without it the runtime answers
                    # with the claim alone: honest, and never the internal
                    # serialization this story took off the wire.
                    voice=wiring.voice,
                ).run()
            finally:
                # The inbound loop is the process's life; the ticker is not
                # allowed to outlive it. Without this, a receive loop that
                # ended would leave a Half nobody can reach still thinking
                # about people on a schedule.
                ticker.cancel()
    finally:
        # What the mornings did, once, on the way out — counts only (AD-22).
        # Without it a process that ran for a month and never once spoke would
        # end with nothing anywhere saying so.
        wiring.mornings.flush()
        # What the classifier did, once, on the way out — counts only (AD-22).
        # Without it a process that ran for a week with a wholly failing
        # classifier could end without ever reaching a round number.
        wiring.second.flush()
        # And what the correction widening did — counts only (AD-22). A process
        # that ran for a week proposing a candidate on every turn and having
        # none confirmed would otherwise end with nothing anywhere saying so.
        wiring.corrections.flush()
        # And what the composer did — counts only (AD-22). A process that ran
        # for a week composing nothing that passed the judge would otherwise end
        # with nothing anywhere saying so, which looks exactly like a week in
        # which nobody had anything worth hearing.
        wiring.voice.flush()
        # And what the disagreement judge did — counts only (AD-22). A process
        # that ran for a week judging nothing, or judging everything and being
        # refused every time, would otherwise end with nothing anywhere saying
        # so, which looks exactly like a week in which nobody's life pulled in
        # two directions.
        wiring.judges.flush()
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
