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


def ledger_calls(path: Path) -> set[str]:
    """Every method this module calls on ``self.ledger``.

    A **predicate over the door**, not a list of forbidden words. The rule is
    that a package reaches a main's log through its injected ledger and through
    nothing else, so the thing to measure is what it asks that object for — a
    word list would have to guess the name of the next wider door, and every
    denylist this codebase has shipped was walked around. It also has to
    tolerate ``list.append``, which is not a log append and which an earlier
    spelling of this gate reported as one.
    """
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    found: set[str] = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute):
            continue
        target = node.func.value
        if isinstance(target, ast.Await):
            target = target.value
        if (
            isinstance(target, ast.Attribute)
            and target.attr == "ledger"
            and isinstance(target.value, ast.Name)
            and target.value.id == "self"
        ):
            found.add(node.func.attr)
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
