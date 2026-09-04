"""CAP-10 story 5d: the unsaid queue — what is held, and what would release it.

``tests/test_ladder.py`` carries the rung rules and the ceiling; this file
carries the queue that reports what those rules are holding back.

**The queue is asked of the ladder, so the cases are written against the
ladder.** Every release condition here is checked twice: once that it is
*named* for a belief missing it, and once that satisfying it — through
``ladder.promote`` or through a real ``release_ceiling``, never by editing a
field by hand — actually takes the item out of the queue. A condition that is
reported and does not release is the *"false hope"* this story exists to
prevent, and a condition that releases and is not reported is the silent
withholding it replaces.

**What this build cannot seed, and why the cases say so.** The ladder holds the
write monopoly on ``license``, ``support`` and ``known_to_main``, and
``promote`` is the only path to `assert` — so a belief *this build wrote* can
never sit at `assert` missing a precondition. The acknowledgement and receipt
rows therefore describe records this build did not write: an earlier schema,
another build, a hand-written line. Those cases are built as belief mappings
rather than seeded through a ``Store``, deliberately and not for convenience —
``tests/test_ladder.py``'s writer gate forbids spelling a governed field into a
record outside ``half/governance/`` and ``tests/conftest.py``, and walking round
it here would be this suite demonstrating the bypass it is meant to close. The
condition reachable through the product's own doors today is the **ceiling**,
and every ceiling case here runs end to end over a real log.

**Nothing here reads a clock.** The queue is a function of the log and nothing
else, so it changes when the log changes and at no other moment (AD-30).

**Two markers, disjoint, and applied case by case.** ``cap10_unsaid`` is the
behaviour; ``cap10_unsaid_structure`` is the single-case structural rules the
queue rests on. Every case carries exactly one of them and there is no module
``pytestmark``: a file-wide mark makes a gate's count the *file's* count, which
is how the AD-28 gate once selected every rung and quarantine case in
``tests/test_ladder.py`` while every ceiling case could have been deleted under
it. Disjoint rather than superset-and-subset for the reason this repository has
had to demonstrate three times — a floor on a superset cannot protect a handful
of cases inside it, so a superset here would be a floor claiming protection it
does not have.
"""

from __future__ import annotations

import ast
import asyncio
import dataclasses
from pathlib import Path
from typing import Final

import pytest

from half.actor.registry import ActorRegistry
from half.governance import ladder
from half.governance.ladder import RUNGS, Ceiling, License
from half.governance.unsaid import (
    ACKNOWLEDGEMENT,
    CEILING,
    CONDITIONS,
    RECEIPT,
    UNCAPPED,
    VISIBLE,
    Unsaid,
    UnsaidView,
    depth,
    depths,
    missing,
    narrowed_for_unsaid,
    queue,
    view_fields,
    waiting_on,
)
from half.store.fold import State
from half.store.ops import Op
from half.store.store import Store

from tests.conftest import CLOSED, UNREACHABLE, resolved_imports

ROOT = Path(__file__).resolve().parents[1]

MAIN: Final[str] = "vidit"
T: Final[str] = "2026-09-01T00:00:00Z"
CLAIM: Final[str] = "wants to buy farmland before the monsoon"


# ── helpers ──────────────────────────────────────────────────────────────────


def belief(**fields):
    """One belief record, as a mapping.

    The license fields are spelled here because these are the shapes a log
    written by another build carries — see this module's docstring. Nothing in
    this file writes one into a ``Store``.
    """
    record = {"id": "b_1", "claim": CLAIM, "topics": ["farmland"]}
    record.update(fields)
    return record


#: The four shapes the ladder's `assert` preconditions produce, by name.
UNACKNOWLEDGED = belief(license="assert", support=["s_1"])
UNCITED = belief(license="assert", known_to_main=True)
NEITHER = belief(license="assert")
SAYABLE = belief(license="assert", support=["s_1"], known_to_main=True)


def a_view(*beliefs, ceiling=None):
    """A view over ``beliefs``, keyed by their ids, under ``ceiling``."""
    return UnsaidView(
        beliefs={record["id"]: record for record in beliefs},
        ceiling=Ceiling(License.ASSERT if ceiling is None else ceiling),
    )


def only(items):
    """The one item in ``items``, or a failure naming what was there instead."""
    assert len(items) == 1, [item.belief_id for item in items]
    return items[0]


def seed(root, *, main_id=MAIN, rung=License.ASSERT, ident="b_1", claim=CLAIM):
    """One main holding one belief at ``rung``, seeded through the ladder.

    `assert` is a rung a belief *earns*: it is admitted at the floor with a
    receipt and promoted with an acknowledgement, which is the only path there
    is. Nothing here spells a license field.
    """
    with Store(root / main_id) as store:
        store.record(
            Op.ASSERT, ident, T, claim=claim, topics=["farmland"],
            **ladder.admitted(support=["s_1"]),
        )
        if rung is not License.BEHAVE:
            record = store.state().beliefs[ident]
            store.record(
                Op.ASSERT, ident, T,
                **ladder.promote(record, to=rung, acknowledged=True),
            )


def held(registry, main_id=MAIN):
    """This main's queue, read through the registry's one door."""
    return queue(asyncio.run(registry.unsaid_view(main_id)))


def log_bytes(root, main_id=MAIN):
    """Every byte of this main's **log**, for a before-and-after comparison.

    The shards and nothing else. The log is the authority (AD-3); ``half.db`` is
    the derived view beside it and its bytes move when SQLite checkpoints on
    close, which is not a write anybody made. The derived file is still compared
    — inside the process, where a checkpoint has not happened — by
    ``directory_bytes`` below, so nothing is exempt from the claim, only from
    the part of it a close would make meaningless.
    """
    return sorted(
        (path.name, path.read_bytes())
        for path in sorted((root / main_id).rglob("*.jsonl"))
    )


def directory_bytes(root, main_id=MAIN):
    """Every byte of everything under this main's directory, derived included."""
    return sorted(
        (path.name, path.read_bytes())
        for path in sorted((root / main_id).rglob("*"))
        if path.is_file()
    )


# ═════════════════════════════════════════════════════════════════════════════
# matrix: waiting on the main / on a receipt / on both
# ═════════════════════════════════════════════════════════════════════════════


@pytest.mark.cap10_unsaid
def test_a_belief_the_main_has_not_been_told_is_queued_on_the_acknowledgement():
    """Matrix: waiting on the main.

    A belief that would be `assert` and cites its evidence, which the main has
    never heard Half think. *"The danger of assertion is being unexpected, not
    being wrong"* — so the ladder holds it at `ask`, and the queue names the one
    thing that would release it.
    """
    item = only(queue(a_view(UNACKNOWLEDGED)))
    assert item.belief_id == "b_1"
    assert item.conditions == (ACKNOWLEDGEMENT,)
    assert item.rung is License.ASK
    assert item.would_reach is License.ASSERT


@pytest.mark.cap10_unsaid
def test_a_belief_that_cites_nothing_is_queued_on_the_receipt():
    """Matrix: waiting on a receipt. *"An unsupported claim may be asked, never
    asserted"* — the main knows Half holds it, and Half cannot show why."""
    item = only(queue(a_view(UNCITED)))
    assert item.conditions == (RECEIPT,)
    assert item.rung is License.ASK


@pytest.mark.cap10_unsaid
def test_a_belief_neither_acknowledged_nor_cited_names_both_and_not_the_first():
    """Matrix: waiting on both. **Separable reasons.**

    The two preconditions are independent and fail independently, so a queue
    that reported the first refusal it found would tell an operator to go and
    get an acknowledgement for a claim that would still be refused after they
    did.
    """
    item = only(queue(a_view(NEITHER)))
    assert item.conditions == (ACKNOWLEDGEMENT, RECEIPT)


@pytest.mark.cap10_unsaid
def test_asking_whether_one_repair_helps_would_miss_the_conjunctive_case():
    """**Non-vacuity for the probe's shape**, which is the case that decided it.

    The obvious probe is *"does this one repair raise the belief?"*, asked of
    each condition alone. It is right for a belief missing one precondition and
    silently wrong for a belief missing two: `assert` wants a receipt **and** an
    acknowledgement, so neither repair alone lifts anything and the naive probe
    reports an empty queue for the belief that is held hardest.

    Written out here against the same ladder the shipped probe asks, so the
    difference is a property of the rule rather than a claim in a docstring.
    """
    from half.governance.unsaid import _rung  # the shipped one-door helper

    naive = tuple(
        name
        for name, repair in (
            (ACKNOWLEDGEMENT, {"known_to_main": True}),
            (RECEIPT, {"support": ["s_1"]}),
        )
        if _rung({**NEITHER, **repair}, UNCAPPED) is not _rung(NEITHER, UNCAPPED)
    )
    assert naive == (), "the naive probe changed; this case no longer proves it"
    assert missing(NEITHER, ceiling=UNCAPPED) == (ACKNOWLEDGEMENT, RECEIPT)


# ═════════════════════════════════════════════════════════════════════════════
# matrix: quarantined — never an item, and never a false hope
# ═════════════════════════════════════════════════════════════════════════════


@pytest.mark.cap10_unsaid
@pytest.mark.parametrize(
    "record",
    [
        belief(license="behave", quarantined=True),
        belief(license="assert", support=["s_1"], known_to_main=True,
               quarantined=True),
        belief(license="ask", quarantined=True),
    ],
    ids=["pinned", "pinned-with-a-stale-assert-field", "pinned-at-ask"],
)
@pytest.mark.parametrize("rung", RUNGS, ids=[str(r) for r in RUNGS])
def test_a_quarantined_belief_is_never_an_item(record, rung):
    """Matrix: quarantined. **Never a false hope.**

    The pin is permanent and no path lifts it, so a quarantined belief is not
    *waiting* for anything. Listing it with a condition that could be met would
    suggest something releases it, and the one thing worse than a silent
    withholding is a queue that lies about what is waiting.

    Swept over every ceiling, because the ceiling is the one condition that is
    not a property of the belief: a capped main must not acquire a queue entry
    for a belief nothing would release.

    **The second shape is the one that bites.** A properly quarantined record
    carries `behave` as well as the pin, so it is level with its own rung and
    would fall out of any queue. A record whose license field still says
    `assert` — a log written before the pin was applied, or by another build —
    is held far below the rung its field claims, and it is still not an item.
    """
    assert queue(a_view(record, ceiling=rung)) == ()
    assert missing(record, ceiling=Ceiling(rung)) == ()


@pytest.mark.cap10_unsaid
def test_the_queue_has_no_branch_for_quarantine_at_all():
    """**Absence is the design, not an omission.**

    A quarantined belief is absent because no repair the ladder accepts raises
    it — the probe finds nothing and a belief with no condition is not an item.
    An ``if quarantined`` guard here would be a second reader of the pin with
    its own idea of what counts, which is how a quarantined contact became a
    crisis door once already; and it would be a guard the rule above it already
    forbids the case of, which is a guard that cannot fire.

    **Two spellings, because the first one alone was weaker than this
    docstring.** A scan over bound names catches ``from ... import quarantined``
    and ``ladder.quarantined(b)`` and misses ``belief.get("quarantined")``,
    which is the shorter way to write the same branch — verified by mutation,
    where the string-literal form walked past the name scan and was caught only
    by the behavioural sweep above. So string constants are read too, with
    docstrings excluded: this module's prose says the word ``quarantined``
    several times, on purpose, and a scan that could not tell an explanation
    from a branch would be red for the explanation.
    """
    tree = ast.parse(
        (ROOT / "half/governance/unsaid.py").read_text(encoding="utf-8")
    )
    docstrings = {
        ast.get_docstring(node, clean=False)
        for node in ast.walk(tree)
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef,
                             ast.AsyncFunctionDef))
    }
    named = {
        node.attr for node in ast.walk(tree) if isinstance(node, ast.Attribute)
    } | {
        node.id for node in ast.walk(tree) if isinstance(node, ast.Name)
    } | {
        alias.name
        for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)
        for alias in node.names
    } | {
        node.value
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant) and isinstance(node.value, str)
        and node.value not in docstrings
    }
    assert not named & {"quarantined", "QUARANTINED", "pinned",
                        "QuarantineCandidate"}, sorted(
        named & {"quarantined", "QUARANTINED", "pinned", "QuarantineCandidate"}
    )


# ═════════════════════════════════════════════════════════════════════════════
# matrix: already sayable / nothing held
# ═════════════════════════════════════════════════════════════════════════════


@pytest.mark.cap10_unsaid
@pytest.mark.parametrize(
    "record",
    [
        SAYABLE,
        belief(license="behave"),
        belief(license="ask"),
        belief(license="shout"),
        belief(),
    ],
    ids=["assert-earned", "behave", "ask", "malformed", "no-license-field"],
)
def test_a_belief_at_the_rung_it_needs_is_not_queued(record):
    """Matrix: already sayable, and the ordinary case beside it.

    Nothing is being withheld from a belief that is on the rung it would reach,
    and that covers the two shapes that would otherwise flood the queue: a
    `behave` belief is not an insight above its license, it *is* its license;
    and a malformed or missing license resolves to `behave` in both directions
    at once, so it is level with itself rather than held below a rung nobody
    can read.
    """
    assert queue(a_view(record)) == ()


@pytest.mark.cap10_unsaid
def test_a_main_with_nothing_above_its_license_has_an_empty_queue():
    """Matrix: nothing held. **The ordinary case, and not an error.**"""
    assert queue(UnsaidView()) == ()
    assert queue(a_view(belief(license="behave"))) == ()
    assert depth(queue(UnsaidView())) == 0
    assert depths(()) == {condition: 0 for condition in CONDITIONS}


# ═════════════════════════════════════════════════════════════════════════════
# matrix: capped — the rung is the effective one (AD-28)
# ═════════════════════════════════════════════════════════════════════════════


@pytest.mark.cap10_unsaid
@pytest.mark.ad28
def test_a_ceiling_holding_a_belief_below_its_own_rung_names_the_ceiling():
    """Matrix: capped. The condition is the ceiling, and the reported rung is
    the **effective** one — a queue that reported the uncapped answer would be
    wrong in exactly the direction AD-28 exists to close."""
    item = only(queue(a_view(SAYABLE, ceiling=License.BEHAVE)))
    assert item.conditions == (CEILING,)
    assert item.rung is License.BEHAVE
    assert item.would_reach is License.ASSERT


@pytest.mark.cap10_unsaid
@pytest.mark.ad28
@pytest.mark.parametrize(
    "rung, capped",
    [(License.ASSERT, 0), (License.ASK, 1), (License.BEHAVE, 2)],
    ids=["uncapped", "capped-at-ask", "capped-at-behave"],
)
def test_a_main_capped_lower_holds_more_unsaid_and_the_queue_says_so(rung, capped):
    """AD-28, as the story states it: *a main capped at `behave` holds more
    unsaid*. The ceiling is applied where licenses are resolved, so lowering it
    lengthens this queue with nothing else changing anywhere."""
    view = a_view(
        belief(id="b_ask", license="ask"),
        belief(id="b_assert", license="assert", support=["s_1"],
               known_to_main=True),
        ceiling=rung,
    )
    items = queue(view)
    assert depth(items) == capped
    assert all(item.conditions == (CEILING,) for item in items)


@pytest.mark.cap10_unsaid
@pytest.mark.ad28
def test_a_capped_and_unacknowledged_belief_names_both_of_its_two_sources():
    """A belief refused for two reasons names **both**, and the two reasons here
    come from two different places: one from the ladder's own preconditions, one
    from AD-28's cap. Neither hides the other."""
    item = only(queue(a_view(UNACKNOWLEDGED, ceiling=License.BEHAVE)))
    assert item.conditions == (ACKNOWLEDGEMENT, CEILING)
    assert item.rung is License.BEHAVE


# ═════════════════════════════════════════════════════════════════════════════
# every named condition is necessary, and together they release it
# ═════════════════════════════════════════════════════════════════════════════


@pytest.mark.cap10_unsaid
@pytest.mark.parametrize(
    "record",
    [UNACKNOWLEDGED, UNCITED, NEITHER, SAYABLE],
    ids=["unacknowledged", "uncited", "neither", "earned"],
)
@pytest.mark.parametrize("rung", RUNGS, ids=[str(r) for r in RUNGS])
def test_the_named_conditions_are_exactly_what_it_takes_to_release_it(record, rung):
    """**The round trip, over every shape and every ceiling.**

    Two halves, and a queue is only honest if it has both. *Sufficient*: meeting
    every named condition puts the belief on the rung it would reach, so no
    condition was left out and nobody is told a lie about what remains.
    *Necessary*: leaving any one of them out does not, so no condition was named
    that would not have to be met — which is the padding a queue with a
    plausible-looking list would quietly acquire.

    Computed against ``resolve`` directly rather than through the queue, so the
    probe is checked against the ladder rather than against itself.
    """
    from half.context.build import resolve

    ceiling = Ceiling(rung)
    named = missing(record, ceiling=ceiling)
    would_reach = resolve(
        {**record, "known_to_main": True, "support": ["s_1"]}, ceiling=UNCAPPED
    )
    if not named:
        assert resolve(record, ceiling=ceiling) is would_reach
        return

    def met(conditions):
        repaired = dict(record)
        if ACKNOWLEDGEMENT in conditions:
            repaired["known_to_main"] = True
        if RECEIPT in conditions:
            repaired["support"] = ["s_1"]
        cap = UNCAPPED if CEILING in conditions else ceiling
        return resolve(repaired, ceiling=cap)

    assert met(named) is would_reach, f"{named} does not release {record}"
    for one in named:
        short = tuple(c for c in named if c != one)
        assert met(short) is not would_reach, (
            f"{one!r} is named but not needed; {short} already releases it"
        )


# ═════════════════════════════════════════════════════════════════════════════
# matrix: depth, and reasons that stay separable
# ═════════════════════════════════════════════════════════════════════════════


@pytest.mark.cap10_unsaid
def test_eleven_held_for_two_different_reasons_are_readable_as_both():
    """Matrix: depth. **The glossary's signal, and the failure 5b names.**

    *"Eleven insights waiting on an acknowledgement"* and *"eleven waiting on a
    receipt"* are different situations. A number that cannot tell them apart is
    not the signal the glossary asks for, so depth sits beside its reasons and
    never instead of them.
    """
    beliefs = [
        belief(id=f"b_{n}", license="assert", support=["s_1"]) for n in range(11)
    ] + [
        belief(id=f"c_{n}", license="assert", known_to_main=True) for n in range(11)
    ]
    items = queue(a_view(*beliefs))
    assert depth(items) == 22
    assert depths(items) == {ACKNOWLEDGEMENT: 11, RECEIPT: 11, CEILING: 0}
    assert len(waiting_on(items, ACKNOWLEDGEMENT)) == 11
    assert {item.belief_id for item in waiting_on(items, RECEIPT)} == {
        f"c_{n}" for n in range(11)
    }


@pytest.mark.cap10_unsaid
def test_the_counts_by_reason_do_not_sum_to_the_depth_and_are_not_meant_to():
    """A belief refused for two reasons is **one** item under **two** headings.
    Asserted rather than left to a reader, because a caller that adds the counts
    up will otherwise report a queue twice as deep as it is."""
    items = queue(a_view(NEITHER))
    assert depth(items) == 1
    assert sum(depths(items).values()) == 2


@pytest.mark.cap10_unsaid
def test_a_reason_nobody_is_waiting_on_reads_as_zero_and_not_as_absent():
    """A caller comparing two mains, or one main across two days, must not have
    to tell a missing key from an empty one."""
    counts = depths(queue(a_view(UNACKNOWLEDGED)))
    assert set(counts) == set(CONDITIONS)
    assert counts[RECEIPT] == 0 and counts[CEILING] == 0


@pytest.mark.cap10_unsaid
def test_a_condition_this_build_does_not_know_is_asked_about_without_raising():
    """``waiting_on`` answers empty for a vocabulary this build does not have:
    a caller asking about nothing Half holds is honestly told nothing."""
    assert waiting_on(queue(a_view(NEITHER)), "day-of-week") == ()
    assert waiting_on(None, ACKNOWLEDGEMENT) == ()
    assert depth(None) == 0


# ═════════════════════════════════════════════════════════════════════════════
# matrix: junk, and every script
# ═════════════════════════════════════════════════════════════════════════════


@pytest.mark.cap10_unsaid
@pytest.mark.parametrize(
    "record, expected",
    [
        (None, ()),
        ("b_1", ()),
        (42, ()),
        ([], ()),
        ({}, ()),
        ({"license": 3}, ()),
        ({"license": "shout"}, ()),
        ({"license": "assert", "support": 7}, (ACKNOWLEDGEMENT, RECEIPT)),
        ({"license": "assert", "support": ["s_1"], "known_to_main": "yes"},
         (ACKNOWLEDGEMENT,)),
        ({"license": "assert", "support": ["s_1"], "known_to_main": 1},
         (ACKNOWLEDGEMENT,)),
    ],
    ids=["none", "string", "int", "list", "empty", "license-int", "license-word",
         "support-int", "known-string", "known-int"],
)
def test_a_junk_belief_travels_through_the_queue_without_raising(record, expected):
    """The queue is read on a main's own path, so a malformed record must cost a
    queue entry and never a turn — nothing here raises whatever it is handed.

    **And every uncertain value resolves in the restrictive direction**, which
    for a *permission-granting* field is the opposite direction from everywhere
    else: ``known_to_main="yes"`` and ``known_to_main=1`` are not knowledge the
    main has, so the belief is still held and the acknowledgement is still named.
    A value that is not a belief at all is not held; a belief whose license
    nothing can read is level with itself at `behave` and is not held either.
    """
    assert missing(record, ceiling=UNCAPPED) == expected
    view = UnsaidView(beliefs={"b_1": record}, ceiling=Ceiling())
    assert tuple(item.conditions for item in queue(view)) == (
        (expected,) if expected else ()
    )


@pytest.mark.cap10_unsaid
@pytest.mark.parametrize(
    "claim",
    [
        "wants to buy farmland",
        "転職を考えている",
        "ज़मीन खरीदना चाहता है",
        "يريد شراء الأرض",
        "хочет купить землю",
        "🌾🌾",
    ],
    ids=["latin", "japanese", "devanagari", "arabic", "cyrillic", "emoji"],
)
def test_a_claim_in_any_script_is_queued_identically(claim):
    """Matrix: worldwide. **Never defaulted.**

    The queue never reads a claim at all — an item carries an id, two rungs and
    a tuple of names — so no tokenizer, no collation and no locale is anywhere
    on this path, and a belief written in a script this build has never seen is
    held and reported exactly like one written in Latin.
    """
    item = only(queue(a_view(belief(claim=claim, license="assert"))))
    assert item.conditions == (ACKNOWLEDGEMENT, RECEIPT)
    assert claim not in repr(item)


# ═════════════════════════════════════════════════════════════════════════════
# the log: computed, never stored, and never written to
# ═════════════════════════════════════════════════════════════════════════════


@pytest.mark.cap10_unsaid
def test_reading_the_queue_any_number_of_times_leaves_the_log_unchanged(tmp_path):
    """Matrix: nothing promoted. **Never a silent write.**

    Compared byte for byte over the whole of the main's directory rather than by
    counting records: a queue that quietly appended, rewrote a shard or touched
    an index would pass a record count and fail this. The derived SQLite file is
    included while the process is open — an index the read touched would show
    there — and dropped afterwards, because a checkpoint on close moves its
    bytes without anybody having written anything.
    """
    registry = ActorRegistry(tmp_path)
    try:
        seed(tmp_path)
        registry.lower_ceiling(MAIN, License.BEHAVE, t=T, because="aftercare")
        before = directory_bytes(tmp_path)
        shards = log_bytes(tmp_path)
        for _ in range(5):
            assert depth(held(registry)) == 1
            assert directory_bytes(tmp_path) == before
    finally:
        registry.close()
    assert log_bytes(tmp_path) == shards


@pytest.mark.cap10_unsaid
@pytest.mark.ad28
def test_a_ceiling_that_lifts_shrinks_the_queue_with_no_write_of_its_own(tmp_path):
    """Matrix: a ceiling lifts. **Derived.**

    Aftercare restores a rung; the queue shrinks because the fold says so, and
    nothing about the queue is recorded anywhere. The restore is a real
    ``release_ceiling`` — one rung at a time, which is the only way up — so what
    is being tested is the product's own path and not a rewritten field.
    """
    registry = ActorRegistry(tmp_path)
    try:
        seed(tmp_path)
        registry.lower_ceiling(MAIN, License.BEHAVE, t=T, because="aftercare")
        first = only(held(registry))
        assert first.conditions == (CEILING,) and first.rung is License.BEHAVE

        registry.release_ceiling(MAIN, to=License.ASK, t=T, because="step one")
        stepped = only(held(registry))
        assert stepped.conditions == (CEILING,) and stepped.rung is License.ASK

        registry.release_ceiling(MAIN, to=License.ASSERT, t=T, because="step two")
        assert held(registry) == ()
        ceilings = _records(tmp_path, Op.CEILING)
        assert len(ceilings) == 3, "the restore was not the product's own path"
    finally:
        registry.close()


@pytest.mark.cap10_unsaid
def test_an_acknowledgement_landing_takes_the_item_out_of_the_queue():
    """Matrix: an acknowledgement lands. **Derived.**

    The release runs through ``ladder.promote`` — the real writer, with the real
    acknowledgement argument — rather than by setting a field, so what is
    asserted is that the condition the queue named is the one the ladder
    actually wants. The fields it returns are the fields of an append and the
    fold would carry them; here they are folded straight back into a view, which
    is the same arithmetic one record earlier.

    Seeded as a mapping rather than through a ``Store`` for the reason this
    module's docstring gives: this build cannot write an unacknowledged
    `assert`, and the writer gate is what stops it.
    """
    view = a_view(UNACKNOWLEDGED)
    assert only(queue(view)).conditions == (ACKNOWLEDGEMENT,)

    promoted = {
        **UNACKNOWLEDGED,
        **ladder.promote(UNACKNOWLEDGED, to=License.ASSERT, acknowledged=True),
    }
    assert promoted["known_to_main"] is True
    assert queue(a_view(promoted)) == ()


@pytest.mark.cap10_unsaid
def test_a_belief_the_main_erased_is_absent_from_the_queue(tmp_path):
    """Matrix: erased. **Tombstones respected**, and without a rule here about
    them: the fold removes an expunged belief, so a queue folded from the log
    cannot report one. A queue with a record of its own would have kept it."""
    registry = ActorRegistry(tmp_path)
    try:
        seed(tmp_path)
        registry.lower_ceiling(MAIN, License.BEHAVE, t=T, because="aftercare")
        assert depth(held(registry)) == 1
    finally:
        registry.close()

    with Store(tmp_path / MAIN) as store:
        store.expunge("b_1", t="2026-09-02T00:00:00Z")

    registry = ActorRegistry(tmp_path)
    try:
        assert held(registry) == ()
    finally:
        registry.close()


@pytest.mark.cap10_unsaid
def test_folding_the_same_log_twice_gives_the_same_queue(tmp_path):
    """Matrix: replay (AD-4). The queue is a pure function of the log, so two
    folds — and two processes, since the second registry hydrates from disk —
    produce the identical value, item for item and condition for condition."""
    registry = ActorRegistry(tmp_path)
    try:
        seed(tmp_path)
        seed(tmp_path, ident="b_2", rung=License.ASK, claim="wants a dog")
        registry.lower_ceiling(MAIN, License.BEHAVE, t=T, because="aftercare")
        first = held(registry)
        second = held(registry)
    finally:
        registry.close()
    again = ActorRegistry(tmp_path)
    try:
        third = held(again)
    finally:
        again.close()
    assert first == second == third
    assert [item.belief_id for item in first] == ["b_1", "b_2"]


def _records(root, op, main_id=MAIN):
    with Store(root / main_id) as store:
        return [record for record in store.log if record.op is op]


# ═════════════════════════════════════════════════════════════════════════════
# structure: computed and never stored
# ═════════════════════════════════════════════════════════════════════════════


@pytest.mark.cap10_unsaid_structure
def test_there_is_nowhere_to_store_a_queue(tmp_path):
    """Matrix: computed (AD-3, AD-30). **No record, no counter, no field.**

    Three halves, because a stored queue could arrive as any of them: a field on
    ``State`` for the fold to carry, an op for the log to hold, or a record
    appended by the read itself. The last is the one a behavioural test would
    miss on a fresh store and catch a week later, so it is checked over a main
    who actually has a queue.
    """
    assert not {f.name for f in dataclasses.fields(State)} & {
        "unsaid", "queue", "held", "conditions", "unsaid_depth",
    }
    assert not {str(op) for op in Op} & {"unsaid", "queued", "release"}

    registry = ActorRegistry(tmp_path)
    try:
        seed(tmp_path)
        registry.lower_ceiling(MAIN, License.BEHAVE, t=T, because="aftercare")
        before = len(_records(tmp_path, Op.ASSERT)) + len(
            _records(tmp_path, Op.CEILING)
        )
        assert depth(held(registry)) == 1
        after = len(_records(tmp_path, Op.ASSERT)) + len(
            _records(tmp_path, Op.CEILING)
        )
    finally:
        registry.close()
    assert before == after


@pytest.mark.cap10_unsaid_structure
def test_the_door_reads_the_log_and_appends_nothing(tmp_path):
    """The registry's door is one narrowed read. Asserted over its own body,
    because *"it does not append today"* decays the first time somebody adds a
    convenience beside it — and the convenience would be the first step of the
    delivery path CAP-10 puts at context construction."""
    tree = ast.parse((ROOT / "half/actor/registry.py").read_text(encoding="utf-8"))
    door = next(
        node for node in ast.walk(tree)
        if isinstance(node, ast.AsyncFunctionDef) and node.name == "unsaid_view"
    )
    called = {
        node.func.attr if isinstance(node.func, ast.Attribute) else
        node.func.id if isinstance(node.func, ast.Name) else ""
        for node in ast.walk(door) if isinstance(node, ast.Call)
    }
    assert called == {"acquire", "list", "fold_records", "narrowed_for_unsaid",
                      "Ceiling"}, sorted(called)
    assert not called & {"record", "append", "expunge", "send", "note_ask"}


@pytest.mark.cap10_unsaid_structure
def test_the_view_is_narrowed_and_not_the_fold(tmp_path):
    """Story 10's lesson, for the fourth time and for a reason of its own.

    ``if state.aftercare is not None: return ()`` is one line, needs no new
    import, and would report *nothing held* for the main holding the most —
    aftercare is what lowers a ceiling and a lowered ceiling is what fills this
    queue. It is an ``AttributeError`` here rather than a line a scan has to be
    clever enough to see. The allowlist is read from the module rather than
    copied into this file.
    """
    registry = ActorRegistry(tmp_path)
    try:
        seed(tmp_path)
        view = asyncio.run(registry.unsaid_view(MAIN))
    finally:
        registry.close()
    assert view_fields() == (*VISIBLE, "ceiling")
    assert VISIBLE == ("beliefs",)
    for absent in ("aftercare", "crisis", "schedule", "spoke", "touches",
                   "loops", "tensions", "expunged"):
        assert not hasattr(view, absent), f"{absent} is reachable from the queue"
    with pytest.raises(dataclasses.FrozenInstanceError):
        view.ceiling = Ceiling(License.BEHAVE)


@pytest.mark.cap10_unsaid_structure
def test_the_view_copies_rather_than_referencing_the_fold():
    """A view handed out must not change under its reader while the actor keeps
    working, and must not be a way to write into the fold."""
    state = State()
    state.beliefs["b_1"] = {"license": "assert", "support": ["s_1"]}
    view = narrowed_for_unsaid(state, Ceiling())
    state.beliefs["b_1"]["known_to_main"] = True
    assert view.beliefs["b_1"].get("known_to_main") is None
    assert only(queue(view)).conditions == (ACKNOWLEDGEMENT,)


# ═════════════════════════════════════════════════════════════════════════════
# structure: a view, never a route
# ═════════════════════════════════════════════════════════════════════════════


#: Every package a held insight must not be able to reach from here: the two
#: that put words on a wire, the three that compose or judge, the stores and the
#: actor that could write, and the model and the network.
#:
#: **Derived from ``tests/conftest.py`` rather than restated**, for the reason
#: that file gives about its own constants: a list of forbidden strings only
#: catches the spellings somebody thought of, and a second copy of a rule is a
#: weaker copy of it. ``CLOSED`` is *no path to a store*; ``UNREACHABLE`` is *no
#: model, no channel, no network*; the rest is this story's own addition — the
#: composers, which no other guarded package needed named because none of them
#: is downstream of one.
COMPOSERS: Final[tuple[str, ...]] = (
    "half.voice", "half.surface", "half.interrupt", "half.crisis",
    "half.consolidate", "half.correction", "half.questions", "half.trust",
)
TO_A_WIRE: Final[tuple[str, ...]] = tuple(
    sorted({*CLOSED, *UNREACHABLE, *COMPOSERS})
)


def _module_file(name):
    """The file a dotted ``half.*`` target lives in, longest prefix first.

    Longest first so ``half.context.build.resolve`` resolves to
    ``half/context/build.py`` and not to the package's ``__init__``, which
    imports something different — the collapse that made an earlier version of
    ``tests/conftest.py``'s model sweep report a clean surface for a package
    that reached the provider.
    """
    if not name.startswith("half"):
        return None
    parts = name.split(".")
    for stop in range(len(parts), 0, -1):
        stem = "/".join(parts[:stop])
        for candidate in (ROOT / f"{stem}.py", ROOT / stem / "__init__.py"):
            if candidate.is_file():
                return candidate
    return None


def _named(path):
    """``path`` as it should read in a trail: relative inside the tree, and its
    bare name for a synthetic bypass written outside it."""
    return str(path.relative_to(ROOT)) if path.is_relative_to(ROOT) else path.name


def routes_to(start, roots):
    """Every path from ``start`` to something under ``roots``, each step named.

    **Transitive, and the trail is reported rather than the destination**, so a
    red build hands a reviewer the route and not just its end — the discipline
    ``past_the_port`` in ``tests/conftest.py`` settled on. Import reachability
    rather than a call graph, deliberately: a module that cannot *name* a
    channel cannot reach one however it is called, and a call-graph scan is only
    ever as clever as whoever wrote it.
    """
    offending, seen, pending = [], {start}, [start]
    trail = {start: _named(start)}
    while pending:
        path = pending.pop()
        for name in sorted(resolved_imports(path)):
            if any(name == root or name.startswith(f"{root}.") for root in roots):
                offending.append(f"{trail[path]} -> {name}")
                continue
            step = _module_file(name)
            if step is None or step in seen:
                continue
            seen.add(step)
            trail[step] = f"{trail[path]} -> {name}"
            pending.append(step)
    return sorted(offending)


@pytest.mark.cap10_unsaid_structure
@pytest.mark.ad18
def test_no_route_leads_from_the_queue_to_a_wire(tmp_path):
    """**The rule a reviewer should be hardest on, asserted structurally.**

    CAP-10 puts enforcement at context construction and says so in the same
    sentence that asks for this queue, because a queue with a delivery path is a
    second route to the wire and the first thing a later story would reach for.
    A fixture cannot make this claim: it only ever shows the routes somebody
    thought of. So the whole reachable tree is walked from the queue outward, and
    the claim is that no path — of any length — arrives at a channel, a
    composer, a judge, a store, the actor, a model or the network.

    The one exemption is the one the story mandates: the queue reaches
    ``half.context.build`` because ``resolve`` is *the* door that answers what
    rung a belief is effectively on, and that door drags in
    ``half.context.channels`` for its own return types. That is checked as a
    *narrower* rule below rather than waved through here — the queue must name
    one thing in that package and no channel type at all.
    """
    assert routes_to(ROOT / "half/governance/unsaid.py", TO_A_WIRE) == []


@pytest.mark.cap10_unsaid_structure
@pytest.mark.parametrize(
    "line",
    [
        "from half.channel.port import Channel",
        "from half.voice import compose",
        "import half.surface.morning",
        "from half.store import store as _second",
        "from half.actor import ActorRegistry",
        "import anthropic",
        "from half.consolidate.judge import judge",
    ],
    ids=["channel", "composer", "surface", "aliased-store", "actor", "model",
         "judge"],
)
def test_the_route_sweep_catches_each_reach_it_exists_to_forbid(tmp_path, line):
    """**A guard nobody has tried to defeat is a guard resting on nothing.**

    Each of these is one edge away from the queue. The sweep must report the
    route rather than merely refusing, so the trail is asserted too — a scan
    that says *"something is wrong"* and not *"here is the path"* is one nobody
    can act on.
    """
    reaching = tmp_path / "reaching.py"
    reaching.write_text(f"{line}\n", encoding="utf-8")
    found = routes_to(reaching, TO_A_WIRE)
    assert found, f"the sweep does not see: {line}"
    assert all(route.startswith("reaching.py -> ") for route in found), found


@pytest.mark.cap10_unsaid_structure
def test_the_route_sweep_admits_the_one_door_the_story_mandates(tmp_path):
    """The other half: a sweep that fired on everything would be as useless as
    one that fired on nothing. Reading the ladder through the context builder is
    exactly what this story was told to do."""
    legitimate = tmp_path / "legitimate.py"
    legitimate.write_text(
        "from half.context.build import resolve\n"
        "from half.governance.ladder import Ceiling\n"
        "from half.store.fold import State\n",
        encoding="utf-8",
    )
    assert routes_to(legitimate, TO_A_WIRE) == []


@pytest.mark.cap10_unsaid_structure
@pytest.mark.ad18
def test_the_queue_names_one_thing_in_the_context_package_and_no_channel():
    """The narrower half of *no route to a context*.

    ``half.context.channels`` is transitively reachable because ``resolve``
    lives beside ``build`` — that is a property of where story 4b put the door,
    not a route this story opened. What this story must not do is *name*
    anything that assembles or carries a context, so the queue's own bindings
    are pinned: one function from ``half.context``, and no ``Context``,
    ``Content``, ``Directive`` or ``Question`` anywhere in the file.
    """
    source = (ROOT / "half/governance/unsaid.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    from_context = {
        name for name in resolved_imports(ROOT / "half/governance/unsaid.py")
        if name.startswith("half.context")
    }
    assert from_context == {"half.context.build", "half.context.build.resolve"}

    named = {
        node.id for node in ast.walk(tree) if isinstance(node, ast.Name)
    } | {
        node.attr for node in ast.walk(tree) if isinstance(node, ast.Attribute)
    }
    assert not named & {"Context", "Content", "Directive", "Question", "Item",
                        "split", "build", "withheld", "leaks", "fragments"}


@pytest.mark.cap10_unsaid_structure
def test_the_queue_reaches_past_the_one_door_into_no_rule_of_its_own():
    """**The release condition is read, not restated.**

    A second reader of the license fields would be a second answer to *what rung
    is this belief on*, with AD-28's ceiling capping only one of them — and a
    second list of what a rung requires would agree with the ladder until
    somebody edits one, which is the failure this codebase has caught in a
    denylist, a marker list and a floor comment. So the queue takes the ladder's
    **field names** and its **rung arithmetic**, and none of its rules.
    """
    imported = {
        f"{node.module}.{alias.name}"
        for node in ast.walk(
            ast.parse((ROOT / "half/governance/unsaid.py").read_text(
                encoding="utf-8"))
        )
        if isinstance(node, ast.ImportFrom)
        for alias in node.names
    }
    assert "half.context.build.resolve" in imported
    assert not imported & {
        f"half.governance.ladder.{name}"
        for name in ("permitted", "own_rung", "rung_of", "has_receipt",
                     "known_to_main", "quarantined", "cap", "weaker", "promote",
                     "demote", "admitted")
    }
    # The field names *are* taken from the ladder, which is the other half of
    # the same rule: a probe that spelled "known_to_main" itself would be a
    # second place the field is named, and a rename would leave it probing a
    # field no belief has.
    assert {"half.governance.ladder.KNOWN",
            "half.governance.ladder.SUPPORT"} <= imported


@pytest.mark.cap10_unsaid_structure
def test_nothing_under_half_reaches_the_queue_but_the_registrys_door():
    """**Adding this queue added no caller on a send path.**

    The one importer is the registry, and what it does with it is one narrowed
    read. A second importer is not forbidden for ever — a later story may
    legitimately want one — but it is a deliberate edit with a reviewer on it
    rather than a line that arrives unnoticed inside a composer.
    """
    importers = sorted(
        str(path.relative_to(ROOT))
        for path in (ROOT / "half").rglob("*.py")
        if path.name != "unsaid.py"
        and any(
            name == "half.governance.unsaid"
            or name.startswith("half.governance.unsaid.")
            for name in resolved_imports(path)
        )
    )
    assert importers == ["half/actor/registry.py"], importers


# ═════════════════════════════════════════════════════════════════════════════
# structure: a value with no word of a claim
# ═════════════════════════════════════════════════════════════════════════════


@pytest.mark.cap10_unsaid_structure
@pytest.mark.ad18
def test_an_item_holds_no_word_of_the_claim_it_is_about():
    """**AD-22 and CAP-10's *never quotable* in one property.**

    The deepest reason no route exists from here to a wire is that there is
    nothing on this value to put on one. An item carries an opaque id, two rungs
    and a tuple of condition names — no claim, no topic, no wording — so a
    caller that got hold of the whole queue and reached a channel would have
    nothing to say with it.

    Asserted on the fields *and* on the rendering, because a field named
    innocently could still carry text: the claim's every word is checked against
    the item's own repr.
    """
    fields = {f.name for f in dataclasses.fields(Unsaid)}
    assert fields == {"belief_id", "rung", "would_reach", "conditions"}
    assert not fields & {"claim", "text", "wording", "belief", "topics",
                         "subject", "loop"}

    item = only(queue(a_view(belief(claim=CLAIM, license="assert"))))
    rendered = repr(item)
    for word in CLAIM.split():
        assert word not in rendered, f"the item carries {word!r} of the claim"
    assert dataclasses.asdict(item) == {
        "belief_id": "b_1",
        "rung": License.ASK,
        "would_reach": License.ASSERT,
        "conditions": (ACKNOWLEDGEMENT, RECEIPT),
    }


@pytest.mark.cap10_unsaid_structure
def test_an_item_is_frozen_and_cannot_be_widened_by_its_holder():
    """A caller cannot write over what it was handed, and **cannot bolt a claim
    onto it either**: the item is slotted, so there is no ``__dict__`` for a
    caller to grow one in. That is the half that matters here — the fields are
    empty of text by design, and an item somebody could attach text to would be
    a route back."""
    item = only(queue(a_view(UNACKNOWLEDGED)))
    with pytest.raises(dataclasses.FrozenInstanceError):
        item.conditions = ()
    assert "__slots__" in vars(Unsaid) and not hasattr(item, "__dict__")
    with pytest.raises((AttributeError, TypeError)):
        item.claim = CLAIM
    assert not hasattr(item, "claim")


# ═════════════════════════════════════════════════════════════════════════════
# structure: the vocabulary, and the cap that cannot be forgotten
# ═════════════════════════════════════════════════════════════════════════════


@pytest.mark.cap10_unsaid_structure
def test_the_condition_vocabulary_is_closed_and_ordered():
    """A caller counting what is held counts constants, never a message — an
    exception message quotes the value that caused it, and here that would be a
    record out of a main's own log (AD-22). Ordered, because two builds folding
    one log must produce the same queue byte for byte and a set would order it
    by hash seeding (AD-4)."""
    assert CONDITIONS == (ACKNOWLEDGEMENT, RECEIPT, CEILING)
    assert len(set(CONDITIONS)) == len(CONDITIONS)
    for record, ceiling in ((NEITHER, License.BEHAVE), (UNCITED, License.ASK)):
        named = missing(record, ceiling=Ceiling(ceiling))
        assert set(named) <= set(CONDITIONS)
        assert list(named) == [c for c in CONDITIONS if c in named]


@pytest.mark.ad28
@pytest.mark.cap10_unsaid_structure
def test_asking_what_is_missing_without_a_ceiling_is_a_type_error():
    """The structural half of AD-28, which no scan can be wrong about: a caller
    that forgets the cap gets a ``TypeError`` rather than a queue computed as
    though no cap existed — which would report *nothing held* for precisely the
    main a ceiling is holding everything back from."""
    with pytest.raises(TypeError):
        missing(SAYABLE)


@pytest.mark.ad28
@pytest.mark.cap10_unsaid_structure
def test_the_lifted_cap_is_a_ceiling_that_caps_nothing_and_not_an_exemption():
    """``ceiling=None`` inside ``half/`` is a surface declaring itself exempt
    from AD-28, which ``tests/test_ladder.py`` fails the build for. The
    counterfactual here is a *ceiling* at the top rung, which by AD-28's own
    arithmetic subtracts nothing — a hypothetical rather than an exemption."""
    assert isinstance(UNCAPPED, Ceiling)
    assert UNCAPPED.rung is License.ASSERT
    assert UNCAPPED.capping is False
    # Asserted over the *code* rather than the file: the module's own comment
    # explains why ``ceiling=None`` is refused here, and a scan over raw text
    # would fail on the explanation. This is the AD-28 gate's own reading — a
    # call passing a literal ``None`` for the cap — asked of this one module.
    tree = ast.parse((ROOT / "half/governance/unsaid.py").read_text(
        encoding="utf-8"))
    exempting = [
        node.lineno
        for node in ast.walk(tree) if isinstance(node, ast.Call)
        for keyword in node.keywords
        if keyword.arg == "ceiling"
        and isinstance(keyword.value, ast.Constant)
        and keyword.value.value is None
    ]
    assert not exempting, f"a cap is declared absent at {exempting}"
