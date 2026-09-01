"""CAP-12 story 6c: coming back — one case per row of the I/O matrix.

Three things this file refuses to do, for the reasons ``tests/test_crisis.py``
gives and one of its own:

**It observes a ceiling in a log, not a return value.** Every row about a
restore is driven through the real runtime, the real registry and the real
store, at a stamp the channel adapter produced — because "aftercare restored a
rung" is only true if it survived the append, the eviction and the rehydration.
The cases that do carry ``cap12_durable`` as well, and CI gates that marker
separately.

**It never lets time be the last condition.** The mirror rows assert the cap
*holding* at least as often as they assert it moving: a suite that only checks
the happy path would pass on a build where thirty days silently restored
everything, which is the exact failure CAP-12 names.

**It moves the clock without owning one.** Every stamp here is computed by the
test and handed in. There is no clock inside ``half/crisis`` to patch, which is
asserted statically as well as relied on — a build where a module under there
imported ``time`` would fail ``tests/test_crisis.py`` before reaching this file.

**A green run here is not clinical review.** The companion's build requirement
6 is a qualified reviewer before launch, and nothing here substitutes for it.
"""

from __future__ import annotations

import asyncio
import ast
import datetime as dt
from pathlib import Path

import pytest

from half.actor.registry import ActorRegistry
from half.actor.runtime import Runtime
from half.channel.port import Inbound
from half.channel.telegram import TelegramChannel
from half.crisis import aftercare, respond, signals, templates
from half.crisis.aftercare import (
    ASK_AGAIN_DAYS,
    DAY,
    FLOOR_DAYS,
    MIRROR_DWELL_DAYS,
    Schedule,
    Standing,
    evaluate,
)
from half.crisis.gate import CrisisGate
from half.errors import StoreError
from half.governance.ladder import TOP, License
from half.store.ops import (
    AFTERCARE_AGREED,
    AFTERCARE_ASKED,
    AFTERCARE_DECLINED,
    Op,
)
from half.store.store import Store
from tests.conftest import FakeTransport, msg

pytestmark = [pytest.mark.cap12, pytest.mark.cap12_aftercare]

ROOT = Path(__file__).resolve().parents[1]

#: The moment the mode opens in every end-to-end case below.
ENTRY_AT = 1_788_256_800   # 2026-09-01T10:00:00Z
ENTRY = "2026-09-01T10:00:00Z"

#: A disclosure that enters, and an ordinary message that does not.
DISCLOSURE = "i want to kill myself"
ORDINARY = "the cat is well and work was fine"


def when(days: float = 0, *, seconds: int = 0, base: str = ENTRY) -> str:
    """``base`` moved by ``days``, as the stamp an adapter would produce."""
    start = dt.datetime.fromisoformat(base.replace("Z", "+00:00"))
    moved = start + dt.timedelta(days=days, seconds=seconds)
    return moved.strftime("%Y-%m-%dT%H:%M:%SZ")


def crisis(state: str = "entered", *, t: str = ENTRY) -> dict:
    """A folded crisis record, as the fold would hand one over."""
    return {"op": "crisis", "id": "cr_1", "t": t, "state": state, "tier": "disclosure"}


def care(state: str, *, t: str) -> dict:
    """A folded aftercare record."""
    return {"op": "aftercare", "id": "ac_1", "t": t, "state": state}


# -- the real thing, end to end ----------------------------------------------


def drive(registry, turns, *, mains=None):
    """Run ``turns`` — ``(text, epoch)`` pairs — through the real runtime.

    One Runtime per turn, so every case also exercises the path a restarted
    worker takes: the gate, the desk, the schedule and the holder are rebuilt
    each time and everything they know comes back out of the log.
    """
    replies: list[str | None] = []
    for index, (text, at) in enumerate(turns):
        transport = FakeTransport([
            msg(text=text, message_id=f"m{index}", chat_id="123", date=at)
        ])
        channel = TelegramChannel(
            transport=transport, mains=mains or {"123": "vidit"}
        )
        asyncio.run(Runtime(channel=channel, registry=channel and registry).run())
        replies.append(transport.sent[-1][1] if transport.sent else None)
    return replies


@pytest.fixture
def mains(tmp_path):
    return tmp_path / "mains"


def rung(root, main_id: str = "vidit") -> License:
    """The cap as a *rehydrated* registry reads it — never the one in memory."""
    fresh = ActorRegistry(root)
    found = fresh.license_ceiling(main_id).rung
    fresh.close()
    return found


def ceilings(root, main_id: str = "vidit") -> list[str]:
    return [r.data.get("rung") for r in Store(root / main_id).log if r.op is Op.CEILING]


def entries(root, main_id: str = "vidit") -> list[str]:
    return [
        r.t for r in Store(root / main_id).log
        if r.op is Op.CRISIS and r.data.get("state") == "entered"
    ]


# =============================================================================
# matrix: inside the floor
# =============================================================================


@pytest.mark.cap12_durable
@pytest.mark.parametrize("day", [0, 1, 3, 14, 29, 29.99])
def test_nothing_restores_inside_the_floor(mains, day):
    """Matrix: inside the floor. *No restore, by any path* — and the parametrized
    days are the point: a build that restored on the twenty-ninth day would
    pass a suite that only tested day three."""
    registry = ActorRegistry(mains)
    drive(registry, [(DISCLOSURE, ENTRY_AT), (ORDINARY, ENTRY_AT + int(day * DAY))])
    registry.close()

    assert rung(mains) is License.BEHAVE, "time alone restored a rung"
    assert ceilings(mains) == ["behave"], (
        "a ceiling record was written inside the floor; nothing may move here"
    )


@pytest.mark.cap12_aftercare_property
def test_the_floor_is_thirty_days_and_changing_it_fails_by_name():
    """The number CAP-12 states, pinned. Changing it is an Ask-First change and
    has to fail mechanically rather than be noticed in review."""
    assert FLOOR_DAYS == 30
    assert MIRROR_DWELL_DAYS == 14
    assert ASK_AGAIN_DAYS == 14


def test_inside_the_floor_the_question_is_not_even_computed():
    """The pure half of the same row: at day twenty-nine there is no step and
    no question, whatever else is true of the log."""
    found = evaluate(crisis(), None, now=when(29))
    assert found.running and found.rung is License.BEHAVE
    assert not found.asks and not found.awaiting


# =============================================================================
# matrix: the floor reached
# =============================================================================


@pytest.mark.cap12_durable
def test_day_thirty_grants_the_first_step_and_only_the_first(mains):
    """Matrix: floor reached. *The first step only* — `behave` to `ask`, never
    a full restore, and the mirror is not granted with it."""
    registry = ActorRegistry(mains)
    drive(registry, [(DISCLOSURE, ENTRY_AT), (ORDINARY, ENTRY_AT + 30 * DAY)])
    registry.close()

    assert rung(mains) is License.ASK
    assert ceilings(mains) == ["behave", "ask"], (
        "the cap went somewhere other than one rung up"
    )


def test_the_first_step_says_nothing_at_all(mains):
    """*Half asks, never announces* — and coming off `behave` is not the thing
    it asks about. A status update about Half's own licence, in a conversation
    that is not about Half, is the announcement the story forbids."""
    registry = ActorRegistry(mains)
    replies = drive(registry, [(DISCLOSURE, ENTRY_AT), (ORDINARY, ENTRY_AT + 30 * DAY)])
    registry.close()

    for line in templates.AFTERCARE_ASK_LINES:
        assert line.text not in (replies[1] or ""), line.id


@pytest.mark.cap12_aftercare_property
def test_the_mirror_is_not_granted_at_the_floor():
    found = evaluate(crisis(), None, now=when(FLOOR_DAYS))
    assert found.rung is License.ASK
    assert not found.asks, "the mirror question has its own dwell"


# =============================================================================
# matrix: the step's own dwell
# =============================================================================


@pytest.mark.cap12_durable
@pytest.mark.parametrize("day", [30, 35, 43, 43.99])
def test_the_second_step_has_its_own_floor(mains, day):
    """Matrix: step dwell. *No further restore* — the step after the first is
    not granted by the first having been granted."""
    registry = ActorRegistry(mains)
    drive(registry, [(DISCLOSURE, ENTRY_AT), (ORDINARY, ENTRY_AT + int(day * DAY))])
    registry.close()

    assert rung(mains) is License.ASK
    assert "assert" not in ceilings(mains)


def test_a_main_who_returns_late_still_takes_the_steps_in_order(mains):
    """A main away for sixty days gets the first step and the question on the
    same turn — and still does not get the mirror, because the mirror needs an
    answer that only a later turn can carry. Late is not a shortcut."""
    registry = ActorRegistry(mains)
    replies = drive(registry, [(DISCLOSURE, ENTRY_AT), (ORDINARY, ENTRY_AT + 60 * DAY)])
    registry.close()

    assert rung(mains) is License.ASK
    assert templates.AFTERCARE_ASK.text in replies[1]


# =============================================================================
# matrix: the mirror step
# =============================================================================


@pytest.mark.cap12_durable
def test_the_mirror_is_asked_for_and_the_cap_holds_until_it_is_answered(mains):
    """Matrix: mirror step. *Half asks; the cap holds until answered* — the
    whole of the story's last condition. Elapsed time can never be the last
    thing that has to be true."""
    registry = ActorRegistry(mains)
    replies = drive(registry, [
        (DISCLOSURE, ENTRY_AT),
        (ORDINARY, ENTRY_AT + 44 * DAY),
    ])
    registry.close()

    for line in templates.AFTERCARE_ASK_LINES:
        assert line.text in replies[1], line.id
    assert rung(mains) is License.ASK, "the mirror resumed without an answer"
    assert ActorRegistry(mains).aftercare_record("vidit")["state"] == AFTERCARE_ASKED


@pytest.mark.cap12_aftercare_property
def test_the_question_carries_the_way_out_of_it():
    """A question a main cannot decline is not a question. The closing line is
    part of the ask by construction — ``templates`` refuses to import without
    it — and it is asserted here as behaviour too."""
    asked = aftercare.question()
    assert templates.AFTERCARE_ASK.text in asked
    assert templates.AFTERCARE_ASK_CLOSE.text in asked
    assert respond.is_templated(asked)


def test_asking_does_not_move_the_cap(mains):
    """Being asked restores nothing. The record says a question was put; the
    ceiling records say nothing happened."""
    registry = ActorRegistry(mains)
    drive(registry, [(DISCLOSURE, ENTRY_AT), (ORDINARY, ENTRY_AT + 44 * DAY)])
    registry.close()
    assert ceilings(mains) == ["behave", "ask"]


# =============================================================================
# matrix: the main agrees
# =============================================================================


@pytest.mark.cap12_durable
@pytest.mark.parametrize(
    "answer",
    ["yes", "yes please", "please do", "go ahead", "sure", "id like that",
     "yeah", "do it", "im ready"],
)
def test_an_affirmative_answer_resumes_the_mirror_and_is_recorded(mains, answer):
    """Matrix: main agrees. *The mirror resumes and the event is recorded* —
    both halves, because a mirror that resumed with no record of anybody
    agreeing is the same product as one that resumed on a timer."""
    registry = ActorRegistry(mains)
    replies = drive(registry, [
        (DISCLOSURE, ENTRY_AT),
        (ORDINARY, ENTRY_AT + 44 * DAY),
        (answer, ENTRY_AT + 44 * DAY + 3600),
    ])
    registry.close()

    assert rung(mains) is TOP
    assert ceilings(mains) == ["behave", "ask", "assert"], (
        "the cap reached the top by some route other than one rung at a time"
    )
    fresh = ActorRegistry(mains)
    assert fresh.aftercare_record("vidit")["state"] == AFTERCARE_AGREED
    fresh.close()
    assert templates.AFTERCARE_AGREED.text in replies[2]


@pytest.mark.cap12_aftercare_property
def test_a_yes_that_nobody_was_asked_restores_nothing(mains):
    """The other side of the same rule. Consent answers a question; a message
    that happens to say yes before Half has asked anything is not an answer,
    and reading it as one is the restore this story exists to prevent."""
    registry = ActorRegistry(mains)
    drive(registry, [
        (DISCLOSURE, ENTRY_AT),
        ("yes please", ENTRY_AT + 31 * DAY),   # past the floor, before the dwell
    ])
    registry.close()

    assert rung(mains) is License.ASK
    assert ActorRegistry(mains).aftercare_record("vidit") is None


# =============================================================================
# matrix: the main declines
# =============================================================================


@pytest.mark.cap12_durable
def test_a_decline_holds_the_cap_and_is_not_for_ever(mains):
    """Matrix: main declines. *Cap holds; Half asks again after a further
    interval* — and the second half is the one that matters. Declining once
    must not mean never being asked again."""
    registry = ActorRegistry(mains)
    replies = drive(registry, [
        (DISCLOSURE, ENTRY_AT),
        (ORDINARY, ENTRY_AT + 44 * DAY),
        ("no, not yet", ENTRY_AT + 44 * DAY + 3600),
        (ORDINARY, ENTRY_AT + 50 * DAY),                    # inside the interval
        (ORDINARY, ENTRY_AT + 44 * DAY + ASK_AGAIN_DAYS * DAY + 3600),
    ])
    registry.close()

    assert templates.AFTERCARE_DECLINED.text in replies[2]
    assert rung(mains) is License.ASK, "a decline moved the cap"

    assert templates.AFTERCARE_ASK.text not in (replies[3] or ""), (
        "Half asked again inside the interval; that is nagging"
    )
    assert templates.AFTERCARE_ASK.text in replies[4], (
        "declining once became never being asked again"
    )


def test_a_vague_affirmative_after_a_decline_is_still_not_consent(mains):
    """A main who says no and then says "yes, that sounds good" about something
    else has not consented to anything. What stops it is the same rule that
    stops it before a decline: consent has to be substantially the whole
    message."""
    registry = ActorRegistry(mains)
    drive(registry, [
        (DISCLOSURE, ENTRY_AT),
        (ORDINARY, ENTRY_AT + 44 * DAY),
        ("no", ENTRY_AT + 44 * DAY + 3600),
        ("yes, that sounds good about the flights", ENTRY_AT + 45 * DAY),
    ])
    registry.close()

    assert rung(mains) is License.ASK
    assert ActorRegistry(mains).aftercare_record("vidit")["state"] == AFTERCARE_DECLINED


@pytest.mark.cap12_durable
def test_a_main_who_changes_their_mind_after_declining_is_heard(mains):
    """*The main always wins.* Somebody who says no on Tuesday and *"yes
    please"* on Wednesday has changed their mind, and a build that held them to
    the withdrawn answer for the next fortnight would be enforcing a decision
    they had already taken back.

    The strictness that matters is what counts as a yes, and that is unchanged:
    the case above still refuses a vague one.
    """
    registry = ActorRegistry(mains)
    replies = drive(registry, [
        (DISCLOSURE, ENTRY_AT),
        (ORDINARY, ENTRY_AT + 44 * DAY),
        ("no, not yet", ENTRY_AT + 44 * DAY + 3600),
        ("yes please", ENTRY_AT + 45 * DAY),
    ])
    registry.close()

    assert templates.AFTERCARE_AGREED.text in replies[3]
    assert rung(mains) is TOP
    assert ceilings(mains) == ["behave", "ask", "assert"]


@pytest.mark.cap12_durable
def test_a_change_of_mind_long_after_the_decline_is_not_heard(mains):
    """And it expires with the question it answers. Past the window there is
    nothing standing to change your mind about, and Half asks again rather than
    reading an old thread's yes."""
    registry = ActorRegistry(mains)
    drive(registry, [
        (DISCLOSURE, ENTRY_AT),
        (ORDINARY, ENTRY_AT + 44 * DAY),
        ("no, not yet", ENTRY_AT + 44 * DAY + 3600),
        ("yes please", ENTRY_AT + (44 + aftercare.ANSWER_WINDOW_DAYS + 1) * DAY),
    ])
    registry.close()
    assert rung(mains) is License.ASK


# =============================================================================
# matrix: no answer
# =============================================================================


@pytest.mark.cap12_durable
def test_silence_is_not_consent(mains):
    """Matrix: no answer. *Cap holds indefinitely.* Any number of turns, none
    of them an answer, and nothing moves."""
    registry = ActorRegistry(mains)
    turns = [(DISCLOSURE, ENTRY_AT), (ORDINARY, ENTRY_AT + 44 * DAY)]
    turns += [(ORDINARY, ENTRY_AT + (45 + n) * DAY) for n in range(30)]
    drive(registry, turns)
    registry.close()

    assert rung(mains) is License.ASK
    assert "assert" not in ceilings(mains)


@pytest.mark.parametrize(
    "answer",
    ["maybe", "i guess so", "kind of", "sort of", "not sure", "if you want",
     "up to you", "i dont know", "perhaps", "whatever"],
)
def test_a_hedge_is_not_consent(answer):
    """The subtlest half of *silence is not consent*. ``is_affirmative`` reads
    a hedge as a yes on purpose, because entering the mode on one is cheap;
    lifting a cap on one is not, so ``reads_as_consent`` reads it as not yet."""
    assert not signals.reads_as_consent(answer), answer


@pytest.mark.parametrize("answer", ["yes", "yeah", "please do", "sure"])
def test_a_clear_yes_is_still_consent(answer):
    """Non-vacuity for the rule above: a strictness that refused everything
    would pass every case in this section and ship a cap nothing lifts."""
    assert signals.reads_as_consent(answer), answer


@pytest.mark.cap12_aftercare_property
def test_the_two_readings_of_yes_disagree_on_purpose():
    """The inversion, asserted rather than described. The same word answers two
    questions whose failures point in opposite directions."""
    assert signals.is_affirmative("maybe")
    assert not signals.reads_as_consent("maybe")


# =============================================================================
# matrix: re-entry
# =============================================================================


@pytest.mark.cap12_durable
def test_a_second_crisis_restarts_the_floor_from_the_later_entry(mains):
    """Matrix: re-entry. *The floor restarts from the later entry, never from
    the first.* Twenty days after a second disclosure is inside the floor even
    though it is fifty days after the first."""
    registry = ActorRegistry(mains)
    drive(registry, [
        (DISCLOSURE, ENTRY_AT),
        (DISCLOSURE, ENTRY_AT + 30 * DAY),          # a second crisis, mid-aftercare
        (ORDINARY, ENTRY_AT + 50 * DAY),            # day 20 of the new floor
    ])
    registry.close()

    assert len(entries(mains)) == 2, "the second disclosure was not an entry"
    assert rung(mains) is License.BEHAVE, "the floor ran from the first entry"


@pytest.mark.cap12_durable
def test_the_new_floor_grants_its_own_first_step_in_time(mains):
    """Non-vacuity for the row above: a build that simply never restored after
    a second entry would pass it. Thirty days after the *second* entry, the
    first step lands."""
    registry = ActorRegistry(mains)
    drive(registry, [
        (DISCLOSURE, ENTRY_AT),
        (DISCLOSURE, ENTRY_AT + 30 * DAY),
        (ORDINARY, ENTRY_AT + 61 * DAY),
    ])
    registry.close()
    assert rung(mains) is License.ASK


@pytest.mark.cap12_durable
def test_a_long_conversation_inside_the_mode_is_still_one_entry(mains):
    """The other half of re-entry, and story 6a's rule unchanged: a held main
    who keeps talking is not disclosing again on every turn, and one record per
    message would be a log full of the same fact."""
    registry = ActorRegistry(mains)
    drive(registry, [
        (DISCLOSURE, ENTRY_AT),
        (ORDINARY, ENTRY_AT + 60),
        (ORDINARY, ENTRY_AT + 120),
        ("thank you for staying", ENTRY_AT + 180),
    ])
    registry.close()
    assert len(entries(mains)) == 1


def test_an_aftercare_record_from_before_the_latest_entry_is_not_this_periods():
    """The pure half. A question asked in July is not an answer about
    September, and the record is ignored rather than deleted — the log is
    append-only and what Half asked in July is still true about July."""
    found = evaluate(
        crisis(t=ENTRY),
        care(AFTERCARE_DECLINED, t=when(-10)),
        now=when(FLOOR_DAYS + MIRROR_DWELL_DAYS),
    )
    assert found.asks, "a stale decline suppressed this period's question"
    assert not found.awaiting


# =============================================================================
# matrix: the evaluation point
# =============================================================================


def test_aftercare_is_evaluated_on_the_mains_own_turn(mains):
    """Matrix: evaluation point. *Aftercare is re-evaluated on that turn* — and
    there is no other trigger, because there is no scheduler here."""
    registry = ActorRegistry(mains)
    drive(registry, [(DISCLOSURE, ENTRY_AT)])
    # Forty-four days pass and the main does not write. Nothing happens: no
    # step, no question, no record.
    assert rung(mains) is License.BEHAVE
    drive(registry, [(ORDINARY, ENTRY_AT + 44 * DAY)])
    registry.close()
    assert rung(mains) is License.ASK


@pytest.mark.cap12_aftercare_property
def test_no_scheduler_and_no_caring_contacts_were_built():
    """The story's Never list, structurally. Caring Contacts need a due-time
    queue (story 9, AD-9) and approximating one with a poll here would be
    building the thing the story defers.
    """
    source = (ROOT / "half/crisis/aftercare.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    called = {
        node.func.attr if isinstance(node.func, ast.Attribute) else
        node.func.id if isinstance(node.func, ast.Name) else ""
        for node in ast.walk(tree) if isinstance(node, ast.Call)
    }
    for forbidden in ("sleep", "create_task", "run_forever", "schedule_at",
                      "every", "cron", "poll"):
        assert forbidden not in called, forbidden
    assert "caring" not in source.casefold().replace("caring contacts", ""), (
        "Caring Contacts are deferred to story 9's due-time queue"
    )


# =============================================================================
# matrix: the operator reversal
# =============================================================================


@pytest.mark.cap12_durable
def test_the_operator_reversal_still_works_and_is_still_recorded(mains):
    """Matrix: operator reversal. *Still works, still recorded, unchanged.*

    And it is deliberately *not* stepwise: a reversal says the entry should
    never have happened, so there is no aftercare period to come back from.
    Stepping a falsely-capped main up one rung at a time over six weeks would
    be applying a safety schedule to somebody who was never in danger.
    """
    registry = ActorRegistry(mains)
    drive(registry, [(DISCLOSURE, ENTRY_AT)])
    asyncio.run(registry.reverse_crisis(
        "vidit", t=when(1), because="entered on a film quote; confirmed"
    ))
    registry.close()

    assert rung(mains) is TOP
    reasons = [
        r.data.get("because") for r in Store(mains / "vidit").log
        if r.op is Op.CRISIS and r.data.get("state") == "reversed"
    ]
    assert reasons == ["entered on a film quote; confirmed"]


def test_a_reversed_entry_leaves_no_aftercare_to_run():
    """The floor runs from an *entry*. A reversal is the statement that there
    was not one, and it has already put the ceiling back itself."""
    found = evaluate(crisis("reversed"), None, now=when(90))
    assert not found.running
    assert not found.asks


@pytest.mark.cap12_durable
def test_aftercare_does_not_re_cap_a_main_whose_entry_was_reversed(mains):
    """The regression this row exists for: aftercare running after a reversal
    would put a falsely-capped main straight back under the schedule."""
    registry = ActorRegistry(mains)
    drive(registry, [(DISCLOSURE, ENTRY_AT)])
    asyncio.run(registry.reverse_crisis("vidit", t=when(1), because="false entry"))
    drive(registry, [(ORDINARY, ENTRY_AT + 44 * DAY)])
    registry.close()
    assert rung(mains) is TOP


# =============================================================================
# matrix: tier
# =============================================================================


@pytest.mark.cap12_aftercare_property
def test_aftercare_reads_no_tier_payment_or_entitlement():
    """Matrix: tier. *Identical behaviour, never gated.* Asserted structurally,
    because no output check proves a value was not consulted: what is checked
    is that aftercare cannot see one."""
    source = (ROOT / "half/crisis/aftercare.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    seen: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Name):
            seen.add(node.id.casefold())
        elif isinstance(node, ast.Attribute):
            seen.add(node.attr.casefold())
        elif isinstance(node, ast.Constant) and isinstance(node.value, str):
            seen.add(node.value.casefold())
    forbidden = {"subscription", "plan_id", "paid", "premium", "billing",
                 "entitlement", "quota", "is_paid", "free", "lapsed"}
    assert not seen & forbidden, sorted(seen & forbidden)


@pytest.mark.cap12_aftercare_property
def test_evaluate_takes_two_records_and_a_stamp_and_nothing_else():
    """The signature *is* the rule. There is no argument through which a tier,
    a payment state, a mood or a recovery judgement could reach the answer."""
    import inspect

    parameters = inspect.signature(evaluate).parameters
    assert list(parameters) == ["crisis", "care", "now"]


# =============================================================================
# matrix: purity and replay
# =============================================================================


def test_the_same_log_and_the_same_now_give_the_same_state():
    """Matrix: purity. *Identical aftercare state, no clock read.*"""
    found = {
        evaluate(crisis(), care(AFTERCARE_ASKED, t=when(44)), now=when(50))
        for _ in range(50)
    }
    assert len(found) == 1


def test_moving_only_now_is_what_changes_the_answer():
    """Non-vacuity for the row above: a function that returned a constant would
    pass it. The stamp is the only moving part, and it moves the answer."""
    assert evaluate(crisis(), None, now=when(3)).rung is License.BEHAVE
    assert evaluate(crisis(), None, now=when(30)).rung is License.ASK


@pytest.mark.cap12_aftercare_property
def test_no_module_here_reads_a_clock():
    """AD-30, and the reason the day arithmetic is written out by hand. The
    package-wide scan in ``tests/test_crisis.py`` already fails on an import of
    ``time`` or ``datetime``; this names the calls as well, so a clock reached
    through an argument fails too."""
    tree = ast.parse((ROOT / "half/crisis/aftercare.py").read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            name = (
                node.func.attr if isinstance(node.func, ast.Attribute)
                else node.func.id if isinstance(node.func, ast.Name) else ""
            )
            assert name not in {
                "now", "utcnow", "today", "time", "monotonic", "perf_counter",
                "fromtimestamp", "timestamp",
            }, f"aftercare reads a clock at line {node.lineno}"


@pytest.mark.cap12_durable
def test_a_log_spanning_entry_steps_and_consent_replays_identically(mains):
    """Matrix: replay. *Licences identical after rebuild* (AD-4). The derived
    view is discarded and the log replayed; the cap, the mode and the answer
    all come back."""
    registry = ActorRegistry(mains)
    drive(registry, [
        (DISCLOSURE, ENTRY_AT),
        (ORDINARY, ENTRY_AT + 30 * DAY),
        (ORDINARY, ENTRY_AT + 44 * DAY),
        ("yes please", ENTRY_AT + 45 * DAY),
    ])
    registry.close()

    before = Store(mains / "vidit").state().canonical_json()
    (mains / "vidit" / "half.db").unlink()
    rebuilt = Store(mains / "vidit")
    assert rebuilt.state().canonical_json() == before
    assert rebuilt.state().aftercare["state"] == AFTERCARE_AGREED
    assert rebuilt.state().ceiling == "assert"
    rebuilt.close()


# =============================================================================
# matrix: reply safety
# =============================================================================


class Exploding:
    """A store that fails at every door aftercare opens."""

    def crisis_record(self, main_id):
        raise StoreError("the log is unreadable")

    def aftercare_record(self, main_id):
        raise StoreError("the log is unreadable")

    def license_ceiling(self, main_id):
        raise StoreError("the log is unreadable")

    async def note_aftercare(self, main_id, *, t, state):
        raise StoreError("the disk is full")

    async def restore_step(self, main_id, *, t, because, note=None):
        raise StoreError("the disk is full")


def test_a_store_failure_while_evaluating_never_costs_the_reply():
    """Matrix: reply safety. *The turn still replies.* Going quiet is one of
    the two documented catastrophic failures, so the set of exceptions worth
    losing a reply over is empty."""
    schedule = Schedule(store=Exploding())
    said = asyncio.run(schedule.evaluate("vidit", now=when(44), text=ORDINARY))
    assert said == ""


def test_a_crisis_turn_still_replies_when_aftercare_explodes():
    """The same failure, observed where it matters: through the gate, on a turn
    that entered the mode."""
    async def pipeline(_inbound):
        return "ordinary"

    gate = CrisisGate(pipeline=pipeline, schedule=Schedule(store=Exploding()))
    reply = asyncio.run(gate.handle(Inbound(
        main_id="vidit", address="123", text=DISCLOSURE,
        external_id="m1", t=when(44),
    )))
    assert reply and respond.is_templated(reply)


# =============================================================================
# the turn Half stays out of
# =============================================================================


class Recording:
    """A store that answers from memory and remembers what it was asked to do."""

    def __init__(self, *, ceiling=License.BEHAVE, care=None, entry=ENTRY):
        self.rung = ceiling
        self.care = care
        self.entry = entry
        self.notes: list[str] = []
        self.steps: list[str] = []
        self.held: list[License] = []

    def crisis_record(self, main_id):
        return crisis(t=self.entry)

    def aftercare_record(self, main_id):
        return self.care

    def license_ceiling(self, main_id):
        from half.governance.ladder import Ceiling

        return Ceiling(self.rung)

    async def note_aftercare(self, main_id, *, t, state):
        self.notes.append(state)

    async def hold_ceiling(self, main_id, *, to, t, because):
        self.held.append(to)
        self.rung = to

    async def restore_step(self, main_id, *, t, because, note=None):
        from half.governance.ladder import next_rung

        if note is not None:
            self.notes.append(note)
        self.rung = next_rung(self.rung) or self.rung
        self.steps.append(str(self.rung))


@pytest.mark.cap12_aftercare_property
def test_a_quiet_turn_still_takes_the_step_and_puts_no_question():
    """A main asking for their safety plan, or telling Half about somebody
    else's danger, is not a main to ask *"shall I start saying what I notice
    about you again?"* — that is answering somebody's subject with Half's own.
    The silent step still lands, because it was never a thing Half says."""
    store = Recording()
    schedule = Schedule(store=store)
    said = asyncio.run(schedule.evaluate(
        "vidit", now=when(44), text=ORDINARY, quiet=True
    ))
    assert said == ""
    assert store.notes == [], "a question was recorded on a turn Half stayed out of"
    assert store.steps == ["ask"], "the silent step was skipped as well"


@pytest.mark.cap12_aftercare_property
def test_a_quiet_turn_does_not_read_the_message_as_an_answer():
    """The other half. A yes typed on a turn that was about something else is
    not consent to a question Half did not just put."""
    store = Recording(ceiling=License.ASK, care=care(AFTERCARE_ASKED, t=when(44)))
    asyncio.run(Schedule(store=store).evaluate(
        "vidit", now=when(45), text="yes please", quiet=True
    ))
    assert store.rung is License.ASK
    assert store.notes == []


@pytest.mark.cap12_aftercare_property
def test_a_cap_above_what_the_floor_permits_is_held_back_down():
    """The self-heal the crisis path used to provide by re-capping on every
    turn — at the price of making every restore last exactly one message. A
    process killed between the entry's two appends leaves a main in the mode
    with no ceiling record; aftercare notices on their next turn."""
    store = Recording(ceiling=TOP)
    asyncio.run(Schedule(store=store).evaluate("vidit", now=when(3), text=ORDINARY))
    assert store.held == [License.BEHAVE]
    assert store.rung is License.BEHAVE


@pytest.mark.cap12_durable
def test_a_held_turn_no_longer_re_caps_a_main_who_was_restored(mains):
    """The regression that made this whole rule necessary: the suspension used
    to re-drop the ceiling on every turn inside the mode, so a restore survived
    exactly until the main wrote again."""
    registry = ActorRegistry(mains)
    drive(registry, [
        (DISCLOSURE, ENTRY_AT),
        (ORDINARY, ENTRY_AT + 30 * DAY),
        (ORDINARY, ENTRY_AT + 31 * DAY),
        (ORDINARY, ENTRY_AT + 32 * DAY),
    ])
    registry.close()
    assert rung(mains) is License.ASK
    assert ceilings(mains) == ["behave", "ask"], (
        "the cap moved on a turn that entered nothing"
    )


@pytest.mark.cap12_aftercare_property
def test_an_ordinary_turn_with_nothing_to_say_is_still_silence():
    """AD-27. Aftercare must not turn silence into a message: a turn with no
    step, no question and no reply stays silent."""
    async def quiet(_inbound):
        return None

    gate = CrisisGate(pipeline=quiet)
    reply = asyncio.run(gate.handle(Inbound(
        main_id="vidit", address="123", text=ORDINARY,
        external_id="m1", t=when(44),
    )))
    assert reply is None


# =============================================================================
# no path restores everything at once (CAP-12)
# =============================================================================


@pytest.mark.cap12_durable
def test_the_registry_refuses_a_restore_of_more_than_one_rung(mains):
    """The failure CAP-12 names, refused at the append rather than avoided by
    the caller. ``release_ceiling`` used to *default* to putting everything
    back."""
    registry = ActorRegistry(mains)
    drive(registry, [(DISCLOSURE, ENTRY_AT)])
    with pytest.raises(StoreError) as excinfo:
        registry.release_ceiling("vidit", to=License.ASSERT, t=when(31),
                                 because="all at once")
    registry.close()
    assert "more than one rung" in str(excinfo.value)
    assert rung(mains) is License.BEHAVE


@pytest.mark.cap12_aftercare_property
def test_release_ceiling_has_no_default_target():
    """A default is not a decision anybody makes. The old signature restored
    everything to `assert` for a caller who passed nothing."""
    import inspect

    parameter = inspect.signature(ActorRegistry.release_ceiling).parameters["to"]
    assert parameter.default is inspect.Parameter.empty


@pytest.mark.cap12_durable
@pytest.mark.cap12_aftercare_property
def test_restore_step_takes_no_target_at_all(mains):
    """The path aftercare actually uses. It cannot be asked for a rung, so
    there is no argument through which a full restore could be requested."""
    import inspect

    assert "to" not in inspect.signature(ActorRegistry.restore_step).parameters

    registry = ActorRegistry(mains)
    drive(registry, [(DISCLOSURE, ENTRY_AT)])
    asyncio.run(registry.restore_step("vidit", t=when(30), because="one step"))
    asyncio.run(registry.restore_step("vidit", t=when(44), because="one step"))
    asyncio.run(registry.restore_step("vidit", t=when(45), because="already there"))
    registry.close()
    assert ceilings(mains) == ["behave", "ask", "assert"]


@pytest.mark.cap12_aftercare_property
def test_no_module_asks_for_a_ceiling_at_the_top():
    """The whole tree, not just this story's files: after 6c there is no call
    anywhere that raises a cap straight to `assert`, except the operator
    reversal, which is not a restore and says so."""
    offenders: list[str] = []
    for path in sorted((ROOT / "half").rglob("*.py")):
        relative = str(path.relative_to(ROOT))
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            name = (
                node.func.attr if isinstance(node.func, ast.Attribute)
                else node.func.id if isinstance(node.func, ast.Name) else ""
            )
            if name not in {"release_ceiling", "restore_step"}:
                continue
            for keyword in node.keywords:
                if keyword.arg == "to":
                    offenders.append(f"{relative}:{node.lineno}")
    assert not offenders, (
        f"a restore names its own target instead of taking one step: {offenders}"
    )


# =============================================================================
# the wording, under 6a's never-list
# =============================================================================


AFTERCARE_LINES = (
    templates.AFTERCARE_OPEN, templates.AFTERCARE_ASK,
    templates.AFTERCARE_ASK_CLOSE, templates.AFTERCARE_AGREED,
    templates.AFTERCARE_DECLINED,
)


@pytest.mark.parametrize("line", AFTERCARE_LINES, ids=lambda line: line.id)
def test_every_aftercare_line_is_in_the_reviewed_corpus(line):
    """A line outside ``templates.LINES`` is a line the golden digest does not
    cover and a clinician did not read."""
    assert line in templates.LINES
    assert line.text in templates.TEXTS


@pytest.mark.parametrize("line", AFTERCARE_LINES, ids=lambda line: line.id)
def test_no_aftercare_line_names_a_duration(line):
    """No digits, like every other template — and here for a second reason: a
    template that counts is wrong the moment the floor moves, and the number is
    not what is being asked about."""
    assert not any(char.isdigit() for char in line.text), line.id


@pytest.mark.cap12_aftercare_property
def test_the_aftercare_question_is_a_question_and_not_an_announcement():
    """*Half asks, never announces.* Resuming the mirror without asking is
    surveillance restarting, which the companion's open question exists to
    avoid."""
    assert templates.AFTERCARE_ASK.text.rstrip().endswith("?")


@pytest.mark.cap12_aftercare_property
def test_nothing_here_says_the_main_is_better():
    """The story's Never list: Half tracks time and consent, never recovery.
    No line claims progress, improvement or healing on the main's behalf."""
    claims = ("better now", "you are doing better", "youre doing better",
              "improved", "recovered", "back to normal", "over it", "healed",
              "stronger now", "proud of you")
    for line in AFTERCARE_LINES:
        lowered = line.text.casefold()
        for claim in claims:
            assert claim not in lowered, f"{line.id}: {claim!r}"


# =============================================================================
# the pure rule, row by row
# =============================================================================


@pytest.mark.parametrize(
    "stamp",
    ["", "not a date", "2026-13-01T00:00:00Z", "2026-09-01", "2026-09-01T25:00Z",
     "2026-09-01T10:00:00+05:30", None, 17, {"t": "2026-09-01T10:00:00Z"}],
)
def test_an_unreadable_stamp_restores_nothing(stamp):
    """Fail-closed, in the one direction that is safe: a stamp this build
    cannot read leaves the main capped rather than restoring on a guess."""
    found = evaluate(crisis(t=ENTRY), None, now=stamp)
    assert found.rung is License.BEHAVE
    assert not found.asks


def test_a_stamp_that_went_backwards_restores_nothing():
    """A clock that ran backwards, or a record out of order. A floor a negative
    number satisfies is not a floor."""
    found = evaluate(crisis(t=when(90)), None, now=ENTRY)
    assert found.rung is License.BEHAVE


def test_a_main_who_never_entered_the_mode_has_no_aftercare():
    assert evaluate(None, None, now=when(90)) == Standing()


@pytest.mark.cap12_aftercare_property
def test_the_day_arithmetic_agrees_with_the_calendar():
    """The hand-written civil-date computation exists because no module under
    ``half/crisis`` may import ``datetime``. It has to agree with one."""
    for stamp in ("2000-02-29T12:34:56Z", "2026-09-01T10:00:00Z",
                  "2100-03-01T00:00:01Z", "2024-12-31T23:59:59Z",
                  "2024-02-29T00:00:00Z", "2200-12-31T23:59:59Z"):
        expected = int(
            dt.datetime.fromisoformat(stamp.replace("Z", "+00:00")).timestamp()
        )
        assert aftercare.instant(stamp) == expected, stamp


@pytest.mark.parametrize(
    "stamp",
    ["2026-02-31T10:00:00Z", "2026-02-29T10:00:00Z", "2026-04-31T10:00:00Z",
     "2026-06-31T10:00:00Z", "2026-13-01T10:00:00Z", "2026-00-10T10:00:00Z",
     "2026-01-00T10:00:00Z", "2026-01-01T10:00:99Z", "2026-01-01T10:60:00Z",
     "2026-01-01T24:00:00Z", "2026-01-01T00:00", "2026-01-01T00:00:00+05:30",
     "0001-01-01T00:00:00Z", "9999-01-01T00:00:00Z", "1970-01-01T00:00:00Z"],
    ids=["feb-31", "feb-29-not-a-leap-year", "april-31", "june-31", "month-13",
         "month-0", "day-0", "second-99", "minute-60", "hour-24", "no-zone",
         "an-offset", "year-1", "year-9999", "before-the-product"],
)
def test_a_stamp_that_is_not_a_real_instant_is_refused(stamp):
    """Matrix: impossible stamp. *Restores nothing* — and the reason is one
    direction: **every** one of these shortens the floor.

    ``2026-02-31`` folded to the third of March and lost three days.
    ``2026-02-29`` is a date in a year that has no such day. ``10:00:99`` is a
    minute that has no such second, while the hour and the minute were
    range-checked beside it. A stamp with no zone was read as UTC while the
    spine's convention promises ``Z``. A year-one record was thirty days past
    its floor on the day it was written.

    The parser is total over every triple — it has to be, it is arithmetic —
    so validating the *date* is not something the arithmetic can do for it.
    """
    assert aftercare.instant(stamp) is None, stamp


def test_a_refused_stamp_restores_nothing_and_asks_nothing():
    """Non-vacuity for the row above, at the level that matters: a refused
    entry stamp leaves the main capped rather than restoring on a guess."""
    for stamp in ("2026-02-31T10:00:00Z", "0001-01-01T00:00:00Z"):
        found = evaluate(crisis(t=stamp), None, now=when(400))
        assert found.rung is License.BEHAVE, stamp
        assert not found.asks, stamp


@pytest.mark.cap12_aftercare_property
def test_a_leap_day_is_a_date_in_a_leap_year_and_not_otherwise():
    from half.governance.aftercare import month_length

    assert month_length(2024, 2) == 29
    assert month_length(2026, 2) == 28
    assert month_length(2100, 2) == 28, "the hundred-year rule"
    assert month_length(2000, 2) == 29, "the four-hundred-year rule"


def test_seconds_are_optional_in_a_stored_stamp():
    """The log holds both shapes — ``2026-07-04T08:00Z`` and
    ``2026-09-01T22:14:00Z`` — and a floor that only understood one of them
    would silently never restore for half the logs there are."""
    assert aftercare.instant("2026-07-04T08:00Z") == aftercare.instant(
        "2026-07-04T08:00:00Z"
    )


# =============================================================================
# review round 1: consent is the whole message, and a refusal in it wins
# =============================================================================


@pytest.mark.parametrize(
    "answer",
    ["yes, but please dont", "yes but not the mirror stuff", "yes, later",
     "yeah but not yet", "sure, but please do not", "yes — id rather not"],
)
def test_an_affirmation_with_a_refusal_in_it_is_a_refusal(answer):
    """Matrix: refusal containing yes. *A refusal anywhere wins.*

    Every one of these resumed the mirror before this rule existed, because the
    matcher looked for a consent phrase at any index and examined nothing after
    it. Several of them contain no "no" at all, which is why the refusal table
    is written in the words people actually use.
    """
    assert not signals.reads_as_consent(answer), answer
    assert signals.reads_as_refusal(answer), answer


@pytest.mark.parametrize(
    "answer",
    ["sure, I picked up the milk", "im ready to go to bed",
     "yes I went to the shops", "yeah the train was late again",
     "do it yourself, the tap I mean", "yep the cat knocked it over"],
)
def test_an_affirmation_in_passing_is_not_an_answer(answer):
    """Matrix: affirmation in passing. *Consent is the whole message.*

    Not a refusal either — these answer nothing, so the question stays standing
    and the cap stays where it is, which is what "not an answer" has to mean.
    """
    assert not signals.reads_as_consent(answer), answer


@pytest.mark.parametrize(
    "answer",
    ["yes", "yes please", "yeah", "sure", "go ahead", "please do",
     "yes id like that", "yep do it"],
)
def test_a_clear_answer_is_still_read_as_one(answer):
    """Non-vacuity: a rule strict enough to refuse everything would pass every
    case above and ship a cap that nothing lifts."""
    assert signals.reads_as_consent(answer), answer


def test_ordinary_conversation_is_never_read_as_an_answer():
    """The other direction of the bound. A message about a cat contains *but*;
    it is not a refusal, because a contradiction counts only beside a yes."""
    for text in ("the cat is well but tired", "work was fine although long",
                 "i went out, not far, just the shops"):
        assert not signals.reads_as_refusal(text), text
        assert not signals.reads_as_consent(text), text


@pytest.mark.cap12_durable
def test_a_refusal_containing_yes_does_not_resume_the_mirror(mains):
    """The same rule where it is load-bearing: through the real gate, the real
    registry and the real log."""
    registry = ActorRegistry(mains)
    replies = drive(registry, [
        (DISCLOSURE, ENTRY_AT),
        (ORDINARY, ENTRY_AT + 44 * DAY),
        ("yes, but please dont", ENTRY_AT + 44 * DAY + 3600),
    ])
    registry.close()

    assert rung(mains) is License.ASK, "a refusal resumed the mirror"
    assert templates.AFTERCARE_DECLINED.text in replies[2]
    assert ActorRegistry(mains).aftercare_record("vidit")["state"] == AFTERCARE_DECLINED


# =============================================================================
# review round 1: a standing question expires
# =============================================================================


@pytest.mark.cap12_durable
def test_an_affirmative_long_after_the_question_is_not_its_answer(mains):
    """Matrix: stale question. *Questions expire.*

    A question that never expired made every later affirmative its answer, so a
    main who said "yes" to something else a month on resumed the mirror without
    ever having answered.
    """
    registry = ActorRegistry(mains)
    drive(registry, [
        (DISCLOSURE, ENTRY_AT),
        (ORDINARY, ENTRY_AT + 44 * DAY),
        ("yes", ENTRY_AT + (44 + aftercare.ANSWER_WINDOW_DAYS + 1) * DAY),
    ])
    registry.close()
    assert rung(mains) is License.ASK


@pytest.mark.cap12_aftercare_property
def test_the_answer_window_is_shorter_than_the_interval_before_asking_again():
    """Deliberate, and the ordering is the point: a question stops being
    answerable before Half puts it again, so there is never a moment when two
    different askings are both live."""
    assert aftercare.ANSWER_WINDOW_DAYS < aftercare.ASK_AGAIN_DAYS


def test_an_unreadable_or_future_stamp_on_the_question_expires_it():
    """The safe direction for the one field that can lift a cap. A question
    whose age cannot be computed is stale rather than answerable — and a record
    stamped in the future is not a question asked a moment ago."""
    stale = evaluate(crisis(), care(AFTERCARE_ASKED, t="not a date"),
                     now=when(44))
    assert not stale.awaiting
    ahead = evaluate(crisis(), care(AFTERCARE_ASKED, t=when(90)), now=when(44))
    assert not ahead.awaiting


def test_a_future_dated_question_does_not_suppress_the_next_one():
    """The mirror of the row above: `elapsed` goes negative, and a comparison
    written the obvious way would read that as "no time has passed" and hold
    the question for ever."""
    ahead = evaluate(crisis(), care(AFTERCARE_ASKED, t=when(90)), now=when(44))
    assert ahead.asks, "a future-dated record silenced the question"


# =============================================================================
# review round 1: the hedge is an answer
# =============================================================================


@pytest.mark.cap12_durable
@pytest.mark.parametrize("answer", ["maybe", "i guess", "not sure", "up to you"])
def test_a_hedge_holds_the_cap_and_is_acknowledged(mains, answer):
    """A hedge is not consent and it is not nothing. The main replied, so Half
    answers them and asks again on the ordinary interval rather than sitting on
    a question they have already responded to."""
    registry = ActorRegistry(mains)
    replies = drive(registry, [
        (DISCLOSURE, ENTRY_AT),
        (ORDINARY, ENTRY_AT + 44 * DAY),
        (answer, ENTRY_AT + 44 * DAY + 3600),
    ])
    registry.close()

    assert rung(mains) is License.ASK
    assert templates.AFTERCARE_DECLINED.text in replies[2]
    assert ActorRegistry(mains).aftercare_record("vidit")["state"] == AFTERCARE_DECLINED


# =============================================================================
# matrix: stop asking
# =============================================================================


@pytest.mark.cap12_durable
def test_a_main_who_asks_not_to_be_asked_is_not_asked_again(mains):
    """Matrix: stop asking. *The question stops; the cap holds.*

    Declining is not permanent — Half asks again after an interval — but asking
    is not perpetual either, and being asked every fortnight for the rest of
    your life about the worst night of it is not care.
    """
    registry = ActorRegistry(mains)
    replies = drive(registry, [
        (DISCLOSURE, ENTRY_AT),
        (ORDINARY, ENTRY_AT + 44 * DAY),
        ("no, and please stop asking", ENTRY_AT + 44 * DAY + 3600),
    ])
    registry.close()

    assert templates.AFTERCARE_STOPPED.text in replies[2]
    assert ActorRegistry(mains).aftercare_record("vidit")["state"] == "stopped"

    registry = ActorRegistry(mains)
    later = drive(registry, [
        (ORDINARY, ENTRY_AT + 60 * DAY),
        (ORDINARY, ENTRY_AT + 200 * DAY),
        (ORDINARY, ENTRY_AT + 900 * DAY),
    ])
    registry.close()
    for reply in later:
        assert templates.AFTERCARE_ASK.text not in (reply or "")
    assert rung(mains) is License.ASK, "stopping the question moved the cap"


@pytest.mark.parametrize(
    "text",
    ["stop asking", "please stop asking", "dont ask me again",
     "never ask me again", "quit asking"],
)
def test_a_request_to_stop_is_recognised(text):
    assert signals.asks_to_stop(text)


def test_ordinary_talk_is_not_a_request_to_stop():
    for text in ("stop the car", "i asked her about it", "dont ask me why"):
        assert not signals.asks_to_stop(text), text


# =============================================================================
# review round 1: the floor is enforced where a cap is actually raised
# =============================================================================


@pytest.mark.cap12_durable
@pytest.mark.parametrize("day", [0, 2, 15, 29])
def test_the_write_path_refuses_a_restore_inside_the_floor(mains, day):
    """Matrix: floor at the write path. *Refused there too.*

    The floor used to live only in the pure function that *decides* a step,
    while ``restore_step`` — the write path a future caller reaches for —
    checked one-rung-ness and nothing else. Two calls dated two days after an
    entry took a main from `behave` to `assert`. A rule that lives in one
    function is not an invariant; it is a convention that function follows.
    """
    registry = ActorRegistry(mains)
    drive(registry, [(DISCLOSURE, ENTRY_AT)])
    with pytest.raises(StoreError) as excinfo:
        asyncio.run(registry.restore_step("vidit", t=when(day), because="early"))
    registry.close()

    assert "floor" in str(excinfo.value)
    assert rung(mains) is License.BEHAVE


@pytest.mark.cap12_durable
def test_two_calls_inside_the_floor_cannot_walk_the_cap_to_the_top(mains):
    """The exact reproduction: two `restore_step` calls two days after entry
    raised `behave` to `assert` with every gate green."""
    registry = ActorRegistry(mains)
    drive(registry, [(DISCLOSURE, ENTRY_AT)])
    for _ in range(2):
        with pytest.raises(StoreError):
            asyncio.run(registry.restore_step("vidit", t=when(2), because="x"))
    registry.close()
    assert rung(mains) is License.BEHAVE
    assert ceilings(mains) == ["behave"]


@pytest.mark.cap12_durable
def test_a_restore_with_no_crisis_to_come_back_from_is_refused(mains):
    """Aftercare restores what a crisis capped. A caller raising a ceiling on a
    main who was never in the mode is doing something else, and it has its own
    path."""
    root = mains
    (root / "vidit").mkdir(parents=True)
    registry = ActorRegistry(root)
    with pytest.raises(StoreError) as excinfo:
        asyncio.run(registry.restore_step("vidit", t=when(90), because="why"))
    registry.close()
    assert "no crisis entry" in str(excinfo.value)


@pytest.mark.cap12_durable
def test_a_consent_record_with_no_question_before_it_is_refused(mains):
    """An ``agreed`` has to answer an ``asked`` in the same period. That is
    what the aftercare op was added to make unforgeable — a consent record
    nobody was asked for is a mirror resumed on a record Half wrote itself."""
    registry = ActorRegistry(mains)
    drive(registry, [(DISCLOSURE, ENTRY_AT), (ORDINARY, ENTRY_AT + 30 * DAY)])
    with pytest.raises(StoreError) as excinfo:
        asyncio.run(registry.restore_step(
            "vidit", t=when(45), because="mirror", note=AFTERCARE_AGREED
        ))
    registry.close()
    assert "answer a question" in str(excinfo.value)
    assert rung(mains) is License.ASK


@pytest.mark.cap12_durable
def test_a_consent_record_after_a_question_is_accepted(mains):
    """Non-vacuity for the rule above."""
    registry = ActorRegistry(mains)
    drive(registry, [
        (DISCLOSURE, ENTRY_AT),
        (ORDINARY, ENTRY_AT + 44 * DAY),      # the question is put here
    ])
    asyncio.run(registry.restore_step(
        "vidit", t=when(45), because="mirror", note=AFTERCARE_AGREED
    ))
    registry.close()
    assert rung(mains) is TOP


# =============================================================================
# review round 1: aftercare ends, and the self-heal is real
# =============================================================================


@pytest.mark.cap12_durable
def test_aftercare_stops_running_once_the_mirror_is_back(mains):
    """*Aftercare terminates.* Once the main has asked for the mirror and got
    it, the period is over — nothing steps, holds or asks again, so a cap an
    operator sets afterwards for an unrelated reason is not walked back by a
    schedule that outlived its purpose."""
    registry = ActorRegistry(mains)
    drive(registry, [
        (DISCLOSURE, ENTRY_AT),
        (ORDINARY, ENTRY_AT + 44 * DAY),
        ("yes please", ENTRY_AT + 45 * DAY),
    ])
    assert rung(mains) is TOP

    registry.lower_ceiling("vidit", License.BEHAVE, t=when(60),
                           because="an unrelated safety concern")
    registry.close()

    registry = ActorRegistry(mains)
    drive(registry, [
        (ORDINARY, ENTRY_AT + 61 * DAY),
        (ORDINARY, ENTRY_AT + 62 * DAY),
        (ORDINARY, ENTRY_AT + 90 * DAY),
    ])
    registry.close()

    assert rung(mains) is License.BEHAVE, (
        "a finished aftercare walked an operator's deliberate cap back up"
    )


@pytest.mark.cap12_aftercare_property
def test_a_finished_period_is_not_running():
    found = evaluate(crisis(), care(AFTERCARE_AGREED, t=when(45)), now=when(400))
    assert not found.running


@pytest.mark.cap12_durable
def test_a_main_in_the_mode_with_no_ceiling_record_is_capped_on_their_next_turn(
    mains,
):
    """Matrix: lost ceiling append. *The next turn caps them.*

    The self-heal that replaced the removed re-cap in ``suspend_for_crisis`` —
    exercised here through the **real registry**, because its only previous
    test drove a stub's own three-line method and would have passed with
    ``hold_ceiling``'s body deleted.

    The state is the one a process killed between the entry's two appends
    leaves behind: a crisis record in the log and no ceiling record at all.
    """
    root = mains
    with Store(root / "vidit") as store:
        store.record(Op.CRISIS, "cr_vidit_1", ENTRY, state="entered",
                     tier="disclosure", score=1)
    assert Store(root / "vidit").state().ceiling is None

    registry = ActorRegistry(root)
    assert registry.license_ceiling("vidit").rung is TOP, "the setup is wrong"
    drive(registry, [(ORDINARY, ENTRY_AT + 3 * DAY)])
    registry.close()

    assert rung(mains) is License.BEHAVE, (
        "an uncapped main in the mode stayed uncapped"
    )
    assert ceilings(mains) == ["behave"]


@pytest.mark.cap12_durable
def test_the_self_heal_never_lifts_a_cap_it_finds(mains):
    """Non-vacuity in the other direction: holding down is not a licence to
    raise. A main inside the floor is held at `behave`, never moved up."""
    registry = ActorRegistry(mains)
    drive(registry, [(DISCLOSURE, ENTRY_AT), (ORDINARY, ENTRY_AT + 3 * DAY)])
    registry.close()
    assert ceilings(mains) == ["behave"]


# =============================================================================
# review round 1: the derived view must not silently lose an answer
# =============================================================================


@pytest.mark.cap12_durable
def test_a_derived_view_written_before_aftercare_existed_is_discarded(mains):
    """Matrix: upgraded view. *Discarded and replayed; a decline survives.*

    Both schema bumps could be reverted with the suite green. A pre-6c derived
    view has no aftercare row, so a recorded **decline** folds to ``None`` on
    upgrade — and the next turn is then free to read a later yes as the answer
    to a question the main already refused.
    """
    import sqlite3

    from half.store import db

    registry = ActorRegistry(mains)
    drive(registry, [
        (DISCLOSURE, ENTRY_AT),
        (ORDINARY, ENTRY_AT + 44 * DAY),
        ("no, not yet", ENTRY_AT + 45 * DAY),
    ])
    registry.close()
    assert Store(mains / "vidit").state().aftercare["state"] == AFTERCARE_DECLINED

    # An older build's view: the governance row for aftercare simply absent,
    # and the version stamped as the one that predates it.
    conn = sqlite3.connect(mains / "vidit" / "half.db")
    conn.execute("DELETE FROM governance WHERE key = 'aftercare'")
    # Stamped with the literal version that predates aftercare, not with
    # ``DERIVED_VERSION - 1``. The relative form passes whatever
    # ``DERIVED_VERSION`` happens to be, so reverting the bump left this green;
    # the literal makes a revert land here as well as on the pin below.
    conn.execute("PRAGMA user_version = 5")
    conn.commit()
    conn.close()

    reopened = Store(mains / "vidit")
    assert reopened.state().aftercare is not None, (
        "the stale view was trusted and the main's answer disappeared"
    )
    assert reopened.state().aftercare["state"] == AFTERCARE_DECLINED
    reopened.close()


@pytest.mark.cap12_aftercare_property
def test_the_derived_version_moved_when_the_view_gained_a_row():
    """The bump itself, pinned. A view that gained a column without one is a
    view an older build reads as complete."""
    from half.store import db
    from half.store.ops import SCHEMA_VERSION

    assert db.DERIVED_VERSION >= 6, (
        "the derived view gained the aftercare row in story 6c"
    )
    assert SCHEMA_VERSION >= 4, "the log gained the aftercare op in story 6c"


@pytest.mark.cap12_durable
def test_a_recorded_decline_survives_a_full_replay(mains):
    """The log is the authority. Deleting the derived view entirely and
    replaying reproduces the answer the main gave."""
    registry = ActorRegistry(mains)
    drive(registry, [
        (DISCLOSURE, ENTRY_AT),
        (ORDINARY, ENTRY_AT + 44 * DAY),
        ("no, not yet", ENTRY_AT + 45 * DAY),
    ])
    registry.close()

    (mains / "vidit" / "half.db").unlink()
    rebuilt = Store(mains / "vidit")
    assert rebuilt.state().aftercare["state"] == AFTERCARE_DECLINED
    rebuilt.close()


# =============================================================================
# review round 1: the quiet turns, observed on the wire
# =============================================================================


@pytest.mark.cap12_durable
def test_the_question_is_not_put_underneath_the_mains_own_safety_plan(mains):
    """Observed on the reply rather than on a stub. The previous version of
    this rule could be deleted with the suite green, and the behaviour it
    prevents is Half appending *"would you like me to start saying what I
    notice about you again?"* under somebody's own safety plan."""
    from half.crisis import safetyplan

    with Store(mains / "vidit") as store:
        store.record(Op.ASSERT, "p_1", "2026-08-01T00:00Z",
                     **safetyplan.held_fields(["Ring Asha. She knows."]))
    registry = ActorRegistry(mains)
    replies = drive(registry, [
        (DISCLOSURE, ENTRY_AT),
        ("can you show me my safety plan", ENTRY_AT + 44 * DAY),
    ])
    registry.close()

    assert "Ring Asha. She knows." in replies[1]
    for line in templates.AFTERCARE_ASK_LINES:
        assert line.text not in replies[1], line.id
    assert ActorRegistry(mains).aftercare_record("vidit") is None, (
        "a question was recorded on a turn the main asked about their plan"
    )


@pytest.mark.cap12_durable
def test_the_silent_step_still_lands_on_a_plan_turn(mains):
    """The other half: quiet suppresses the *question*, never the step. The
    step was never a thing Half says."""
    from half.crisis import safetyplan

    with Store(mains / "vidit") as store:
        store.record(Op.ASSERT, "p_1", "2026-08-01T00:00Z",
                     **safetyplan.held_fields(["Ring Asha."]))
    registry = ActorRegistry(mains)
    drive(registry, [
        (DISCLOSURE, ENTRY_AT),
        ("show me my safety plan", ENTRY_AT + 31 * DAY),
    ])
    registry.close()
    assert rung(mains) is License.ASK


@pytest.mark.cap12_aftercare_property
def test_two_aftercare_records_in_one_minute_are_two_records():
    """Stored stamps are minute-resolution, so a question put and answered
    inside one minute used to be two log lines with one id. The fold's
    last-write-wins happened to keep the right one, but a log where two
    different facts share an identifier is a log that cannot be read back."""
    from half.actor.registry import _note_aftercare

    class Recorder:
        main_id = "vidit"

        def __init__(self):
            self.written = []

        class store:  # noqa: N801 - a stand-in, not a class of its own
            pass

    recorder = Recorder()
    written: list[tuple] = []
    recorder.store = type("S", (), {
        "record": lambda self, op, ident, t, **fields: written.append((ident, fields))
    })()
    _note_aftercare(recorder, t=ENTRY, state=AFTERCARE_ASKED)
    _note_aftercare(recorder, t=ENTRY, state=AFTERCARE_DECLINED)
    assert len({ident for ident, _ in written}) == 2, written


@pytest.mark.cap12_durable
def test_an_answer_in_the_same_minute_as_the_question_is_the_last_word(mains):
    """And the fold still reads the later fact as the current one."""
    registry = ActorRegistry(mains)
    drive(registry, [
        (DISCLOSURE, ENTRY_AT),
        (ORDINARY, ENTRY_AT + 44 * DAY),
        ("no", ENTRY_AT + 44 * DAY + 5),      # the same minute as the question
    ])
    registry.close()
    assert Store(mains / "vidit").state().aftercare["state"] == AFTERCARE_DECLINED


@pytest.mark.cap12_durable
def test_a_consent_record_after_a_stop_request_is_still_refused(mains):
    """A main who asked not to be asked is not answering anything. ``stopped``
    is not evidence that a question is standing, so a consent record after one
    is refused like a consent record after nothing at all."""
    registry = ActorRegistry(mains)
    drive(registry, [
        (DISCLOSURE, ENTRY_AT),
        (ORDINARY, ENTRY_AT + 44 * DAY),
        ("please stop asking", ENTRY_AT + 44 * DAY + 3600),
    ])
    with pytest.raises(StoreError):
        asyncio.run(registry.restore_step(
            "vidit", t=when(46), because="mirror", note=AFTERCARE_AGREED
        ))
    registry.close()
    assert rung(mains) is License.ASK
