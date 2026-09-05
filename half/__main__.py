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

import argparse
import asyncio
import logging
import os
import sys
from dataclasses import dataclass, field

from half.actor.registry import ActorRegistry, validate_main_id
from half.actor.runtime import Runtime
from half.channel.telegram import TelegramChannel
from half.channel.telegram_transport import PTBTransport
from half.config import MAINS_ENV, TELEGRAM_TOKEN_ENV, Config, load
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
from half.derive.claim import (
    CLASSIFY_TIER as DERIVE_TIER,
    PER_CALL_MICRO_USD as DERIVE_PER_CALL_MICRO_USD,
    PER_PASS_MICRO_USD as DERIVE_PER_PASS_MICRO_USD,
    Derivers,
)
from half.derive.particular import GENERATE_TIER as PARTICULAR_TIER
from half.derive.revealed import (
    CLASSIFY_TIER as REVEALED_TIER,
    PER_CALL_MICRO_USD as REVEALED_PER_CALL_MICRO_USD,
    PER_PASS_MICRO_USD as REVEALED_PER_PASS_MICRO_USD,
    Revealed,
    Run,
    consumer_for,
    fields_of,
)
from half.errors import HalfError, ModelError
from half.governance import ladder
from half.ingest.gmail import GmailRecent
from half.ingest.gmail_transport import HttpTransport, MailboxMisconfigured
from half.ingest.pipeline import Ingested, Pipeline
from half.ingest.port import Draining, MailSource
from half.interrupt.gate import Interrupt
from half.onboard import flow as onboarding
from half.onboard.consent import LEAVES_THE_MACHINE, Consent
from half.store.ops import Op
from half.model.anthropic import AnthropicProvider
from half.model.anthropic_transport import SDKTransport
from half.model.budget import Budget
from half.model.port import Classifier, Generator
from half.model.tier import Tiers
from half.questions.engine import QuestionEngine
from half.schedule.clock import SystemClock
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

#: The sentence telling the main their messages leave the machine (CAP-2).
#:
#: **Deployment copy, in the main's own language, and Half ships none.**
#: ``half.onboard.consent`` records the whole argument: a privacy notice
#: written in one language and shown to everybody is a notice most of the world
#: cannot read, which is a notice they were not given. Unset means no mailbox is
#: connected for anybody, which is the fail-closed direction and the only one
#: available — the alternative is reading somebody's mail on the strength of a
#: sentence they never saw.
CONSENT_ENV = "HALF_CONSENT"

#: What Half says when a mailbox yielded no claim (CAP-2's *nothing to offer*).
#:
#: Deployment copy for ``CONSENT_ENV``'s reason, and unset is silence rather
#: than something composed. A generated message on this path would be a
#: pleasantry — a sentence that fills the ninety seconds and says nothing —
#: which the story forbids in as many words, and there is no template this
#: product can ship worldwide to put there instead.
NOTHING_YET_ENV = "HALF_NOTHING_YET"


def notices(env: dict[str, str] | None = None) -> tuple[Consent, str]:
    """The deployment's own two sentences: the notice, and *nothing yet*.

    Read here because this module is the one that reads the environment, and
    returned as values so that ``build`` wires them **by value** — *"a
    deployment with no notice connects no mailbox"* has to be assertable from
    the constructed ``Wiring`` rather than by finding a keyword in this file,
    which is how story 6d's identical claim passed with the value set to
    ``None``.

    Neither is validated for language, length or content, and that is not an
    omission: any check would be a rule about somebody's language written by
    somebody who does not speak it. What is checked is that the notice is
    *there*, and ``half.onboard.consent.Consent`` drops anything that is not a
    sentence with characters in it.
    """
    source = os.environ if env is None else env
    return (
        Consent({LEAVES_THE_MACHINE: source.get(CONSENT_ENV, "")}),
        source.get(NOTHING_YET_ENV, ""),
    )


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
    #: Who decides whether a message was worth keeping (CAP-5, story 15a).
    #: Always constructed and possibly empty, and an empty one is a supported
    #: deployment rather than a degraded one: every message is still recorded,
    #: still read for the language sample and for responsiveness, and still
    #: never a belief. What is lost is claims from the turn path.
    #:
    #: Held here rather than inside the runtime so that the counts have
    #: somewhere to go in the shipped process — a week in which every admission
    #: gate failed would otherwise end with nothing anywhere saying so, which
    #: looks exactly like a week in which nobody said anything worth keeping.
    derivers: Derivers
    #: Who decides what a main's *mail* is worth keeping (CAP-3, story 15b).
    #: Always constructed and possibly empty, and an empty one is exactly the
    #: state story 3 shipped: receipts are captured, no body is persisted, and
    #: the revealed ledger stays empty.
    #:
    #: Holds ``derivers`` above rather than a second copy of 15a's gates, so
    #: *what makes a claim worth keeping* has one definition in this process as
    #: well as one in the tree.
    revealed: Revealed
    #: The rule that governs speaking out of turn (CAP-10, story 5c). Built
    #: with **no urgency source**, and that is the whole of what this story
    #: ships: the mode, the platform, the ceiling, the interruption's own bound
    #: and each wanting's own clock are all exercised on every pass, nobody is
    #: asked whether an option is closing, and **this build never interrupts
    #: anybody**.
    #:
    #: That is deliberate rather than unfinished. Half cannot currently know
    #: that an option is closing — nothing in any record carries a horizon —
    #: and a product that can interrupt before it has a rule for interrupting
    #: is worse than one that cannot interrupt yet. Story 5b shipped a module
    #: with no production caller and waited a story to become real; this does
    #: the same on purpose, because the restraint is the valuable half.
    #:
    #: Held here rather than inside the scheduler for the reason ``voice`` and
    #: ``judges`` are: *"the shipped build wires no urgency source"* has to be
    #: assertable **by value** rather than by finding a keyword in the source,
    #: which is how story 6d's identical claim passed with the value set to
    #: ``None`` for entirely the wrong reason.
    interrupt: Interrupt
    #: What the main is told before a source is connected (CAP-2, story 7).
    #:
    #: Always constructed and possibly empty, and an empty one has a **visible**
    #: consequence: ``half.onboard.flow.demonstrate`` connects no mailbox and
    #: runs no demonstration at all for that deployment. That is the fail-closed
    #: direction and the only one available — Half reads somebody's mail and
    #: hands the bodies to a model provider, and the sentence saying so has to
    #: reach the main before any of it happens, in a language they read. Half
    #: ships no wording for it; see ``CONSENT_ENV``.
    consent: Consent = field(default_factory=Consent)
    #: What Half says when a mailbox yielded nothing to offer. Empty is silence.
    #:
    #: Beside the consent rather than inside it, because it is not consent: it
    #: is the honest answer to *the pull found no label with two independent
    #: groups behind it*, which after a first mailbox pull is the ordinary
    #: outcome. Composing something here instead would be a pleasantry, which
    #: story 7 forbids in as many words.
    nothing_yet: str = ""


def build(config: Config, token: str) -> Wiring:
    """Wire the object graph. Separate from ``main`` so it is testable.

    Three stories have now shipped a surface reachable only from tests, so the
    credential store and the per-main source stores are constructed here even
    though ingestion is not yet scheduled — an object graph nothing builds is
    an object graph nobody has run.
    """
    for main_id in config.mains.values():
        validate_main_id(main_id)

    # What the main is told before a source is connected, and what Half says
    # when a pull found nothing (CAP-2). Both are the deployment's own
    # sentences, in the main's own language, and this package ships neither.
    deployment_notice, nothing_yet = notices()

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

    # Who decides whether a message was worth keeping (CAP-5, 15a), built here
    # because the reader below holds it: the gates that decide whether a *body*
    # is worth a claim are the same four, imported and not restated, so there is
    # one bench in this process and not two.
    gates = derivers(config, secrets)

    # The rule that governs speaking out of turn (CAP-10, story 5c), wired with
    # **no urgency source**. Nothing runs it: it is handed to no scheduler and
    # to no runtime, because an interruption needs a judge and this build has
    # none — so the honest composition is one that holds the rule and never
    # applies it. What is not honest, and what this replaces, is a product with
    # no rule at all, in which the first surface that wants to interrupt
    # invents its own.
    #
    # Built from this wiring's own channel and this wiring's own composer, so
    # an interruption that ever does happen goes out on the same platform door
    # and through the same voice — the gate, the tripwire and the fallback
    # ladder — as the morning and the turn.
    return Wiring(channel=channel, registry=registry, secrets=secrets,
                  sources=sources, scheduler=scheduler, mornings=mornings,
                  second=second_opinion(config, secrets),
                  questions=QuestionEngine(ledger=registry),
                  corrections=widening(config, secrets), voice=voice,
                  judges=bench, derivers=gates,
                  revealed=readers(config, secrets, gates),
                  interrupt=Interrupt(channel=channel, urgency=None,
                                      voice=voice),
                  # **The consent notice reaches the shipped product here and
                  # nowhere else** (CAP-2, story 7), wired by value for the
                  # reason the composer and the classifier are. Without wording
                  # this is an empty ``Consent``, ``half.onboard.consent.told``
                  # answers no, and no mailbox is connected for anybody —
                  # which is the fail-closed direction and is visible in the
                  # value rather than hidden in a branch.
                  consent=deployment_notice, nothing_yet=nothing_yet)


def readers(
    config: Config, secrets: FileSecretStore, gates: Derivers
) -> Revealed:
    """The revealed-ledger readers, for the mains a deployment has equipped
    (CAP-3, story 15b).

    Built beside ``derivers``, ``judges``, ``second_opinion``, ``widening`` and
    ``voices`` and on exactly their terms — a per-main narrow holder, its own
    budget, every failure leaving that main unequipped and the process running —
    with two differences worth stating.

    **It is handed 15a's bench rather than building a second one.** What makes a
    claim worth keeping has one definition in this tree
    (``half.derive.gates``); this path supplies the ledger and the evidence.
    Passing the object rather than constructing another is what makes *"the four
    gates are 15a's"* true by identity in the shipped process, which is a thing
    a test can assert without reading either file.

    **The tier is pinned for everybody**, as it is on the crisis, correction,
    judgement and turn-derivation paths. A mailbox pull is the largest recurring
    spend of the five — it is one reading per body of somebody's archive — so
    SPEC's constraint that the recurring spend runs on a cheaper tier than
    conversation *because the free tier depends on that gap* binds hardest here.
    And there is nothing for a better tier to buy: what comes back is one label
    from a closed set.

    **Its own provider, and therefore its own ledger.** A provider's spend is
    shared by everything it hands out, so reusing the turn deriver's would let a
    mailbox pull draw down the budget a main's own messages are judged on.

    **This is the sixth copy of this loop in this file**, recorded rather than
    hidden for the reason ``judges`` records the fourth and ``derivers`` the
    fifth. The shape ``voices`` named — ``equipped(config, secrets, *,
    tier_for, budget, take, unequipped)`` — is still Ask-First, and this story's
    subject is the independence gate rather than the composition root.
    """
    holders: dict[str, Classifier] = {}
    for main_id in config.mains.values():
        try:
            provider = AnthropicProvider(
                SDKTransport.from_secrets(secrets, main_id),
                tiers=Tiers.parse({main_id: REVEALED_TIER}),
                budget=Budget(
                    per_call_micro_usd=REVEALED_PER_CALL_MICRO_USD,
                    per_pass_micro_usd=REVEALED_PER_PASS_MICRO_USD,
                ),
            )
            holders[main_id] = provider.classifier()
        except Exception as exc:  # noqa: BLE001 - a boot must not die here
            # No key, an unreadable credential file, an unknown tier, a missing
            # SDK. Each is a deployment whose mail is captured as receipts and
            # never read, which is story 3's shipped behaviour exactly. The
            # class only — a provider's own message can quote what it was sent
            # (AD-22).
            logger.warning(
                "main=%s has no usable model (%s); nothing is derived from "
                "their mail", main_id, type(exc).__name__,
            )
    try:
        return Revealed(holders, writers=writers(config, secrets), gates=gates)
    except Exception as exc:  # noqa: BLE001 - nor here
        logger.error(
            "the revealed reader could not be assembled (%s); no claim is "
            "derived from any mailbox", type(exc).__name__,
        )
        return Revealed(gates=gates)


def writers(config: Config, secrets: FileSecretStore) -> dict[str, Generator]:
    """The claim writers, for the mains a deployment has equipped (15c).

    Built beside ``readers`` and on exactly its terms — a per-main narrow
    holder, its own budget, every failure leaving that main unequipped and the
    process running — with three differences worth stating.

    **The narrow holder is a ``Generator``, and it is deliberately a *different
    object* from the classifier ``readers`` builds for the same main.** The
    reading path decides and cannot author; the writing path authors and cannot
    decide. Neither restriction means much alone; it is that no one holder can
    do both that keeps a model out of the admission, and it is checked at the
    bench rather than intended here (``particular.check_writer``).

    **The tier is pinned for everybody**, as the reading tier is and for the
    same sentence in SPEC.md:124 — the recurring spend runs on a cheaper tier
    than conversation *because the free tier depends on that gap*. A mailbox
    pull is the largest recurring spend there is; what makes this affordable at
    all is that a generation happens once per crossed group rather than once per
    body.

    **Its own provider, and therefore its own ledger.** A provider's spend is
    shared by everything it hands out, so reusing the reader's would let one
    long generation draw down the budget every remaining body is read on.

    **This is the seventh copy of this loop in this file**, recorded rather than
    hidden for the reason ``readers`` records the sixth. The shape
    ``voices`` named — ``equipped(config, secrets, *, tier_for, budget, take,
    unequipped)`` — is still Ask-First, and this story's subject is what a claim
    says rather than the composition root.
    """
    holders: dict[str, Generator] = {}
    for main_id in config.mains.values():
        try:
            provider = AnthropicProvider(
                SDKTransport.from_secrets(secrets, main_id),
                tiers=Tiers.parse({main_id: PARTICULAR_TIER}),
                budget=Budget(
                    per_call_micro_usd=REVEALED_PER_CALL_MICRO_USD,
                    per_pass_micro_usd=REVEALED_PER_PASS_MICRO_USD,
                ),
            )
            holders[main_id] = provider.generator()
        except Exception as exc:  # noqa: BLE001 - a boot must not die here
            # No key, an unreadable credential file, an unknown tier, a missing
            # SDK. Each is a deployment whose mail is read and whose candidates
            # are gathered and which admits no claim — receipts still captured,
            # which is story 3's shipped behaviour with one more reason. The
            # class only (AD-22).
            logger.warning(
                "main=%s has no usable model for writing a claim (%s); their "
                "mail is still read and no claim is written from it",
                main_id, type(exc).__name__,
            )
    return holders


async def ingest_mail(
    wiring: Wiring, *, main_id: str, source: MailSource, since: str | None = None
) -> Ingested:
    """Pull one mailbox, and admit what independent sources support (CAP-3).

    **The whole of the story's shipped path, in one function**, and it is here
    because it is composition: the pipeline, the reader, the run and the append
    are four pieces that each belong to a different package, and the only place
    that may hold all four is this one.

    The order is the safety property and it is the pipeline's, not this
    function's: normalise, scrub, hand the ``Scrubbed`` on, write the receipt.
    What this adds is the two ends — a ``Run`` to gather one pull's candidates,
    and the append of whatever ``Run.admitted`` returns.

    **Admission happens after the pull and needs no body**, which is why it can:
    by then every body is out of scope, and what is left is a label from a
    closed set, a message id, a thread id and a content digest. Derivation
    cannot be a later pass; *admission* is not derivation.

    **The claim enters at the weakest rung and cites its sources** (CAP-5,
    AD-28). The rung comes from ``ladder.admitted`` and never from a literal
    here, so there is no spelling of this call that could mint an `assert`; the
    support set names the messages and ``independent`` is what the union-find
    returned.

    **Idempotent on both ends.** The pipeline skips a message whose digest it
    already holds, so a second pull of the same mailbox reads no body twice; and
    a claim already in the ledger is left exactly as it is, which is how
    cross-run accumulation is deferred without a matching rule.

    Never raises for a claim: a failure to append costs the claims and never the
    receipts, which are already durable.

    **A caller that has a deadline bounds the *source*, not this call** (CAP-2,
    story 7). Cancelling here would lose the run with the local and admit
    nothing from a pull whose receipts are already on disk; a source that stops
    yielding lets the ``async for`` end normally, so a truncated pull still
    admits what it gathered and still reports where it read to. See
    ``half.__main__.bounded``.

    **What a truncated pull does *not* return is a moved cursor** (story 20).
    ``Ingested.cursor`` advances only over ground the source finished draining,
    so a cut mid-window leaves it where it was; ``Ingested.read_through`` is
    the pull's own position and is what stamps the claim below.
    """
    with Run() as run:
        # **The scrubbed text's whole lifetime, as a scope** (story 15c). A
        # ``Run`` holds a candidate's scrubbed body so that a claim can be
        # generated over the group it belongs to, and leaving this block
        # releases every one of them — on the exception path as well as this
        # one. *"When the run ends, none of it is still held"* is therefore a
        # property of the indentation rather than of somebody remembering a
        # call, which is the same reason ``Store`` is a context manager.
        pipeline = Pipeline(
            source, wiring.sources[main_id],
            consumer=consumer_for(wiring.revealed, main_id=main_id, into=run),
        )
        result = await pipeline.ingest(since=since)
        claims = run.admitted()

    wiring.revealed.count_claims(claims)
    if not claims:
        return result
    try:
        async with wiring.registry.acquire(main_id) as actor:
            held = actor.store.state().beliefs
            for claim in claims:
                if claim.belief_id in held:
                    # Already admitted by an earlier run. Left alone rather than
                    # restated: adding this run's support to it is cross-run
                    # accumulation, which needs a rule for deciding two derived
                    # claims are the same claim and is deferred.
                    continue
                actor.store.record(
                    # **The pull's own position, not the history cursor.** The
                    # two parted company in story 20: the cursor now moves only
                    # over ground the source finished draining, and a bounded
                    # recent read moves it not at all — while what stamps a
                    # claim is *when the mail it came from was written*, which
                    # is exactly what ``read_through`` reports.
                    Op.ASSERT, claim.belief_id, result.read_through or "",
                    **fields_of(claim),
                    **ladder.admitted(support=list(claim.support)),
                )
    except Exception as exc:  # noqa: BLE001 - the claims, never the receipts
        # The class only, never the exception's own text (AD-22): a store error
        # can quote the record it refused, and a record here names messages.
        logger.error(
            "a revealed claim could not be recorded for main=%s (%s); the "
            "receipts are captured and the run is complete",
            main_id, type(exc).__name__,
        )
    return result



class Bounded:
    """A ``MailSource`` that stops yielding once its deadline has passed.

    **The shape of the ninety-second budget on the pull** (CAP-2, story 7), and
    it is a wrapper rather than a timeout for one reason that matters: a
    cancelled ``ingest_mail`` loses the ``Run`` it was gathering into, so a pull
    stopped part-way would admit nothing from receipts already durable on disk.
    A source that simply stops yielding ends the pipeline's ``async for``
    normally, so the same pull returns a real ``Ingested`` with a real cursor
    and every candidate it managed to gather is admitted.

    The deadline is checked **after** each message is handed over, which is
    after the pipeline has scrubbed it, written its receipt and awaited the
    consumer — so what the check measures is time actually spent, and the
    message in flight is never abandoned half-way through its own receipt.

    Monotonic, from the event loop's own clock: the same reader
    ``half.actor.runtime`` uses for its turn deadline, and not a wall clock.
    Nothing in ``half/`` but ``half/schedule/clock.py`` may read one (AD-30).
    """

    def __init__(self, source: MailSource, *, seconds: float) -> None:
        self.source = source
        self.name = getattr(source, "name", "bounded")
        self._seconds = float(seconds)
        self.stopped_early = False

    async def fetch(self, *, since: str | None = None):
        deadline = asyncio.get_running_loop().time() + self._seconds
        async for message in self.source.fetch(since=since):
            yield message
            if asyncio.get_running_loop().time() >= deadline:
                self.stopped_early = True
                logger.warning(
                    "a mailbox pull stopped at %.0f seconds so the "
                    "demonstration could still be composed inside CAP-2's "
                    "budget; the rest of the mailbox is read on the next pull",
                    self._seconds,
                )
                return


class DrainingBounded(Bounded):
    """``Bounded`` over a source that publishes a watermark, forwarding it.

    **A wrapper must mirror the kind of source it wraps**, and it has to do so
    where a type check can see it. The watermark belongs to the source being
    bounded — it is that source's statement about how far it *finished* — and a
    wrapper that swallowed it would leave the pipeline with no watermark and
    send it back to the ``max()`` cursor story 20 removed, silently.

    Written as a subclass rather than as a ``__getattr__`` on ``Bounded``
    because ``isinstance`` against a runtime-checkable protocol resolves
    attributes **statically** (``inspect.getattr_static``): a ``__getattr__``
    answers a plain attribute lookup and is invisible to the check, so a
    forwarding wrapper written that way passes every direct assertion and is
    not ``Draining`` to the pipeline at all. That is the story's own defect
    wearing the fix's clothes, and it shipped for exactly one review round.
    """

    @property
    def drained_through(self) -> str | None:
        return self.source.drained_through


def bounded(source: MailSource, *, seconds: float) -> Bounded:
    """Bound a pull, mirroring whether its source publishes a watermark."""
    kind = DrainingBounded if isinstance(source, Draining) else Bounded
    return kind(source, seconds=seconds)


async def onboard(
    wiring: Wiring,
    *,
    main_id: str,
    source: MailSource,
    t: str,
    since: str | None = None,
    budget_seconds: float = onboarding.BUDGET_SECONDS,
) -> onboarding.Demonstration:
    """The first run: one source, one claim, offered for confirmation (CAP-2).

    **The onboarding entry point, and it is composition**, which is why it lives
    here beside ``ingest_mail`` rather than inside ``half.onboard``: the notice,
    the channel, the actor registry, the mailbox pull and the composer are five
    pieces belonging to five packages, and this is the only place allowed to
    hold all of them.

    ``source`` is a mailbox **whose token has already been acquired**, which is
    story 3's own deferral (*"the token arrives already acquired"*) and is
    unchanged by this story. What CAP-2 calls *one OAuth* is satisfied here by
    the main having authorised one source and nothing else being asked of them:
    no form, no interview, no second connector, no questionnaire. The
    interactive consent flow that turns a browser redirect into that token is
    deployment infrastructure with its own security surface — a redirect
    handler, a client secret, a verified consent screen — and it is still
    deferred; nothing in this path needs it, because a supplied token exercises
    every step from the mailbox to the statement.

    The source is wrapped so the pull cannot spend the whole budget (see
    ``Bounded``), and the demonstration bounds the whole path a second time as
    a backstop against a fetch that hangs before it ever yields.

    Returns what happened, including the seconds it took and whether that fitted
    — CAP-2's ninety seconds is a requirement, and a caller that never sees the
    number cannot hold anybody to it.
    """
    pull_from = bounded(source, seconds=onboarding.PULL_SECONDS)

    async def pull() -> Ingested:
        return await ingest_mail(
            wiring, main_id=main_id, source=pull_from, since=since,
        )

    return await onboarding.demonstrate(
        main_id=main_id,
        consent=wiring.consent,
        channel=wiring.channel,
        registry=wiring.registry,
        pull=pull,
        # **The demonstration speaks with the same voice as the morning and the
        # turn** — one composer, one gate, one leak check, one tally. Two of
        # each is two renderings of one thing, which is how a guard that scans
        # one string ends up admitting another (story 13b).
        voice=wiring.voice,
        t=t,
        plainly=wiring.nothing_yet,
        budget_seconds=budget_seconds,
    )


async def onboarded(
    wiring: Wiring, *, main_id: str, t: str
) -> onboarding.Demonstration:
    """The demonstration against a **real mailbox**, built from the secret store.

    The one place in the tree that constructs the networked Gmail transport.
    ``onboard`` above takes any ``MailSource``, which is what keeps every case
    above this line offline; this function is the half-line that says *the
    source is Gmail and its token comes from where AD-11 says a token may live*.

    Separated from ``_onboard_command`` so that the path from a stored
    credential to a receipt can be driven end to end against a fake HTTP layer,
    with the platform channel doubled — which is the only way this story's
    integration is assertable without a live key and a live bot.

    A main with no stored token raises ``MailboxMisconfigured`` — a
    ``ChannelError`` and so a ``HalfError`` — **before any request is made**,
    which the command turns into one plain line rather than a traceback.

    **The read is ``GmailRecent`` and not ``GmailSource``, and that is story
    20's second half.** CAP-2 asks what this person has been doing *lately* and
    is cut at ninety seconds; CAP-3 walks the whole of history forward and is
    cut by nothing. Answering the first question with the second one's walk
    reads the oldest mail in the mailbox, and — before this story — moved the
    history cursor to the newest thing the cut happened to reach, which is how
    a bounded demonstration became a permanent loss. ``GmailRecent`` reads the
    newest window and publishes no watermark at all, so the demonstration
    cannot move a cursor it has not earned.
    """
    source = GmailRecent(HttpTransport.from_secrets(wiring.secrets, main_id))
    return await onboard(wiring, main_id=main_id, source=source, t=t)


def derivers(config: Config, secrets: FileSecretStore) -> Derivers:
    """The claim derivers, for the mains a deployment has equipped (CAP-5, 15a).

    Built beside ``judges``, ``second_opinion``, ``widening`` and ``voices`` and
    on exactly their terms — a per-main narrow holder, its own budget, every
    failure leaving that main unequipped and the process running — with two
    differences worth stating.

    **The narrow holder is a ``Classifier``, and here that is the story's own
    guarantee rather than hygiene.** ``classifier()`` hands back an object with
    one method that returns a label from a closed set. An object that could
    *generate* would be a path from a main's message to a sentence Half composed
    about them and wrote into their ledger for ever, arriving through the one
    seam that is supposed to answer yes or no. ``Derivers`` refuses anything
    wider, so this is checked rather than intended.

    **The tier is pinned for everybody**, as it is on the crisis, correction and
    judgement paths and unlike the morning voice's. This runs on every inbound
    message of every main, so it is the second recurring spend in the product
    after the nightly pass, and SPEC's constraint is that the recurring spend
    runs on a cheaper tier than conversation *because the free tier depends on
    that gap*. There is also nothing here for a better tier to buy on a main's
    behalf: four gates, four labels from four closed sets, and nobody reads any
    of them.

    **Its own provider, and therefore its own ledger.** A provider's spend is
    shared by everything it hands out, so reusing the crisis one would let a
    conversation's worth of derivations draw down the budget the crisis path
    runs on.

    **This is the fifth copy of this loop in this file**, and it is recorded
    rather than hidden for the reason ``judges`` records the fourth. The shape
    ``voices`` named — ``equipped(config, secrets, *, tier_for, budget, take,
    unequipped)`` — is still Ask-First, and still for the reason it was: folding
    ``second_opinion`` into it is a behaviour change in the crisis path, and this
    story's subject is the admission gate rather than the composition root.
    """
    holders: dict[str, Classifier] = {}
    for main_id in config.mains.values():
        try:
            provider = AnthropicProvider(
                SDKTransport.from_secrets(secrets, main_id),
                tiers=Tiers.parse({main_id: DERIVE_TIER}),
                budget=Budget(
                    per_call_micro_usd=DERIVE_PER_CALL_MICRO_USD,
                    per_pass_micro_usd=DERIVE_PER_PASS_MICRO_USD,
                ),
            )
            holders[main_id] = provider.classifier()
        except Exception as exc:  # noqa: BLE001 - a boot must not die here
            # No key, an unreadable credential file, an unknown tier, a missing
            # SDK. Each is a deployment that has not equipped this main to have
            # claims derived from what they write, and none is a reason to hold
            # up a Half that still answers everything they say. The class only —
            # a provider's own message can quote what it was sent (AD-22).
            logger.warning(
                "main=%s has no usable model (%s); nothing is derived from "
                "their messages", main_id, type(exc).__name__,
            )
    try:
        return Derivers(holders)
    except Exception as exc:  # noqa: BLE001 - nor here
        logger.error(
            "the claim deriver could not be assembled (%s); no claim is derived "
            "for any main", type(exc).__name__,
        )
        return Derivers()


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
                    # **A message stops being a belief here** (CAP-5, story
                    # 15a). Without it the runtime derives nothing: every
                    # message is still recorded as evidence and still read by
                    # the three subsystems that read it, and no claim is ever
                    # written from the turn path. Wired **by value** for the
                    # reason everything else here is — a surface reachable only
                    # from a test is a surface nobody has run.
                    derivers=wiring.derivers,
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
        # And what the deriver did — counts only (AD-22). A process that ran for
        # a week deriving nothing would otherwise end with nothing anywhere
        # saying so, which looks exactly like a week in which nobody wrote
        # anything worth keeping.
        wiring.derivers.flush()
        # And what the mailbox reader did — counts only (AD-22). A process that
        # pulled an archive and admitted nothing from it would otherwise end
        # with nothing anywhere saying so, which looks exactly like a mailbox
        # with nothing in it — and is far more likely to be a hundred candidates
        # that never found a second independent group.
        wiring.revealed.flush()
        wiring.registry.close()


def arguments(argv: list[str] | None = None) -> argparse.Namespace:
    """The command line: ``half``, ``half run``, ``half onboard <main>``.

    **``onboard`` asks for nothing but the token** (CAP-4). There is no form and
    no interview: the main answers no questions, and the operator names which
    configured main to onboard because a composition root serving several must
    be told which one. The interactive OAuth consent flow that would turn a
    browser redirect into a credential is still deferred — story 3 deferred it
    and story 7 declined it — so the token is supplied out of band into the
    ``SecretStore`` and this command reads it from there.

    A bare ``half`` still serves, which is what every existing deployment and
    the console script in ``pyproject.toml`` invoke.
    """
    parser = argparse.ArgumentParser(
        prog="half", description="A second self that lives in your messaging app."
    )
    commands = parser.add_subparsers(dest="command")
    commands.add_parser(
        "run", help="serve the inbound loop and the due-time queue (the default)"
    )
    first = commands.add_parser(
        "onboard", help="run the first demonstration against a real mailbox"
    )
    first.add_argument(
        "main_id", help="which main in HALF_MAINS to onboard"
    )
    return parser.parse_args(argv)


def onboard_command(config: Config, token: str, main_id: str) -> int:
    """``half onboard`` — story 7's flow, against a real mailbox, reported.

    **It reports the outcome and never the words.** ``Demonstration.text`` is
    what was said to the main; printing it here would put a main's own content
    on an operator's terminal, and the reason, the seconds and whether they
    fitted are what CAP-2 asks anybody to hold this to (AD-22).

    An outcome that is not ``DEMONSTRATED`` is still a **successful run** and
    exits zero: *nothing cleared the gates* and *the deployment wrote no
    notice* are answers this path is designed to produce, and turning one into
    a non-zero exit would invent an outcome story 7 does not have. What exits
    non-zero is a refusal to start at all — no such main, no stored token —
    which ``main`` prints as one line.
    """
    if main_id not in config.mains.values():
        raise HalfError(
            f"{main_id!r} is not a main in {MAINS_ENV}; "
            f"configured: {sorted(config.mains.values())}"
        )
    wiring = build(config, token)
    try:
        done = asyncio.run(
            onboarded(
                wiring,
                main_id=main_id,
                # The one clock reader in the tree (AD-30). Nothing below this
                # line asks what time it is.
                t=SystemClock().read().stamp,
            )
        )
    except MailboxMisconfigured as exc:
        # Re-raised rather than handled, and with exactly one fact added. The
        # transport cannot know where a ``SecretStore`` keeps its files —
        # ``SecretStore`` is a Protocol and a hosted deployment's is not a
        # directory at all — and this is the layer that can. A refusal that
        # names the credential but not the place to put it leaves a
        # self-hoster's first command a dead end, and *says so plainly* is a
        # row of this story's matrix. The token itself is never in ``exc``.
        raise HalfError(f"{exc}, which lives in {wiring.secrets.root}") from None
    finally:
        wiring.registry.close()
    over = "" if done.fitted else " (over CAP-2's ninety seconds)"
    print(f"half: onboarded {main_id}: {done.reason} in {done.seconds:.1f}s{over}")
    return 0


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(
        level=os.environ.get("HALF_LOG_LEVEL", "INFO"),
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    args = arguments(argv)
    try:
        config = load()
        if not config.mains:
            raise HalfError(
                "no mains configured; set HALF_MAINS='<chat_id>:<main_id>'"
            )
        token = os.environ.get(TELEGRAM_TOKEN_ENV, "")
        if args.command == "onboard":
            return onboard_command(config, token, args.main_id)
        asyncio.run(serve(config, token))
    except HalfError as exc:
        # One line, never a traceback: a missing credential is an operator's
        # ordinary Tuesday, and the class of every failure on this path is
        # already a sentence somebody can act on.
        print(f"half: {exc}", file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        return 0
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
