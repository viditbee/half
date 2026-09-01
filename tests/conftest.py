from __future__ import annotations

import pytest

from half.crisis import safetyplan
from half.governance import ladder
from half.governance.ladder import License
from half.store.ops import Op
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
        s.record(Op.LOOP_TRANSITION, "l_1", "2026-08-03T02:41Z",
                 loop="buy-farmland", state="stalled", timescale="years",
                 last_movement="2026-03-12")
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
