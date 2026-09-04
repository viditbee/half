"""The demonstration: connect, ingest, derive, offer one, route the answer.

CAP-2 asks for one OAuth, no forms, and one true, specific, falsifiable
statement about the main inside ninety seconds. Every piece of that existed
before this module — ingestion (story 3), the four admission gates (15a), the
revealed derivation and its independence rule (15b), the ladder (5a), story
12's correction door, and the composer (13a/13b) — and none of them was joined
to the next. There was no first run.

**The conflict this resolves, and why it is not an exception to the ladder.** A
derived claim is born `behave`; only `assert` is quotable; and `assert` needs a
receipt **and** ``known_to_main``, which is written only by a promotion the main
took part in. So on day one Half can state nothing it derived. CAP-2 answers
that in its own success criterion — *"the statement is confirmed as true"* —
and that confirmation **is** the ladder's acknowledgement event. The
demonstration is therefore **offered for confirmation, not asserted**: the
claim is `behave` when the message goes out, it is `behave` while the main
reads it, and the main's own answer is the only thing that moves it. That is
the ladder working exactly as story 5a wrote it, not a hole in it.

**What is an exception, and it is the sharp part.** To confirm a claim the main
must see its words, and a `behave` claim's words may not enter a constructed
context (AD-18). So this story opens the **second** bounded exception, in
``half.context.build``: ``split`` takes an ``offered`` belief id, that one claim
enters the content channel whatever rung it is on, and its wording leaves the
withheld set for that build alone. ``build`` — the door every other surface
uses — has no such parameter, so the bound is a fact about a signature rather
than a branch anybody has to keep true. The first exception (story 12's
correction reply) shipped with its negative half tested against a runtime that
had no classifier wired, which removed the very route the assertion claimed to
bound; 13b's review found it. So the negative here is asserted with this module
constructed, a demonstration already sent and an offer standing.

**Two things this module cannot do, by construction.** It never promotes and it
never corrects. ``confirmed`` returns the fields
``half.governance.ladder.promote`` produced and ``denied`` returns the
``Removal`` ``half.correction.apply.plan`` produced; the append is
``answered``'s, under the actor's own mutex, in the shape
``half.actor.runtime`` already appends a correction. There is no second rung
mover and no second correction path in this tree.

**Exactly one claim, never a list.** A digest of everything Half worked out is
a form, and CAP-4 forbids forms. ``chosen`` picks one, deterministically, and
``Demonstration.offer`` is singular by type.

**Falsifiability is 15a's answer and is not re-decided here.** Every claim this
module can offer came out of ``half.derive.revealed.Run.admitted``, which
admits nothing that did not pass all four gates — decision-relevance,
durability, independence, falsifiability — and nothing supported by fewer than
two independent groups. There is no path in this file that constructs a claim,
which is what makes *"no unfalsifiable claim is offered"* a property of where
the material comes from rather than a check somebody wrote twice.

**Ninety seconds is a budget and it is spent, not assumed.** ``BUDGET_SECONDS``
is CAP-2's number; ``COMPOSE_SECONDS`` is reserved out of it so the pull can
never eat the whole thing and leave nothing to say; the pull runs under a real
deadline and is cut when it passes. What that buys, and what it costs, is
``messages_that_fit`` — and the number is small, because there is no batch seam
anywhere between a mailbox and a claim. See that function; the gap is recorded
rather than papered over.

**Nothing generated is durable** (AD-22). The composed text is returned to the
caller and sent; no log line here takes a claim, a body, a notice or a
completion as an argument, and ``Demonstration`` carries the text for the
caller to send rather than for anything to store.

**A main in crisis is not demonstrated to** (AD-10, CAP-12). The mode is asked
about before the notice is sent and before a mailbox is touched, so a main in
the mode is not told about mail, not read, and not spoken to from here at all.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass
from enum import StrEnum
from typing import Any, Final

from half.context.build import split
from half.correction import apply as correction
from half.correction.apply import Removal, Source
from half.correction.signals import Meaning, is_confirmation, is_decline, recognize
from half.derive.claim import BOUND_SECONDS as GATE_BOUND
from half.derive.revealed import BOUND_SECONDS as READ_BOUND, REVEALED
from half.errors import OnboardError
from half.model.consult import a_bound
from half.governance import ladder
from half.governance.ladder import License
from half.onboard import consent as consenting
from half.onboard.consent import Consent
from half.retrieval.port import Candidate, Ranked
from half.store.ops import Op
from half.store.records import CLAIM, LEDGER, derived_claim
from half.voice.compose import Sample
from half.voice.gate import BOUND_SECONDS as COMPOSE_SECONDS
from half.voice.turn import words

#: Structured, and content-free. Every value logged from this module is a
#: ``main_id``, a ``Reason``, a count or a number of seconds — never a claim,
#: never a body, never the notice, never a word of what was composed (AD-22).
logger = logging.getLogger(__name__)


# ── the budget ───────────────────────────────────────────────────────────────

#: CAP-2's ninety seconds, from the OAuth to the first statement.
#:
#: **A budget that is spent rather than an aspiration.** SPEC records it as a
#: hard product requirement, so it is enforced as a deadline on the pull and
#: reported as a measurement on the way out (``Demonstration.seconds``,
#: ``Demonstration.fitted``) — not asserted about a run nobody timed.
BUDGET_SECONDS: Final[float] = 90.0

#: How much of the budget is reserved for composing the message.
#:
#: ``half.voice.gate.BOUND_SECONDS``, imported rather than chosen: the
#: demonstration is unprompted in the sense that matters here — nobody is
#: holding a webhook open inside AD-23's five seconds — so it is the morning's
#: bound and not the turn's, and it is *the same number*, so a change there
#: moves this with it.
#:
#: Reserved out of the budget rather than added to it. A pull allowed to spend
#: the whole ninety seconds leaves a main who waited the full budget with
#: nothing said, which is the worst of the available outcomes: the cost was
#: paid and the demonstration did not happen.
PULL_SECONDS: Final[float] = BUDGET_SECONDS - COMPOSE_SECONDS


def messages_that_fit(budget_seconds: float = BUDGET_SECONDS) -> int:
    """How many messages a mailbox pull can read inside the budget, worst case.

    **The gap, computed from the shipped constants rather than guessed.** One
    body costs two bounded consultations in series: 15a's four admission gates,
    which run concurrently under one ``half.derive.claim.BOUND_SECONDS``, and
    then 15b's *what does this show they do* under
    ``half.derive.revealed.BOUND_SECONDS``. Bodies themselves are read in
    series — ``half.ingest.pipeline.Pipeline.ingest`` awaits its consumer
    inside the ``async for``, and neither derivation story has a batch seam —
    so the worst case is that product, and this is the arithmetic.

    **The number is small and that is the finding, not a rounding error.** With
    the shipped bounds it is a handful of messages, while
    ``half.derive.revealed.PER_RUN`` allows two hundred: the ninety seconds
    binds long before the per-run cap does, and a first mailbox pull that has to
    find *two independent groups behind one label* inside a handful of messages
    will very often find nothing. The honest outcomes are the ones this module
    ships — measure it, cut the pull at the deadline, and say plainly that
    there is nothing yet — and the fix is a batch seam, which is a story about
    ``half.model`` and not a number that can be tuned here.

    Worst case, deliberately: the bounds are ceilings, so a healthy provider
    fits many times this. A budget that assumed the healthy case would be an
    assumption again.
    """
    per_message = GATE_BOUND + READ_BOUND
    for_the_pull = float(budget_seconds) - COMPOSE_SECONDS
    if for_the_pull <= 0 or per_message <= 0:
        return 0
    return int(for_the_pull // per_message)


# ── what a demonstration comes to ────────────────────────────────────────────


class Reason(StrEnum):
    """Why a demonstration said what it said. **Required** (AD-32).

    Silence is a typed outcome with a reason on this path as on every other,
    and the reasons are kept apart because they are different products: a main
    in crisis, a deployment with no composer, a mailbox with nothing
    independent in it and a budget that ran out all produce no statement, and a
    tally that could not tell them apart would report a working product and a
    broken one identically.
    """

    #: One claim was offered for confirmation. The only outcome with an offer.
    DEMONSTRATED = "demonstrated"
    #: The deployment has no wording for the notice, so nothing was connected.
    NOT_TOLD = "not-told"
    #: The crisis mode is open. The crisis path owns the turn (AD-10, CAP-12).
    IN_CRISIS = "in-crisis"
    #: The platform will not carry an unprompted message to this main (AD-7).
    UNREACHABLE = "unreachable"
    #: The notice was composed and the platform did not carry it, so no source
    #: was connected: attempted is not told.
    NOTICE_NOT_SENT = "notice-not-sent"
    #: No composer is equipped for this main. Nothing is said (AD-27).
    NO_VOICE = "no-voice"
    #: Nothing cleared the four gates and the independence rule.
    NO_CLAIM = "no-claim"
    #: The budget was gone before anything could be composed.
    OUT_OF_TIME = "out-of-time"
    #: The composer produced nothing that survived the judge, the tripwire and
    #: the requirement that the claim appear verbatim.
    NOT_COMPOSED = "not-composed"
    #: The message was composed and the platform did not carry it.
    NOT_SENT = "not-sent"


@dataclass(frozen=True, slots=True)
class Offer:
    """One derived claim, put to the main for confirmation. **Not a promotion.**

    Two strings and nothing else: the belief the offer is about, and the claim
    as the record holds it. No license, no rung, no timestamp, no *confirmed*
    flag — an offer that could carry its own answer is an offer somebody can
    answer without the main.

    Held in memory between the demonstration and the reply, the way story 12
    holds a standing candidate. Nothing durable is written for it, because
    nothing has happened yet: an offer the main never answers leaves the ledger
    exactly as the mailbox pull left it, and *silence is not consent*.
    """

    belief_id: str
    claim: str

    def __post_init__(self) -> None:
        if not isinstance(self.belief_id, str) or not self.belief_id.strip():
            raise OnboardError(
                "an offer must name the belief it is about; without an id "
                "there is nothing the main's answer could promote"
            )
        if not isinstance(self.claim, str) or not self.claim.strip():
            raise OnboardError(
                "an offer must carry the claim's own words. The whole of CAP-2 "
                "is that the main can check the statement, and words they were "
                "never shown are words they cannot check"
            )


@dataclass(frozen=True, slots=True)
class Demonstration:
    """What one run of the demonstration produced.

    ``text`` is what goes on the wire and empty is silence (AD-27). ``offer`` is
    non-``None`` only for ``Reason.DEMONSTRATED``, which is asserted at
    construction: an outcome carrying an offer nobody was shown would leave a
    standing offer that a later *yes* could promote.

    ``seconds`` is what the path actually cost, measured on the loop's own
    monotonic clock, and ``fitted`` is whether it came in under the budget.
    Both travel because CAP-2's ninety seconds is a requirement rather than a
    hope, and a number nobody carries out of the function is a number nobody
    can assert about.
    """

    reason: Reason
    text: str = ""
    offer: Offer | None = None
    seconds: float = 0.0
    fitted: bool = True

    def __post_init__(self) -> None:
        if self.offer is not None and self.reason is not Reason.DEMONSTRATED:
            raise OnboardError(
                f"a {self.reason} outcome carries an offer. Only a "
                "demonstration the main was actually shown may leave one "
                "standing, or a later 'yes' promotes something nobody saw"
            )
        if self.offer is None and self.reason is Reason.DEMONSTRATED:
            raise OnboardError(
                "a demonstration with no offer promotes nothing whatever the "
                "main answers, which is CAP-2's own criterion deleted"
            )


class Answer(StrEnum):
    """What the main's reply to an offer says. Three values, and the third is
    not a decline.

    *Nothing* is its own value rather than being folded into ``DENIED``,
    because the matrix keeps them apart and the two do opposite things: a
    denial appends a correction, and silence appends nothing at all. Silence is
    not consent and it is not refusal either.
    """

    CONFIRMED = "confirmed"
    DENIED = "denied"
    NONE = "none"


@dataclass(frozen=True, slots=True)
class Outcome:
    """What routing one answer did. A value; the append is the caller's frame.

    ``promoted`` is the fields ``half.governance.ladder.promote`` returned, or
    ``None``. ``removal`` is what ``half.correction.apply.plan`` planned, or
    ``None``. At most one of the two is ever set — a reply cannot be both a
    confirmation and a correction — and both may be ``None`` for an answer that
    named a belief that is no longer there.
    """

    answer: Answer
    promoted: Mapping[str, Any] | None = None
    removal: Removal | None = None

    def __post_init__(self) -> None:
        if self.promoted is not None and self.removal is not None:
            raise OnboardError(
                "one reply produced both a promotion and a correction. A main "
                "who confirmed a claim did not also deny it, and a build that "
                "can do both has two rung movers"
            )


# ── choosing the one claim ───────────────────────────────────────────────────


def offerable(belief: Mapping[str, Any] | Any) -> bool:
    """Whether this belief record is a claim the demonstration may offer.

    Four conditions, and every one of them is a rule some other story owns:

    * it is a **derived claim** rather than a message — 15a's mark, read
      through ``half.store.records.derived_claim`` rather than by comparing a
      string here;
    * it belongs to the **revealed** ledger, so what is offered is something
      the main's own sources showed rather than something they told Half;
    * it carries **claim text**, because an offer with no words is an offer
      nobody can check;
    * and it has **not already been confirmed** — ``known_to_main`` on the
      belief means the main has already answered about it, so offering it again
      is Half asking a question it has the answer to.

    Nothing here decides falsifiability, durability, relevance or independence.
    Those are 15a's four gates and 15b's union-find, applied before this record
    existed, and re-deciding any of them here would be a second opinion about a
    rule that already has one.
    """
    if not isinstance(belief, Mapping):
        return False
    if not derived_claim(belief):
        return False
    if belief.get(LEDGER) != REVEALED:
        return False
    claim = belief.get(CLAIM)
    if not isinstance(claim, str) or not claim.strip():
        return False
    return not ladder.known_to_main(belief)


def chosen(beliefs: Mapping[str, Any] | None) -> Offer | None:
    """The one claim to offer, or ``None``. Pure, deterministic.

    **Exactly one, because a list is a form** (CAP-4). Several claims routinely
    qualify after a mailbox pull, and a message carrying all of them is a
    digest — which reads as a report about the main rather than as one thing
    said to them, and is the questionnaire CAP-4 forbids arriving from the
    other direction.

    **Best corroborated first, then by belief id.** The independence count is
    the union-find's answer (15b), so *more independent groups behind it* is the
    one ordering available that is a fact about the evidence rather than a
    judgement about the words — and it is the same ordering in every script,
    because it is arithmetic. The id breaks ties, so two equally supported
    claims produce the same choice on every run and on every replay (AD-30).
    There is no ranking, no salience, no recency and no locale anywhere in it.

    ``None`` is the ordinary answer for a first pull and is not an error: most
    mailboxes yield no label with two independent groups behind it. It is the
    matrix's *nothing to offer* row, and what the caller does with it is say so
    plainly rather than substitute a pleasantry.
    """
    if not isinstance(beliefs, Mapping):
        return None
    best: tuple[int, str] | None = None
    found: Offer | None = None
    for ident, belief in beliefs.items():
        if not isinstance(ident, str) or not offerable(belief):
            continue
        count = belief.get("independent")
        rank = count if isinstance(count, int) and not isinstance(count, bool) else 0
        key = (-rank, ident)
        if best is None or key < best:
            best = key
            found = Offer(belief_id=ident, claim=str(belief[CLAIM]))
    return found


# ── the demonstration ────────────────────────────────────────────────────────


async def demonstrate(
    *,
    main_id: str,
    consent: Consent | None,
    channel: Any,
    registry: Any,
    pull: Callable[[], Awaitable[Any]] | None,
    voice: Any,
    t: str,
    plainly: str = "",
    budget_seconds: float = BUDGET_SECONDS,
) -> Demonstration:
    """One OAuth, one mailbox, one claim offered for confirmation (CAP-2).

    The order is the story and every step of it is a rule:

    1. **The crisis mode first** (AD-10, CAP-12). A main in the mode is not
       demonstrated to at all — not told about mail, not read, not spoken to
       from here. Asked before anything else so that no part of this path runs
       for them.
    2. **The notice, before a source is connected** (CAP-2's launch blocker).
       ``half.onboard.consent`` answers whether there is a notice to give; with
       no wording nothing is connected, and the notice is its own message, sent
       and *confirmed delivered* before ``pull`` is called. A footer under the
       demonstration is the thing this step exists to refuse.
    3. **The mailbox, under the budget's own deadline.** ``pull`` is whatever
       the composition root wired — in the shipped product,
       ``half.__main__.ingest_mail``, which is the one path in the tree from a
       body to a revealed claim. Past ``PULL_SECONDS`` it is cut: the receipts
       already written stay written, the candidates already gathered stay
       gathered, and what admission needs is a label, a message id, a thread id
       and a digest, none of which is a body.
    4. **One claim, chosen from the fold.** Read back through the actor rather
       than out of the pull's own return, so a claim admitted by an *earlier*
       run counts and a re-run offers nothing twice.
    5. **Composed, with the second AD-18 exception**, and sent only if the
       composer's own prose survived. There is deliberately no fallback to the
       bare claim here: ``half.voice.turn.fallback`` would put a `behave`
       claim on the wire unframed, which reads as a statement Half has made
       rather than one it is asking about — so a failed generation is silence
       (``Reason.NOT_COMPOSED``) and the claim stays in the ledger for a later
       run. That is the exception bounded a second way: the wording reaches the
       wire only inside prose that was judged, and never on its own.

    **Never raises for anything a deployment can be in.** No consent, no
    composer, no mail source, a mailbox with nothing in it, a provider that is
    down, a platform that will not carry an unprompted message: each is a
    ``Reason`` and none is fatal. What does raise is a build mistake — a budget
    that is not a budget — because that is a deployment nobody would want to
    keep running.

    ``t`` is the injected instant this build stamps records with; nothing here
    reads a clock. The *duration* is taken from the event loop's own monotonic
    time, which is the same reader ``half.actor.runtime`` uses for its turn
    deadline and is not a wall clock.
    """
    if not a_bound(budget_seconds):
        # ``half.model.consult.a_bound``: positive, a number, not a bool, and
        # **finite**. Infinity and NaN are refused there for the reason they are
        # refused here — a deadline that never fires is not a bound, it is a
        # guard that reports success, and this one sits in front of a person
        # who has just connected their mail and is waiting.
        raise OnboardError(
            f"a budget of {budget_seconds!r} demonstrates nothing to anybody, "
            "for ever, and nothing would say so. CAP-2's number is "
            f"{BUDGET_SECONDS}"
        )
    started = asyncio.get_running_loop().time()

    def spent() -> float:
        return asyncio.get_running_loop().time() - started

    def done(reason: Reason, *, text: str = "", offer: Offer | None = None):
        elapsed = spent()
        return Demonstration(
            reason=reason, text=text, offer=offer,
            seconds=elapsed, fitted=elapsed <= budget_seconds,
        )

    # 1 — the mode owns the inbound path, and it owns this one (AD-10).
    if _in_crisis(registry, main_id):
        logger.info(
            "main=%s is in the crisis mode; no demonstration runs and no "
            "source is connected", main_id,
        )
        return done(Reason.IN_CRISIS)

    # 2 — told, plainly, before anything is connected.
    told = consenting.notice(consent)
    if not told:
        logger.warning(
            "main=%s has no consent notice, so no source is connected. The "
            "sentence that says their messages leave the machine is written by "
            "the deployment, in their own language, and Half ships none",
            main_id,
        )
        return done(Reason.NOT_TOLD)
    if not _reachable(channel, main_id):
        return done(Reason.UNREACHABLE)
    if not await _delivered(channel, main_id, told):
        # Attempted is not told. A notice the platform did not carry leaves the
        # main knowing nothing, so nothing is connected on the strength of it.
        return done(Reason.NOTICE_NOT_SENT)

    # 3 — the mailbox, cut at the deadline rather than allowed to eat the whole
    #     budget. A truncated pull keeps every receipt already written.
    if pull is not None:
        await _pulled(pull, main_id=main_id, seconds=PULL_SECONDS)

    # 4 — one claim, from the fold.
    beliefs = await _beliefs(registry, main_id)
    offer = chosen(beliefs)
    if offer is None:
        # *Nothing to offer.* Half says so with whatever the deployment wrote,
        # in the main's own language, and substitutes nothing of its own: a
        # composed pleasantry here would be Half filling ninety seconds with a
        # sentence that says nothing, which is the one thing worse than saying
        # nothing at all.
        if plainly:
            await _delivered(channel, main_id, plainly)
        return done(Reason.NO_CLAIM, text=plainly)

    # 5 — the words, and the exception that lets them be said.
    if not _has_voice(voice, main_id):
        return done(Reason.NO_VOICE)
    left = budget_seconds - spent()
    bound = min(left, COMPOSE_SECONDS)
    if bound <= 0:
        logger.warning(
            "the demonstration for main=%s spent its whole budget reading "
            "mail; the claim is in the ledger and nothing was said", main_id,
        )
        return done(Reason.OUT_OF_TIME)

    # **The belief record itself**, not a value rebuilt from the offer. What
    # ``resolve`` reads has to be the rung the log actually holds and the
    # ceiling this main actually carries — so the case that says *this claim is
    # `behave` and is quoted only because it was offered* is asserting about
    # the real record, and a claim that had somehow reached `assert` would take
    # the ordinary door and need no exception at all.
    context, hidden = split(
        Ranked(beliefs=(
            Candidate(
                # No prefix and no ``bm25``: nothing was retrieved. The
                # demonstration's ranked set is one belief chosen from the
                # fold, so there is no query behind it and no score to carry —
                # ``None`` is what the backstop already means by *this
                # candidate did not come from a term match*.
                id=offer.belief_id, claim=offer.claim, prefix="", bm25=None,
                belief=beliefs[offer.belief_id],
            ),
        )),
        now=t,
        ceiling=_ceiling(registry, main_id),
        offered=offer.belief_id,
    )
    turned = await words(
        voice, context, main_id=main_id,
        # The notice is the language sample, and it is the only text Half has
        # of this main's before they have written anything. The deployment
        # wrote it in their language, so the first thing Half composes is in
        # that language and not in one language for everybody.
        sample=Sample(told),
        withheld=hidden,
        show=offer.claim,
        bound_seconds=bound,
    )
    if not turned.composed:
        # **No fallback to the bare claim.** See this function's own docstring:
        # the unframed claim is a statement, and the demonstration is an offer.
        logger.info(
            "nothing was composed for main=%s's demonstration; the claim stays "
            "in the ledger and nothing is said", main_id,
        )
        return done(Reason.NOT_COMPOSED)
    if not await _delivered(channel, main_id, turned.text):
        # Nothing landed, so no offer stands: a *yes* on a later turn must not
        # promote a claim the main was never shown.
        return done(Reason.NOT_SENT)
    return done(Reason.DEMONSTRATED, text=turned.text, offer=offer)


# ── routing the answer ───────────────────────────────────────────────────────


def reading(text: object) -> Answer:
    """What the main's reply to a standing offer says. Pure, offline.

    **Story 12's own vocabulary, and no second recogniser.** A confirmation is
    ``half.correction.signals.is_confirmation`` — whole-message, narrow, and
    already the answer to *"shall I?"* everywhere else in this tree. A denial is
    either an explicit correction that module's tables recognise, or a
    whole-message decline. Everything else is ``NONE``.

    **Why a decline table exists here and not for a candidate.** Story 12 has
    deliberately no negative table, because for a *proposal to delete something*
    anything that is not a clear yes is a decline and doing nothing is the safe
    direction. Here the safe direction is the opposite one: Half has just made
    a statement about somebody and asked them to check it, and reading their
    *"no"* as *"said nothing"* would lose the single correction a main is most
    likely to ever make — on the first thing Half said to them. So the decline
    is recognised rather than defaulted to, whole-message, in the same shape
    and for the same reason as the confirmation.

    ``NONE`` for silence, for a blank message, and for a reply that is neither
    — which is correct rather than a gap: a main who answers the demonstration
    with something else has not confirmed it, and Half inventing a reading of
    that is how a claim gets promoted on a *maybe*.
    """
    if is_confirmation(text):
        return Answer.CONFIRMED
    if recognize(text) is not None or is_decline(text):
        return Answer.DENIED
    return Answer.NONE


#: Which meaning a denial that names no cause carries.
#:
#: *Not yet known* (story 12): the main said the statement is wrong and said
#: nothing about whether Half was wrong or they have changed, and only they know
#: which. A default in either direction writes a falsehood into the one ledger
#: whose purpose is to be honest.
_UNSTATED: Final[Meaning] = Meaning.WRONG


def meaning_of(text: object) -> Meaning:
    """What a denial means, for story 12's own door.

    ``recognize``'s answer where the reply says which — *"that was never true"*
    and *"not any more"* are different facts and the record keeps them apart —
    and *wrong, cause unknown* where it does not.

    **An erasure is deliberately not one of the answers.** ``recognize`` can
    return ``Meaning.ERASE`` for a reply like *"delete that"*, and story 12
    requires an erasure to be confirmed before it is applied because it is the
    one removal that cannot be taken back. Answering a demonstration is not that
    confirmation, so an erasure asked for here becomes an ordinary removal and
    the main asks for the erasure again on an ordinary turn, where story 12's
    own asking step is intact. Nothing is lost: the belief still leaves the
    fold on this reply.
    """
    meaning = recognize(text)
    if meaning is None or meaning is Meaning.ERASE:
        return _UNSTATED
    return meaning


async def answered(
    offer: Offer | None,
    text: object,
    *,
    main_id: str,
    registry: Any,
    t: str,
) -> Outcome:
    """Route the main's reply through the ladder's door or story 12's.

    Three outcomes and no fourth:

    * **Confirmed** — ``half.governance.ladder.promote(belief, to='assert',
      acknowledged=True)``, appended under the belief's own id. That call is
      what writes ``known_to_main``, and it refuses without the
      acknowledgement, without a receipt, and for a quarantined belief. The
      demonstration's own claim carries the support set 15b cited, so the
      receipt precondition is already met; the acknowledgement is the main's
      answer and arrives nowhere else.
    * **Denied** — ``half.correction.apply.plan`` and the append
      ``half.actor.runtime`` already makes for a correction. **Never a local
      discard.** A discard would silently lose the correction a main is most
      likely to make, on the first thing Half ever said to them, and leave a
      claim they have explicitly denied sitting in the fold shaping every
      context it enters.
    * **Nothing** — nothing appended, nothing promoted, nothing removed. Silence
      is not consent.

    **Idempotent, and it has to be.** A belief already at `assert` has already
    been confirmed: ``promote`` would refuse it as *not a promotion*, so it is
    checked first and answered as a no-op rather than by catching the refusal —
    a second run of onboarding, or the same *yes* delivered twice, moves
    nothing and appends nothing.

    ``None`` for the offer, and a reply about a belief that has since left the
    fold, both answer with the reading and no append: there is nothing to
    promote and nothing to remove, and the main is not shown an error for it.
    """
    answer = reading(text)
    if offer is None or answer is Answer.NONE:
        return Outcome(answer=answer)

    async with registry.acquire(main_id) as actor:
        held = actor.store.state().beliefs.get(offer.belief_id)
        if not isinstance(held, Mapping):
            # Already corrected, already erased, or never written. No second
            # removal and no second message (story 12's own idempotency).
            return Outcome(answer=answer)
        if answer is Answer.CONFIRMED:
            # **The same question ``offerable`` asks, asked through the same
            # predicate**: has the main already answered about this? It is the
            # ladder's own reader and not a second opinion about the field, and
            # it is deliberately not a rung comparison — no rung is decided
            # here, and ``tests/test_ladder.py`` keeps that single-answered.
            # ``known_to_main`` is written by nothing but an `assert`-level
            # promotion, so a belief carrying it is one this main has already
            # confirmed, and a second *yes* moves nothing and appends nothing.
            if ladder.known_to_main(held):
                return Outcome(answer=answer)
            fields = ladder.promote(held, to=License.ASSERT, acknowledged=True)
            actor.store.record(Op.ASSERT, offer.belief_id, t, **fields)
            return Outcome(answer=answer, promoted=fields)

        removal = correction.plan(
            meaning_of(text),
            target=offer.belief_id,
            belief=held,
            source=Source.TABLE,
        )
        if removal is None:
            return Outcome(answer=answer)
        actor.store.record(
            removal.op,
            correction.record_id(removal, t=t),
            t,
            **correction.fields(removal, t=t),
        )
        return Outcome(answer=answer, removal=removal)


# ── the collaborators, each asked without being trusted ──────────────────────


def _in_crisis(registry: object, main_id: str) -> bool:
    """Whether the mode is open. **Fails closed**: a registry that cannot
    answer is treated as a main who might be in the mode, because the cost of
    demonstrating to somebody in crisis is not symmetric with the cost of not
    demonstrating to somebody who is fine."""
    ask = getattr(registry, "crisis_open", None)
    if not callable(ask):
        return True
    try:
        return bool(ask(main_id))
    except Exception as exc:  # noqa: BLE001 - the class only (AD-22)
        logger.error(
            "the crisis mode could not be read for main=%s (%s); no "
            "demonstration runs", main_id, type(exc).__name__,
        )
        return True


def _ceiling(registry: object, main_id: str):
    """This main's global license cap (AD-28), or ``None``.

    Read and handed to ``split`` rather than omitted, because a capped belief's
    wording must be withheld exactly as an uncapped `behave` belief's is — and
    because ``resolve`` has no default for it on purpose.
    """
    ask = getattr(registry, "license_ceiling", None)
    if not callable(ask):
        return None
    try:
        return ask(main_id)
    except Exception as exc:  # noqa: BLE001 - the class only (AD-22)
        logger.warning(
            "the license ceiling could not be read for main=%s (%s)",
            main_id, type(exc).__name__,
        )
        return None


async def _beliefs(registry: object, main_id: str) -> Mapping[str, Any]:
    """This main's current fold, or an empty one. Never raises."""
    try:
        async with registry.acquire(main_id) as actor:
            return dict(actor.store.state().beliefs)
    except Exception as exc:  # noqa: BLE001 - the class only (AD-22)
        logger.error(
            "the ledger could not be read for main=%s (%s); nothing is "
            "offered", main_id, type(exc).__name__,
        )
        return {}


def _has_voice(voice: object, main_id: str) -> bool:
    """Whether a composer is equipped for this main.

    Asked before anything is awaited, for ``half.voice.turn.words``' own reason:
    a deployment that has equipped nobody must not put a bound in front of a
    demonstration to find out what it already knows.
    """
    holds = getattr(voice, "holds", None)
    if not callable(holds):
        return False
    try:
        return bool(holds(main_id))
    except Exception:  # noqa: BLE001 - an unequipped main, either way
        return False


def _reachable(channel: object, main_id: str) -> bool:
    """Whether the platform will carry an unprompted message right now (AD-7).

    The rule lives on the port and nowhere else; this branches on the answer
    and never learns it. Fails closed — an adapter that cannot answer is not one
    to send an unprompted first message through.
    """
    ask = getattr(channel, "capability_query", None)
    if not callable(ask):
        return False
    try:
        return bool(getattr(ask(main_id), "may_send_freeform", False))
    except Exception as exc:  # noqa: BLE001 - the class only (AD-22)
        logger.warning(
            "reachability could not be read for main=%s (%s); nothing is sent",
            main_id, type(exc).__name__,
        )
        return False


async def _delivered(channel: object, main_id: str, text: str) -> bool:
    """Send ``text`` and answer whether the platform actually carried it.

    ``SendResult.parts`` of zero means nothing was delivered, which an adapter
    may answer instead of raising — the contract ``half.channel.port`` states
    and which the morning surface once discarded, spending a main's one
    unprompted message on nothing. Nothing of ``text`` reaches a log line here
    (AD-22).
    """
    try:
        result = await channel.send(main_id, text)
    except Exception as exc:  # noqa: BLE001 - the class only (AD-22)
        logger.error(
            "a demonstration message could not be sent to main=%s (%s)",
            main_id, type(exc).__name__,
        )
        return False
    parts = getattr(result, "parts", 0)
    return isinstance(parts, int) and parts > 0


async def _pulled(
    pull: Callable[[], Awaitable[Any]], *, main_id: str, seconds: float
) -> None:
    """Run the mailbox pull under its share of the budget. Never raises.

    Cut at the deadline rather than allowed to run on, and the cut is safe by
    construction: ``half.ingest.pipeline`` writes each receipt before it hands
    the body on, so a pull stopped part-way keeps every receipt it wrote and
    every candidate it gathered, and admission needs no body. What is lost is
    the tail of the mailbox, which the next pull reads.

    A pull that fails costs the claims and never the receipts, which is
    ``half.__main__.ingest_mail``'s own rule one layer down.
    """
    try:
        async with asyncio.timeout(seconds):
            await pull()
    except TimeoutError:
        logger.warning(
            "the mailbox pull for main=%s was cut at %.0f seconds so the "
            "demonstration could still be composed inside CAP-2's budget; "
            "at most %d message(s) fit in the worst case",
            main_id, seconds, messages_that_fit(),
        )
    except Exception as exc:  # noqa: BLE001 - the class only (AD-22)
        logger.error(
            "the mailbox pull failed for main=%s (%s); whatever was captured "
            "before it stopped is captured", main_id, type(exc).__name__,
        )


def _check_constants() -> None:
    """Import-time invariants, as raises rather than bare ``assert``.

    A guarantee ``python -O`` removes is not a guarantee, and *there is time
    left to speak in* is exactly the kind an optimisation flag would take away
    while the module still imported cleanly.
    """
    if BUDGET_SECONDS <= 0:
        raise OnboardError(
            f"a budget of {BUDGET_SECONDS} is not a budget; CAP-2's ninety "
            "seconds is a requirement and not a decoration"
        )
    if PULL_SECONDS <= 0:
        raise OnboardError(
            f"the compose reserve is {COMPOSE_SECONDS} seconds against a "
            f"budget of {BUDGET_SECONDS}, which leaves no time to read a "
            "mailbox in. A demonstration with nothing behind it is not a "
            "demonstration"
        )
    if messages_that_fit() < 1:
        raise OnboardError(
            f"no message at all fits inside {BUDGET_SECONDS} seconds at the "
            f"shipped bounds ({GATE_BOUND} + {READ_BOUND} per body). A budget "
            "nothing fits inside is a number rather than a bound, and a "
            "demonstration that can never read anything is not one"
        )


_check_constants()

__all__ = [
    "BUDGET_SECONDS",
    "COMPOSE_SECONDS",
    "PULL_SECONDS",
    "Answer",
    "Demonstration",
    "Offer",
    "Outcome",
    "Reason",
    "answered",
    "chosen",
    "demonstrate",
    "meaning_of",
    "messages_that_fit",
    "offerable",
    "reading",
]
