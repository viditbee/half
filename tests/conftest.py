from __future__ import annotations

import ast
from pathlib import Path
from typing import Final

import pytest

from half.crisis import safetyplan
from half.governance import ladder
from half.governance.ladder import License
from half.loops import ledger
from half.store.ops import TOUCH_TENSION, Op
from half.store.records import EXPIRED_AT, INVALID_AT
from half.surface import touch as touch_module
from half.store.store import Store


def seed_belief(
    store,
    ident,
    t,
    *,
    rung=License.BEHAVE,
    support=None,
    quarantine=None,
    **fields,
):
    """Append a belief at ``rung``, through the ladder.

    **The one sanctioned writer of a license field outside ``half/governance/``,
    and it exists so that the writer gate in ``tests/test_ladder.py`` can be
    absolute.** A test that spells ``license="assert", support=[...],
    known_to_main=True`` into a record is doing exactly what story 5a says
    nobody may do — it makes `assert` a field you can set, at the price of
    three fields instead of one. So tests do what production will: admit a
    belief at the weakest rung, then *promote* it, which is an event with the
    main and refuses without a receipt.

    ``quarantine`` is a reason string, and it goes through the candidate-then-
    answer path for the same reason.
    """
    store.record(Op.ASSERT, ident, t, **fields, **ladder.admitted(support=support))
    target = ladder.rung_of(rung)
    if target is not ladder.FLOOR:
        record = store.state().beliefs[ident]
        store.record(
            Op.ASSERT, ident, t,
            **ladder.promote(record, to=target, acknowledged=True),
        )
    if quarantine is not None:
        record = store.state().beliefs[ident]
        candidate = ladder.quarantine_candidate(record, reason=quarantine)
        store.record(
            Op.ASSERT, ident, t,
            **ladder.quarantine(record, candidate=candidate, answered=True),
        )
    return store.state().beliefs[ident]


#: The one sentence the shared morning double writes. It shares **no adjacent
#: word pair** with any claim any fixture in this suite seeds, which is
#: load-bearing twice over: the AD-18 tripwire refuses a morning that repeats a
#: withheld wording, and a double whose output happened to collide with one
#: would silence every morning in the suite for a reason nobody would look for.
COMPOSED: Final[str] = "sunlight on the veranda, and a whole Tuesday ahead"

#: The main's own last message, as ``half.actor.runtime`` records it. Present so
#: the composer has a language to answer in — a fixture without one is a main
#: Half has never heard from, and gets no unprompted message at all.
LAST_MESSAGE: Final[str] = "morning — still turning that over"


def seed_message(store, text=LAST_MESSAGE, *, ident="b_said", t="2026-08-31T00:00:00Z"):
    """The main's own message, exactly as the turn path writes one.

    ``half.actor.runtime._pipeline`` appends every inbound message as a
    `stated`-ledger belief whose claim is the main's own words, admitted at the
    weakest rung. That record is what ``half.channel.window`` rebuilds
    reachability from and what ``half.voice.compose.sample_from`` reads the
    language off, so a fixture that omits it is not a simplified main — it is a
    main who has never written, whom Half may not contact at all.
    """
    return seed_belief(store, ident, t, subject="self", claim=text,
                       **{"ledger": "stated"})


def quotable_of(work) -> str:
    """The ``may-be-said`` block out of a generation request, as a model sees it.

    Read off the assembled turn rather than off the ``Context``, because that is
    the only thing a generator is ever handed — so a double built on it cannot
    accidentally quote material the composer withheld, and a test that asserts a
    claim reached the wire is asserting it reached the *prompt* first.
    """
    from half.voice.compose import MAY_BE_SAID

    for block in work.prompt.turns[0].text.split("\n\n"):
        if block.startswith(MAY_BE_SAID):
            return block[len(MAY_BE_SAID):].strip()
    return ""


class GeneratorDouble:
    """The port's narrow generator, and nothing wider. **One of these in the
    tree**, which is the rule the door predicate below states and which story
    13a's first build broke three times over in a single story: `test_voice`,
    `test_morning_words` and this file each grew their own.

    One public method, so ``Voice`` — which refuses a holder with any public
    callable but ``generate`` — is held to the same shape as the real thing.
    ``calls`` and ``requests`` are public and are deliberately *not* callable:
    a case that needs to assert a provider was never reached has to be able to
    ask, and the alternative is the double this replaced, whose only signal was
    an ``AssertionError`` the gate swallowed into ``Unspoken(RAISED)``.

    ``answers`` are used in order and the last one repeats. A ``str`` becomes a
    ``Completion``; a ``BaseException`` is raised; a callable is handed the
    ``Generate``; anything else is returned as-is, so a case can hand back a
    ``Failure`` or something unreadable.
    """

    def __init__(self, *answers, sleep: float = 0.0) -> None:
        self._answers = list(answers) or [None]
        self._sleep = sleep
        self._seen: list = []

    async def generate(self, work):
        from half.model.port import Completion, Usage

        self._seen.append(work)
        if self._sleep:
            await __import__("asyncio").sleep(self._sleep)
        index = min(len(self._seen), len(self._answers)) - 1
        answer = self._answers[index]
        if isinstance(answer, BaseException):
            raise answer
        if callable(answer):
            answer = answer(work)
        if isinstance(answer, str):
            return Completion(text=answer, usage=Usage(micro_usd=9_000))
        return answer

    @property
    def calls(self) -> int:
        return len(self._seen)

    @property
    def requests(self) -> list:
        return list(self._seen)


class NeverGenerates:
    """A holder that must never be reached, **and counts the times it was**.

    Raising alone is not enough and review round 1 proved it: ``Voice`` catches
    ``Exception`` and turns an ``AssertionError`` into ``Unspoken(RAISED)``,
    which is a member of ``REASONS``, so a case asserting *"silence, for some
    reason in the set"* passed whether or not the provider had been paid three
    times. Swapping the composer above ``capability_query`` left the whole suite
    green. So the signal is a counter a case can assert on.
    """

    def __init__(self) -> None:
        self._seen: list = []

    async def generate(self, work):
        self._seen.append(work)
        raise AssertionError("a model was consulted where none may be")

    @property
    def calls(self) -> int:
        return len(self._seen)


def echo(work):
    """``COMPOSED``, and then whatever the prompt said may be stated.

    **The one composing double in the tree**, and the default for both helpers
    below. It is doing work rather than being convenient: a double that answered
    a fixed sentence would satisfy every *"that claim did not reach the wire"*
    assertion in the suite — including the ones AD-18 is supposed to be
    withholding — so the behave-material cases would have passed with the two
    channels merged.
    """
    said = quotable_of(work)
    return f"{COMPOSED} {said}".strip()


def stub_voice(text=None, *, mains=("vidit",), **kwargs):
    """A ``Voice`` that composes for ``mains`` and for nobody else.

    ``text`` overrides ``echo`` with a fixed string, or with a callable taking
    the ``Generate`` and returning whatever a case needs. Use ``a_voice`` where
    the case needs the holder as well, which is most of them.
    """
    from half.voice.gate import Voice

    return Voice(
        {main: GeneratorDouble(echo if text is None else text) for main in mains},
        bound_seconds=1.0, **kwargs
    )


def a_voice(*answers, main="vidit", sleep=0.0, bound_seconds=1.0, **kwargs):
    """A ``Voice`` **and the holder inside it**, so a case can count the calls.

    **One of these in the tree**, which is the rule ``GeneratorDouble`` above
    states and which story 13b's first build broke three times over in a single
    story: ``test_bought``, ``test_correction`` and ``test_turn_words`` each
    grew their own, two of them byte-identical. A helper per file is how two
    cases that read like the same case stop testing the same thing.

    ``answers`` are ``GeneratorDouble``'s: used in order, the last repeating, a
    ``str`` becoming a ``Completion``, an exception raised, a callable handed
    the ``Generate``. With none given the holder writes ``echo``.
    """
    from half.voice.gate import Voice

    holder = GeneratorDouble(*(answers or (echo,)), sleep=sleep)
    return Voice({main: holder}, bound_seconds=bound_seconds, **kwargs), holder


@pytest.fixture
def store(tmp_path):
    with Store(tmp_path / "main") as s:
        yield s


@pytest.fixture
def seed():
    return seed_belief


@pytest.fixture
def tier_change_log(tmp_path):
    """A log whose consolidation output was produced under two different model
    tiers, plus a month rollover.

    This fixture is the point of the replay test. A fold that re-derives
    instead of replaying recorded outcomes would produce different tensions on
    the second run, and a fixture without a tier change would never notice
    (AD-30).
    """
    with Store(tmp_path / "tiered") as s:
        seed_belief(s, "b_1", "2026-07-04T08:00Z", subject="self",
                    claim="replies to mother within three minutes",
                    ledger="revealed", independent=2, model_tier="cheap")
        seed_belief(s, "b_2", "2026-07-19T21:30Z", subject="self",
                    claim="said he would start running in March", ledger="stated",
                    rung=License.ASK, independent=1, model_tier="cheap")
        s.record(Op.TENSION, "x_1", "2026-07-20T02:10Z",
                 between=["b_1", "b_2"], state="fresh", model_tier="cheap",
                 **ladder.admitted())
        # tier changes here — anything re-derived would now differ
        seed_belief(s, "b_3", "2026-08-02T07:15Z", subject="self",
                    claim="has not flown a paraglider in three years",
                    ledger="revealed", independent=3, model_tier="frontier")
        s.record(Op.TENSION, "x_2", "2026-08-03T02:40Z",
                 between=["b_2", "b_3"], state="widening", model_tier="frontier",
                 **ladder.admitted())
        # A tension that *moved* (story 9c). Here for the reason the loop
        # transitions below are: the replay test is what proves a transition
        # merges over the mint rather than replacing it, and that what comes
        # back after a rebuild is the tension's new state **with its pair and
        # its license still on it**. A transition that replaced the record
        # would round-trip perfectly and be a tension with no sides — the drift
        # computation would report it as not computable for ever, silently.
        s.record(Op.TENSION, "x_1", "2026-08-04T02:10Z", state="persistent")
        # And a tension resolved by a correction to one of its two entries —
        # the *inverse* of the loop firewall, which is exactly why it is in the
        # fixture that proves replay. A tension left `fresh` over a retracted
        # entry would survive a rebuild looking live; one *deleted* by the
        # correction would lose a record of the main's own life. It has to come
        # back present and `resolved`.
        seed_belief(s, "b_4", "2026-08-04T08:00Z", subject="self",
                    claim="says the mornings are for writing", ledger="stated",
                    independent=1, model_tier="frontier")
        seed_belief(s, "b_5", "2026-08-04T08:01Z", subject="self",
                    claim="has sent no draft since May", ledger="revealed",
                    independent=2, model_tier="frontier")
        s.record(Op.TENSION, "x_3", "2026-08-05T02:10Z",
                 between=["b_4", "b_5"], state="fresh", model_tier="frontier",
                 **ladder.admitted())
        s.record(Op.RETRACT, "r_x3", "2026-08-06T09:00Z", target="b_5")
        s.record(Op.LOOP_TRANSITION, "l_1", "2026-08-03T02:41Z",
                 loop="buy-farmland", state="stalled", timescale="years",
                 last_movement="2026-03-12")
        # Opens, moves and closes (story 8, CAP-6). Here for the reason the
        # crisis and aftercare records are: the replay test is what proves a
        # loop's state, its own timescale and its last movement fold,
        # round-trip through SQLite and reproduce byte-identically. A loop that
        # came back from a rebuild with a different state is a silently
        # different ranking function for everything Half does — and one that
        # came back with a *borrowed* timescale would be nagged on somebody
        # else's schedule.
        #
        # Four shapes, deliberately: a loop opened and then moved twice, a loop
        # that reached `achieved` and is kept rather than deleted, a loop with
        # no timescale at all (which must survive the rebuild still having
        # none), and a loop the main expunged.
        s.record(Op.LOOP_TRANSITION, "l_2", "2026-08-03T02:42Z",
                 **ledger.opened("swim-weekly", state="advancing",
                                 timescale="weeks",
                                 last_movement="2026-07-28T06:00Z",
                                 loops=s.state().loops))
        s.record(Op.LOOP_TRANSITION, "l_3", "2026-08-10T02:42Z",
                 **ledger.move("swim-weekly", at="2026-08-09T06:30Z"))
        s.record(Op.LOOP_TRANSITION, "l_4", "2026-08-12T02:42Z",
                 **ledger.move("swim-weekly", at="2026-08-11T06:30Z",
                               state="achieved"))
        s.record(Op.LOOP_TRANSITION, "l_5", "2026-08-13T02:42Z",
                 **ledger.opened("learn-tabla", state="advancing",
                                 loops=s.state().loops))
        # A loop that acquired its period after the fact — its own named op,
        # never a passenger on a movement append. Separate from `learn-tabla`,
        # which stays period-less on purpose: a rebuild that quietly filled that
        # gap in would look like a successful replay and be a different ranking
        # function.
        s.record(Op.LOOP_TRANSITION, "l_5b", "2026-08-13T03:00Z",
                 **ledger.opened("write-more", state="advancing",
                                 last_movement="2026-08-01",
                                 loops=s.state().loops))
        s.record(Op.LOOP_TRANSITION, "l_5c", "2026-08-13T03:01Z",
                 **ledger.rescale("write-more", to="weeks",
                                  loops=s.state().loops))
        s.record(Op.LOOP_TRANSITION, "l_6", "2026-08-14T02:42Z",
                 **ledger.opened("sell-the-flat", state="stalled",
                                 timescale="months",
                                 last_movement="2026-01-04",
                                 loops=s.state().loops))
        # A raise on a loop the main afterwards erases (story 10). It must come
        # back from a rebuild carrying neither the slug nor the raise: a touch
        # is tombstoned by the same ``loop``-field match that tombstones a
        # transition, because a loop slug is a phrase about a person's life and
        # surviving an erasure is not an erasure. Its *record id* is built from
        # the stamp and never from the slug, for the same reason — a tombstone
        # keeps its id.
        s.record(Op.TOUCH, "tc_2026-08-14T12:00Z", "2026-08-14T12:00Z",
                 **touch_module.raised(
                     "sell-the-flat",
                     origin=touch_module.Origin(kind=TOUCH_TENSION, id="x_2"),
                 ))
        # Erased through the **public** path, which is what a main's erasure
        # actually goes through: it removes the loop and tombstones the
        # transition bodies, where a bare op leaves the slug in the log.
        s.expunge("sell-the-flat", t="2026-08-15T02:42Z")
        # A crisis entry and an operator reversal (CAP-12). Here rather than in
        # a fixture of their own because the replay test is what proves the new
        # op folds, round-trips through SQLite and reproduces byte-identically
        # — and because "last record wins" is exactly the property a fold can
        # get wrong while every other test stays green.
        s.record(Op.CRISIS, "cr_tiered_1", "2026-08-04T01:00Z",
                 state="entered", tier="disclosure", score=2)
        s.record(Op.CEILING, "c_tiered_1", "2026-08-04T01:00Z",
                 rung="behave", because="crisis mode entered (CAP-12)")
        s.record(Op.CRISIS, "cr_tiered_2", "2026-08-05T09:30Z",
                 state="reversed", because="false positive, confirmed")
        # The phone book (story 6b). Here for the reason the crisis records
        # are: the replay test is what proves the new fields fold, round-trip
        # through SQLite and reproduce byte-identically. A contact whose
        # confirmation did not survive a rebuild is a contact Half stops
        # offering after a restart, which is a silent regression on the one
        # path where silence is the failure.
        seed_belief(s, "b_contact", "2026-08-06T10:00Z", rung=License.ASSERT,
                    support=["s_9"], contact="आशा", handle="asha")
        seed_belief(s, "b_place", "2026-08-06T10:01Z", rung=License.ASSERT,
                    support=["s_9"], region="in")
        # Aftercare (story 6c). Here for the reason the crisis records are: the
        # replay test is what proves the new op folds, round-trips through
        # SQLite and reproduces byte-identically. A recorded *decline* that did
        # not survive a rebuild is a question the main already answered being
        # put to them again after a restart — and, worse, a later "yes" free to
        # land on it. The held safety plan travels for the same reason: a plan
        # Half stops holding after a restart is a document produced at three in
        # the morning by nothing.
        s.record(Op.AFTERCARE, "ac_tiered_1", "2026-08-07T09:00Z", state="asked")
        s.record(Op.CEILING, "c_tiered_2", "2026-08-07T09:00Z",
                 rung="ask", because="aftercare: the floor is past, one step")
        s.record(Op.AFTERCARE, "ac_tiered_2", "2026-08-21T18:30Z", state="declined")
        # What Half raised, and when (story 10, CAP-8). Here for the reason
        # every record above is: the replay test is what proves the new op
        # folds, round-trips through SQLite and reproduces byte-identically.
        # A raise that did not survive a rebuild is a loop whose nagging bound
        # answers *may raise* again the moment a derived view is discarded —
        # so a years-long loop would be raised on the morning after every
        # rebuild, which is the one failure the bound exists to make
        # impossible. And ``last_touch`` is what *"at most one a day"* is
        # computed from: losing it in a rebuild buys a second unprompted
        # message on a day one was already sent.
        #
        # The raise on a loop the main afterwards erased is seeded above,
        # beside that erasure.
        s.record(Op.TOUCH, "tc_2026-08-16T03:10Z", "2026-08-16T03:10Z",
                 **touch_module.spoke(
                     day="2026-08-16",
                     origin=touch_module.Origin(kind=TOUCH_TENSION, id="x_1"),
                     loops=("swim-weekly",),
                 ))
        # A day marker that raised nothing and sent nothing — the repair path.
        # Here because it is the one touch shape carrying neither a loop nor an
        # origin, and a fold that required either would drop it silently,
        # leaving the main's day unspent after every rebuild.
        s.record(Op.TOUCH, "tc_2026-08-17T03:10Z", "2026-08-17T03:10Z",
                 **touch_module.repaired(day="2026-08-17"))
        # And a raise that spends no day — the shape CAP-10's interrupt will
        # use. It must round-trip as a raise on the loop's bound *without*
        # becoming the day marker, which is the distinction story 10's review
        # had to introduce.
        s.record(Op.TOUCH, "tc_2026-08-18T09:00Z", "2026-08-18T09:00Z",
                 **touch_module.raised(
                     "swim-weekly",
                     origin=touch_module.Origin(kind=TOUCH_TENSION, id="x_1"),
                 ))
        # The spend half of the trust balance (story 5b, CAP-4). Here for the
        # reason every record above is — the replay test is what proves a new op
        # folds, round-trips through SQLite and reproduces byte-identically —
        # and with one difference worth stating, because it looks like an
        # omission and is not: **an ``asked`` record materializes nothing.**
        #
        # The balance is *computed from the log* rather than counted into a
        # field, so there is deliberately no derived state for this record to
        # produce. What this fixture proves is therefore the other half: that a
        # spend folds without raising, survives the round-trip, and does not
        # disturb anything else — and that the balance read off this log is the
        # same before and after a rebuild, which is asserted in
        # ``tests/test_replay.py``. A counter on ``State`` would round-trip
        # perfectly and still be wrong; nothing here can hold one.
        #
        # **Two spends against one delivered favour, which is deliberately
        # overdrawn.** ``ActorRegistry.note_ask`` refuses a spend it cannot pay
        # for, so this shape is not reachable through the product's own path —
        # it is reachable through an *erasure*, which is the case
        # ``tests/test_trust.py`` exercises directly: erasing the loop a day
        # marker named tombstones that marker, so a favour stops earning
        # underneath a question that was already asked. A log in that state has
        # to fold and replay like any other, and the canonical fixture is where
        # that is proved. ``tests/test_replay.py`` asserts the exact numbers,
        # because an earlier version asserted truthiness and would have passed
        # on any two non-zero counts.
        s.record(Op.ASKED, "qa_2026-08-16T09:00Z", "2026-08-16T09:00Z",
                 question="q_farmland_intent", about="b_2")
        s.record(Op.ASKED, "qa_2026-08-19T09:00Z", "2026-08-19T09:00Z",
                 question="q_swim_register", about="b_1")
        # Corrections carrying an attribution (CAP-11, story 12). Here for the
        # reason every record above is — the replay test is what proves a new
        # field folds, round-trips through SQLite and reproduces
        # byte-identically — and with the difference that looks like an
        # omission and is not: **an attribution materializes nothing.**
        #
        # It is folded from the log, like the trust balance, because the belief
        # it describes has *left* the fold and there is nowhere in the derived
        # view for a cause to hang on. So what this fixture proves is the other
        # half: that the two stamps survive a rebuild verbatim, and that the
        # three states read the same before and after — which
        # ``tests/test_replay.py`` asserts by value, because a build that
        # defaulted an unstated cause would replay perfectly and still be wrong.
        #
        # Three beliefs, one per state, and none of them a side of any tension
        # above: what a correction does to a *tension* is already fixed by
        # ``x_3`` and must not be restated here from a second place.
        seed_belief(s, "b_c1", "2026-08-22T08:00Z", subject="self",
                    claim="rides to the office on a Tuesday", ledger="revealed",
                    independent=2, model_tier="frontier")
        seed_belief(s, "b_c2", "2026-08-22T08:01Z", subject="self",
                    claim="keeps the good knives in the second drawer",
                    ledger="stated", independent=1, model_tier="frontier")
        seed_belief(s, "b_c3", "2026-08-22T08:02Z", subject="self",
                    claim="reads two books at once", ledger="revealed",
                    independent=2, model_tier="frontier")
        s.record(Op.REVISE, "co_2026-08-23T09:00Z", "2026-08-23T09:00Z",
                 target="b_c1", **{EXPIRED_AT: "2026-08-23T09:00Z"})
        s.record(Op.RETRACT, "co_2026-08-23T09:01Z", "2026-08-23T09:01Z",
                 target="b_c2", **{INVALID_AT: "2026-08-23T09:01Z"})
        # The third state, and the one a default would silently overwrite: the
        # main said it was wrong and did not say which, so the record says
        # nothing about the cause and must still say nothing after a rebuild.
        s.record(Op.RETRACT, "co_2026-08-23T09:02Z", "2026-08-23T09:02Z",
                 target="b_c3")
        s.record(Op.ASSERT, "p_tiered", "2026-08-21T18:31Z",
                 **safetyplan.held_fields([
                     "When I start pacing at two in the morning, that is the sign.",
                     "Ring Asha. She knows.",
                 ]))
        yield s


class FakeTransport:
    """The whole network surface the adapter needs, so tests stay offline."""

    def __init__(self, updates=None, fail=None, fail_times=None):
        self.updates = updates or []
        self.sent: list[tuple[str, str]] = []
        self.fail = fail
        self.fail_times = fail_times  # fail this many times, then succeed
        self.attempts = 0

    async def poll(self):
        for update in self.updates:
            yield update

    async def send_message(self, chat_id: str, text: str) -> str:
        self.attempts += 1
        if self.fail is not None:
            if self.fail_times is None or self.attempts <= self.fail_times:
                raise self.fail
        self.sent.append((chat_id, text))
        return f"mid-{len(self.sent)}"


def msg(**kw):
    return {"chat_id": "123", "text": "hi", "message_id": "1", "date": 1000, **kw}


@pytest.fixture
def fake_transport():
    return FakeTransport


# ── the narrow door, as a predicate two packages read ────────────────────────
#
# Story 5b built this for ``half/trust`` and story 11's first build copied it
# into ``tests/test_bought.py`` as a **string-prefix denylist** — which is the
# same defect 5b's review had already found and fixed, arriving one package
# over. ``from half.store import store as _second`` has ``ImportFrom.module ==
# "half.store"``, which no prefix list contained, and ``self.ledger.acquire(...)``
# is not any forbidden word at all. So the machinery lives here now and both
# packages are swept by one rule: if a predicate is worth having twice, it is
# worth having once.

ROOT = Path(__file__).resolve().parents[1]

#: What a module inside a guarded package may not reach, as **dotted roots
#: rather than as import lines**. A second writer is against AD-1 and CAP-4
#: both, and the rule is *"no path to a store"*, not *"none of these spellings"*.
CLOSED: Final[tuple[str, ...]] = (
    "half.store.store", "half.store.log", "half.store.db", "half.actor",
)

#: What no module that decides *whether* to ask may reach: a model, a channel,
#: or the network. Written as roots for the reason ``CLOSED`` is — a list of
#: forbidden strings only ever catches the spellings somebody thought of.
UNREACHABLE: Final[tuple[str, ...]] = (
    "half.model", "half.channel", "anthropic", "httpx", "socket", "urllib",
    "http", "requests",
)

#: Roots lifted for one package, named beside the rule they are lifted from
#: rather than dropped from it — so the exemption is one line somebody has to
#: read, and everything else in ``UNREACHABLE`` still stands over that package.
#:
#: Two entries, and the reason in both cases is the difference between the
#: questions the packages answer. ``half/trust`` and ``half/questions`` decide
#: whether to *ask*, and a model there would be a question composed by a model —
#: the thing their Never lists forbid. ``half/correction``'s recall instrument
#: **is** a model by design (CAP-11): the ways a person says *"that's wrong"* are
#: not enumerable, so a phrase table cannot be the whole of it. ``half/voice``
#: is a model by definition (story 13a): its whole subject is composing the
#: morning's sentence through the port, and the alternative — a written template
#: shipped worldwide — is the thing ``half/context/channels.py`` records the
#: objection to.
#:
#: Each exemption is paid for with a stricter rule of its own.
#: ``tests/test_correction.py``: exactly one module in that package may name the
#: model, it may name only the port, and what it holds is the port's narrow
#: classifier — an object with no method that returns text.
#: ``tests/test_voice.py``: what that package holds is the port's narrow
#: *generator* — refused at construction unless ``generate`` is the only public
#: method on it — and the channel, the store and the network stay closed to it
#: here, which is the half that would otherwise go quiet.
#:
#: **The pin is honest, and that is checked.** Every entry is a deliberate
#: decision with a reason written beside it; ``tests/test_correction.py`` and
#: ``tests/test_voice.py`` each assert the exact contents of this mapping, so a
#: third package cannot acquire the lift by being added to a list.
LIFTED: Final[dict[str, tuple[str, ...]]] = {
    "half/correction": ("half.model",),
    "half/voice": ("half.model",),
}


def outward(package: str) -> tuple[str, ...]:
    """What ``package`` may not reach. ``UNREACHABLE`` minus its own lift.

    Derived rather than restated, so there is one list of forbidden roots in the
    tree and a package's exemption is visible as an exemption.
    """
    lifted = LIFTED.get(package, ())
    return tuple(root for root in UNREACHABLE if root not in lifted)


def resolved_imports(path: Path) -> set[str]:
    """Every dotted target ``path`` imports, both spellings resolved.

    ``import half.store.store`` and ``from half.store import store`` and
    ``from half.store.store import Store`` all resolve to something under
    ``half.store.store``, so a rule written about the module catches every way
    of naming it. Relative imports resolve through the package the file sits in.
    """
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    # A file outside the tree — a synthetic bypass written to ``tmp_path`` —
    # has no package to resolve a relative import against, and answering ``()``
    # for it is correct: the bypasses this is proved against are all absolute.
    package = (
        path.relative_to(ROOT).with_suffix("").parts[:-1]
        if path.is_relative_to(ROOT) else ()
    )
    found: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                found.add(alias.name)
        elif isinstance(node, ast.ImportFrom):
            if node.level:
                base = ".".join(package[: len(package) - (node.level - 1)])
            else:
                base = node.module or ""
            for alias in node.names:
                found.add(f"{base}.{alias.name}" if base else alias.name)
                if base:
                    found.add(base)
    return found


def reaches(path: Path, roots: tuple[str, ...]) -> list[str]:
    """The imports of ``path`` that land inside ``roots``. The predicate."""
    return sorted(
        name for name in resolved_imports(path)
        if any(name == root or name.startswith(f"{root}.") for root in roots)
    )


def ledger_reach(path: Path) -> set[str]:
    """Every name this module takes off ``self.ledger``.

    A **predicate over the door**, not a list of forbidden words. The rule is
    that a package reaches a main's log through its injected ledger and through
    nothing else, so the thing to measure is what it asks that object for — a
    word list would have to guess the name of the next wider door, and every
    denylist this codebase has shipped was walked around. It also has to
    tolerate ``list.append``, which is not a log append and which an earlier
    spelling of this gate reported as one.

    **Every attribute, not only the ones called in place.** This read calls
    alone until a mutation walked past it: ``_door = self.ledger.acquire``
    followed by ``async with _door(main_id)`` is a call on a *local*, so a scan
    that matched ``ast.Call`` saw nothing at all. Taking the name is the reach;
    what happens to it afterwards is not something an AST scan can follow.
    """
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    found: set[str] = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Attribute):
            continue
        target = node.value
        if isinstance(target, ast.Await):
            target = target.value
        if (
            isinstance(target, ast.Attribute)
            and target.attr == "ledger"
            and isinstance(target.value, ast.Name)
            and target.value.id == "self"
        ):
            found.add(node.attr)
    return found


def door_of(protocol) -> set[str]:
    """Every public method a protocol declares, its bases included.

    Read off the MRO rather than off ``vars`` alone, because
    ``QuestionLedger`` extends ``TrustLedger``: a scan that saw only the
    subclass's own two names would report 5b's three methods as outside the
    door, and one that saw only the base would miss the addition.
    """
    found: set[str] = set()
    for base in protocol.__mro__:
        found |= {
            name for name, value in vars(base).items()
            if not name.startswith("_") and callable(value)
        }
    return found
