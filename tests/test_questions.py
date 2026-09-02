"""CAP-4 story 11: minting a question, and the bound on asking it again.

``tests/test_trust.py`` carries the currency, ``tests/test_unasked.py`` the
gates, and ``tests/test_bought.py`` the channel. This file carries the two
things story 11 adds underneath them: the **derived id** that makes a re-ask
recognizable, and the **answer state folded out of the log** that decides
whether a re-ask is a nag.

**The bound is each wanting's own period and the sweep is the assertion.** One
interval across all four timescales must give four different answers; a single
global cooldown — gbrain's ``NUDGE_COOLDOWN_DAYS = 14``, which nags a workout
routine and never once reaches a farmland loop — fails by name below. The shape
is ``tests/test_nagging.py``'s, deliberately, because it is the same rule about
a different object.

**Both sides of every boundary are pinned, at every timescale.** Story 8's
review found a threshold anything between roughly six and thirteen satisfied,
which is a band and not a number.

**Nothing here waits for real time and nothing here reads a clock.** Every
instant is chosen by the test and passed as an argument, which is the point of
the design under test (AD-30).
"""

from __future__ import annotations

import asyncio
import dataclasses
from pathlib import Path

import pytest

from half.actor.registry import ActorRegistry
from half.civil import DAY
from half.governance import ladder
from half.governance.ladder import License
from half.loops import ledger as loops
from half.loops.timescale import PERIOD_DAYS, Timescale
from half.questions.answered import (
    ANSWERED,
    NEVER_ASKED,
    NO_PERIOD,
    REASONS,
    TOO_SOON,
    UNREADABLE_ASK,
    UNREADABLE_NOW,
    Answer,
    history,
    reaskable,
    responsive,
    spend_of,
)
from half.questions.mint import QUESTION_PREFIX, about_of, mint, minted, question_id
from half.schedule.clock import stamp
from half.store.fold import State
from half.store.fold import fold as fold_records
from half.store.ops import Op
from half.store.records import LEDGER, STATED, Record, make
from half.store.store import Store
from half.trust.balance import balance

pytestmark = [pytest.mark.cap4, pytest.mark.cap4_bought]

ROOT = Path(__file__).resolve().parents[1]

#: 2026-09-01T12:00:00Z — the instant ``tests/test_nagging.py``,
#: ``tests/test_surface.py`` and ``tests/test_pass.py`` all build from.
NOON = 1_788_264_000.0
NOW = stamp(NOON)

FARMLAND = "buy-farmland"


# ── helpers ──────────────────────────────────────────────────────────────────


def an_ask(question="q_b_1", *, at, about="b_1"):
    """One ``asked`` record, built through the real append gate."""
    return make(Op.ASKED, f"qa_{at}", at, question=question, about=about)


def a_reply(at, *, ident="b_inbound", ledger=STATED):
    """One inbound message, shaped the way ``half.actor.runtime`` writes it."""
    return make(
        Op.ASSERT, ident, at, subject="self", claim="whatever they said",
        **{LEDGER: ledger}, **ladder.admitted(),
    )


def ago(days):
    """A stamp ``days`` before ``NOON``."""
    return stamp(NOON - days * DAY)


def asked_days_ago(days, *, question="q_b_1"):
    """The ``Answer`` a log holds for a question put ``days`` ago and ignored."""
    return history([an_ask(question, at=ago(days))])[question]


# ═════════════════════════════════════════════════════════════════════════════
# minting: one question per belief, and the same one every time
# ═════════════════════════════════════════════════════════════════════════════


def test_a_question_id_is_derived_from_the_belief_id_and_is_reversible():
    """The whole reason ids are derived rather than minted.

    A question whose id came from a counter or a stamp would be a *different*
    question every time Half considered asking it, so no fold over the log could
    ever say *"this was already put to them"* — and re-asking would be bounded
    by nothing but the balance, which is the nag this story exists to prevent.
    """
    assert question_id("b_1") == f"{QUESTION_PREFIX}b_1"
    assert about_of(question_id("b_1")) == "b_1"
    assert mint("b_1").id == mint("b_1").id, "a re-ask must be the same question"
    assert mint("b_1").about == "b_1"


def test_the_record_a_spend_writes_and_the_derivation_agree():
    """``about_of`` reads the derivation; the record carries the field. The two
    must be one answer, or a fold places a spend against the wrong wanting."""
    one = mint("b_1")
    record = an_ask(one.id, at=NOW, about=one.about)
    assert spend_of(record) == one.id
    assert about_of(spend_of(record)) == one.about == record.data["about"]


@pytest.mark.parametrize(
    "value", [None, "", "   ", 42, ["b_1"], object()],
    ids=["none", "empty", "blank", "int", "list", "object"],
)
def test_nothing_that_cannot_name_a_belief_mints_a_question(value):
    """Total, and never raises: the caller is on a turn's own path."""
    assert question_id(value) == ""
    assert mint(value) is None
    assert minted([value]) == ()


def test_minting_is_deduplicated_on_the_belief_and_keeps_the_caller_s_order():
    """A candidate set naming one belief twice must not look like two questions
    competing for one favour."""
    found = minted(["b_2", "b_1", "b_2", " b_1 "])
    assert [q.about for q in found] == ["b_2", "b_1"]


def test_a_minted_question_carries_no_text():
    """AD-22 at the layer where it is cheapest to break: an ``Unasked`` is two
    ids, and this asserts the *shape* rather than one instance's contents."""
    fields = {f.name for f in dataclasses.fields(mint("b_1"))}
    assert fields == {"id", "about"}


def test_about_of_refuses_anything_that_is_not_a_derived_id():
    assert about_of("b_1") == ""
    assert about_of(None) == ""
    assert about_of(QUESTION_PREFIX) == ""


# ═════════════════════════════════════════════════════════════════════════════
# matrix: answered / ignored — folded from the log, never stored
# ═════════════════════════════════════════════════════════════════════════════


def test_a_question_never_put_has_no_entry_at_all():
    assert history([a_reply(NOW)]) == {}
    assert reaskable(None, period_days=365, now=NOW).may_ask is True
    assert reaskable(None, period_days=365, now=NOW).reason == NEVER_ASKED


def test_a_question_put_and_ignored_is_asked_and_unanswered():
    """Matrix: *ignored*."""
    answers = history([an_ask(at=ago(2))])
    assert answers["q_b_1"] == Answer(asked=True, asked_at=ago(2))


def test_a_question_put_and_then_a_message_from_the_main_reads_as_answered():
    """Matrix: *answered*. **Responsiveness, not answering** — the module says
    so, and this case is the whole of what "answered" means here."""
    answers = history([an_ask(at=ago(2)), a_reply(ago(1))])
    assert answers["q_b_1"].answered is True
    assert answers["q_b_1"].replied_at == ago(1)


def test_a_reply_that_arrived_before_the_question_answers_nothing():
    """Order is the log's. A message the main sent yesterday did not answer a
    question Half put this morning."""
    answers = history([a_reply(ago(3)), an_ask(at=ago(2))])
    assert answers["q_b_1"].answered is False


def test_a_belief_from_the_revealed_ledger_is_not_the_main_speaking():
    """The mark is the **stated** ledger, which is what ``half.actor.runtime``
    writes on an inbound message. An ingested claim is Half reading somebody's
    mailbox, not the main answering."""
    ingested = a_reply(ago(1), ident="b_ingested", ledger="revealed")
    assert responsive(ingested) is False
    assert history([an_ask(at=ago(2)), ingested])["q_b_1"].answered is False


def test_two_outstanding_questions_are_both_answered_by_one_reply():
    """**The honest limit, asserted rather than hidden.** This recognizes
    responsiveness, and one message cannot be attributed to one of two open
    questions without interpreting it — which is claim derivation, deferred
    with the model port since story 3. It errs toward asking *less*, which is
    the correct direction for a rule whose failure is a nag.
    """
    answers = history([
        an_ask("q_b_1", at=ago(3), about="b_1"),
        an_ask("q_b_2", at=ago(2), about="b_2"),
        a_reply(ago(1)),
    ])
    assert all(answer.answered for answer in answers.values())


def test_putting_a_question_again_starts_it_over():
    """A later ``asked`` record says what happened; nothing here decides whether
    it should have. ``reaskable`` is where that is decided, beforehand."""
    answers = history([an_ask(at=ago(9)), a_reply(ago(8)), an_ask(at=ago(2))])
    assert answers["q_b_1"] == Answer(asked=True, asked_at=ago(2))


def test_an_erased_spend_still_costs_a_favour_and_no_longer_names_its_question():
    """Stated rather than hidden. ``expunge_bodies`` leaves the op and takes the
    body, so the currency still charges for the question — that is
    ``half.trust.balance.spent``'s rule — while the log has stopped saying which
    question it was, so the period no longer bounds it. What is lost is the
    bound, never the payment."""
    # Built the way ``BeliefLog.expunge_bodies`` builds one — the record's op,
    # id and position survive and the body is gone. The append gate refuses a
    # ``tombstone`` field outright, which is why the erasure path does not go
    # through it, and why this fixture does not either.
    erased = Record(
        op=Op.ASKED, id="qa_x", t=ago(2),
        data={"t": ago(2), "op": str(Op.ASKED), "id": "qa_x", "v": 8,
              "tombstone": True},
    )
    assert spend_of(erased) == ""
    assert history([erased]) == {}
    assert balance([erased]).spent == 1


def test_a_record_this_build_cannot_read_contributes_nothing_and_never_raises():
    assert history([None, "not a record", 42]) == {}
    assert spend_of(None) == "" and responsive(None) is False


# ═════════════════════════════════════════════════════════════════════════════
# no counter materializes: AD-3, AD-30
# ═════════════════════════════════════════════════════════════════════════════


def test_no_asked_count_or_answered_flag_exists_on_state():
    """The half of AD-30 a behavioural case cannot give: a stored flag replays
    perfectly, so it is only ever *wrong* and never *inconsistent*, and no
    round-trip assertion in the suite would ever see it."""
    names = {f.name for f in dataclasses.fields(State)}
    forbidden = {
        name for name in names
        if any(word in name for word in ("ask", "answer", "question"))
    }
    assert forbidden == set(), f"{sorted(forbidden)} on State is the counter"


def test_the_answer_state_folds_identically_before_and_after_a_rebuild(tmp_path):
    """Matrix: *replay*. The same log gives the same answers, and the derived
    view is never consulted — so discarding it changes nothing."""
    root = tmp_path / "vidit"
    with Store(root) as store:
        store.record(Op.LOOP_TRANSITION, "l_1", "2026-08-01T00:00Z",
                     **loops.opened(FARMLAND, state="stalled", timescale="years",
                                    last_movement="2026-01-04",
                                    loops=store.state().loops))
        store.record(Op.ASSERT, "b_1", "2026-08-01T00:00Z", claim="wants land",
                     loop=FARMLAND, **ladder.admitted())
        store.record(Op.ASKED, "qa_1", ago(9), question="q_b_1", about="b_1")
        store.record(Op.ASSERT, "b_in", ago(8), subject="self", claim="mm",
                     **{LEDGER: STATED}, **ladder.admitted())
        first = history(store.log)
        state_before = fold_records(store.log)

    with Store(root) as store:
        again = history(store.log)
        assert fold_records(store.log) == state_before

    assert first == again
    assert first["q_b_1"].answered is True


# ═════════════════════════════════════════════════════════════════════════════
# matrix: the re-ask bound — one of the wanting's OWN periods
# ═════════════════════════════════════════════════════════════════════════════


@pytest.mark.parametrize("scale", list(Timescale), ids=[str(s) for s in Timescale])
def test_the_bound_is_the_wantings_own_period_at_every_timescale(scale):
    """**The sweep.** One question, ignored, measured at each scale's own
    boundary and one second past it.

    Four timescales, four different answers to one question, which is the
    assertion a single global cooldown cannot satisfy — see the case below.
    Both sides of each boundary are pinned, so a bound that drifted a day in
    either direction fails here rather than in a band.
    """
    period = PERIOD_DAYS[scale]

    at_the_boundary = reaskable(
        asked_days_ago(period), period_days=period, now=NOW
    )
    assert at_the_boundary.may_ask is False
    assert at_the_boundary.reason == TOO_SOON
    assert at_the_boundary.period_days == period

    just_past = reaskable(
        asked_days_ago(period + 1.0 / 86_400), period_days=period, now=NOW
    )
    assert just_past.may_ask is True
    assert just_past.reason is None


def test_one_interval_gives_four_different_answers_across_the_four_timescales():
    """**gbrain's single cooldown fails by name here.**

    ``NUDGE_COOLDOWN_DAYS = 14`` is right for a surface whose objects all move
    on one timescale and wrong here in both directions at once: it nags a
    weekly routine — which has been quiet for two of its own periods — and never
    once reaches a farmland loop. So one interval is swept across every scale
    and the answers must *differ*.
    """
    ignored = asked_days_ago(14)
    answers = {
        scale: reaskable(ignored, period_days=PERIOD_DAYS[scale], now=NOW).may_ask
        for scale in Timescale
    }

    assert answers[Timescale.DAYS] is True
    assert answers[Timescale.WEEKS] is True
    assert answers[Timescale.MONTHS] is False
    assert answers[Timescale.YEARS] is False
    assert len(set(answers.values())) == 2, (
        "one interval must not give one answer for every wanting"
    )
    # And the same interval against one shared fourteen-day cadence would give
    # a single answer for all four, which is exactly the shape being refused.
    shared = {reaskable(ignored, period_days=14, now=NOW).may_ask for _ in Timescale}
    assert len(shared) == 1


@pytest.mark.parametrize("days", [0.0, 1.0, 400.0, 10_000.0],
                         ids=["now", "a-day", "a-year", "for-ever"])
def test_a_question_the_main_responded_to_is_never_put_again(days):
    """Matrix: *answered → never asked again*. Swept across elapsed time,
    because a case at one interval would pass for a bound that merely held it
    quiet for a while."""
    answered = history([an_ask(at=ago(days + 1)), a_reply(ago(days))])["q_b_1"]
    bound = reaskable(answered, period_days=1, now=NOW)
    assert bound.may_ask is False
    assert bound.reason == ANSWERED


def test_a_wanting_with_no_readable_period_holds_a_question_already_put():
    """No cadence to hold it to, so nothing here borrows one from a wanting it
    is nothing like. It errs toward asking less, which is this module's one
    direction."""
    bound = reaskable(asked_days_ago(9_999), period_days=None, now=NOW)
    assert bound.may_ask is False
    assert bound.reason == NO_PERIOD
    assert bound.period_days is None


def test_a_now_that_is_not_an_instant_holds_the_question():
    bound = reaskable(asked_days_ago(9_999), period_days=7, now="tomorrow-ish")
    assert bound.may_ask is False and bound.reason == UNREADABLE_NOW


def test_an_ask_stamp_that_cannot_be_read_is_treated_as_no_ask():
    """``touchable``'s own correction, and the same weighing.

    Refusing is the safe-looking direction, and it weighs one extra question
    against *permanent* silence on one uncertainty: the record is replaced only
    by a later ask, a later ask happens only when the question is chosen, and
    refusing here is what would stop it being chosen.
    """
    bound = reaskable(
        Answer(asked=True, asked_at="whenever"), period_days=7, now=NOW
    )
    assert bound.may_ask is True
    assert bound.reason == UNREADABLE_ASK
    assert bound.degraded is True


def test_a_question_stamped_in_the_future_is_not_immediately_askable_again():
    """Clamped, so a skewed stamp cannot buy a question a negative age — the
    same clamp ``silence`` and ``touchable`` apply."""
    ahead = Answer(asked=True, asked_at=stamp(NOON + 30 * DAY))
    bound = reaskable(ahead, period_days=7, now=NOW)
    assert bound.may_ask is False
    assert bound.since_days == 0.0


def test_every_reason_this_module_reports_is_inside_its_closed_set():
    """A caller logging a reason logs a constant and never a message — an
    exception message quotes the value that caused it, and here that is a
    record out of a main's own ledger (AD-22)."""
    seen = {
        reaskable(None, period_days=7, now=NOW).reason,
        reaskable(asked_days_ago(1), period_days=7, now=NOW).reason,
        reaskable(asked_days_ago(9_999), period_days=None, now=NOW).reason,
        reaskable(asked_days_ago(9_999), period_days=7, now="nope").reason,
        reaskable(Answer(asked=True, asked_at="x"), period_days=7, now=NOW).reason,
        history([an_ask(at=ago(2)), a_reply(ago(1))])["q_b_1"] and ANSWERED,
    }
    assert seen <= REASONS


# ═════════════════════════════════════════════════════════════════════════════
# the registry's door: folded from the log, under the mutex
# ═════════════════════════════════════════════════════════════════════════════


def test_the_registrys_ask_history_folds_the_log_and_not_the_derived_view(tmp_path):
    """``Store.append`` writes the line and *then* rebuilds, so a crash between
    the two leaves the derived view behind — and a question read from a stale
    view as never-asked is a question put twice."""
    registry = ActorRegistry(tmp_path)
    try:
        with Store(tmp_path / "vidit") as store:
            store.record(Op.ASKED, "qa_1", ago(3), question="q_b_1", about="b_1")
        answers = asyncio.run(registry.ask_history("vidit"))
        assert answers["q_b_1"].asked is True
        assert answers["q_b_1"].answered is False
        with Store(tmp_path / "vidit") as store:
            store.record(Op.ASSERT, "b_in", ago(1), subject="self", claim="ok",
                         **{LEDGER: STATED}, **ladder.admitted())
        assert asyncio.run(registry.ask_history("vidit"))["q_b_1"].answered is True
    finally:
        registry.close()


def test_the_registry_hands_out_a_copy_of_the_live_strands(tmp_path):
    """Volatile state (AD-26), so a caller cannot move a main's attention by
    writing into what it was handed — and a main this process is not hosting has
    no conversation open, which correctly holds every question."""
    registry = ActorRegistry(tmp_path)
    try:
        assert registry.live_strands("vidit") is None
        asyncio.run(_hydrate(registry, "vidit"))
        live = registry.live_strands("vidit")
        assert live is not None
        live.weights["forged"] = 1.0
        assert "forged" not in registry.live_strands("vidit").weights
    finally:
        registry.close()


async def _hydrate(registry, main_id):
    async with registry.acquire(main_id) as actor:
        actor.strands.observe("farmland", {"farmland"})
