"""Whether a disagreement is widening, computed from the log (CAP-7, AD-30).

**Widening is computed, never judged.** *Drift is tension velocity* is one of
the three metrics the product is measured on (SPEC, *Success signal*), and a
metric a model decides is a metric that moves when the model changes: two builds
reading one log would disagree about how much a main had drifted, and a model
upgrade would look like a life event. So every transition here is a function of
three things — what the log holds for each side, the stamp on the tension's own
record, and an injected ``now`` — and of nothing else. No model call, no
network, no clock read (AD-19 exists; this module does not need it).

**Nothing here ranks the two sides.** Every rule below is symmetric in the pair:
the *number* of sides that accumulated evidence decides the state, never which
one did. ``Drift`` reports what it found per side as an id-keyed mapping rather
than as a first and a second, and no field this produces reaches the log — a
tension record carries a state and nothing that says which entry moved. For a
person both entries can be true at once, and a record that named a winner would
be Half rendering the verdict the constitution forbids.

**Evidence is the support set, read out of the log.** Accumulation means *this
entry now cites sources it did not cite when the tension was last recorded* —
counted from the belief records themselves, deduplicated, at two points in the
log. Deliberately **not** the ``independent`` field: that is Half's own count of
its own evidence, so trusting it would make drift a function of a number Half
wrote rather than of what arrived. Deliberately not *"a record exists after the
stamp"* either: a license promotion appends a record and adds no evidence at
all, and counting it would report drift every time Half was allowed to speak.

**A counter is never stored for a pass to mutate.** Story 4 made salience
computed for exactly this reason, and the same rule applies one object over: a
``support_at_mint`` field written onto the tension would be state the log does
not describe, re-derived differently by any later build, and an AD-30 violation
the moment a rebuild disagreed with it. The baseline is recovered by reading the
log at the tension's own stamp, every time.

Pure and clockless; imports nothing from ``half`` but ``civil``.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any, Final

from half.civil import DAY, instant
from half.tensions.states import LIVE_STATES, TensionState, is_state

#: The record field naming the two entries a tension links. Owned here, beside
#: the computation that reads it, for the reason ``loops.timescale`` owns
#: ``TIMESCALE``: ``half.store.records`` imports it to validate the append and
#: ``half.tensions.ledger`` to read one back, and the arrow cannot run the other
#: way without closing a cycle. One definition per name, flowing upward.
BETWEEN: Final[str] = "between"

#: The field a belief record cites its evidence in. The ladder owns the
#: *writing* of it (``half.governance.ladder.SUPPORT``) and spells it the same;
#: this module only ever counts it, and ``tests/test_tensions.py`` asserts the
#: two agree so a rename in one place cannot make every tension incomputable in
#: the other.
SUPPORT: Final[str] = "support"

#: How many entries a tension links. Two, and it is named rather than inlined
#: because *"two entries that disagree"* is the definition of the object
#: (glossary) and a tension over three of them is not a tension — it is a topic.
#: A record that names any other number is refused at the append.
SIDES: Final[int] = 2

#: Field names a tension record may **never** carry, because each of them is a
#: verdict on one of its two entries rather than a fact about the pair.
#:
#: A denylist rather than a scan, and refused at the append rather than caught
#: in review, because *"neither side of a tension is wrong"* is a structural
#: promise and the log is append-only: a ``winner`` written once is a ranking
#: every future fold carries and no correction can take back. The natural way to
#: break this rule is not malice — it is a helpful line recording *which* entry
#: the evidence went against, so the morning surface can phrase it better. That
#: line is Half rendering the verdict the constitution forbids (*name the gap,
#: never render the verdict*), and it fails here.
#:
#: The list is the vocabulary of ranking, not an enumeration of everything bad:
#: it covers naming a favoured or defeated side, and marking one entry as the
#: mistaken one. A tension may still carry anything that describes *the pair* —
#: its state, its license, its evidence, the ledgers it spans.
#:
#: **This is not the correction record's business.** *"Half was wrong about
#: you"* is a real and necessary distinction and it lives on the ``revise`` op,
#: which is a statement about a *belief*. What must not exist is a tension
#: saying which of two true-for-a-person claims was the bad one.
RANKED_FIELDS: Final[frozenset[str]] = frozenset(
    {
        "winner", "loser", "won", "lost", "beats",
        "stronger", "weaker", "outranks", "rank", "ranking", "ranked",
        "primary", "secondary", "dominant", "prevailing", "prevails",
        "preferred", "favoured", "favored", "favours", "favors",
        "correct_side", "wrong_side", "right_side",
        "mistaken", "discredited", "refuted", "disproven", "verdict",
    }
)

#: How long both sides may stand still before the standing still is itself the
#: fact — the one threshold in this module, and it decides `persistent`, never
#: `widening`.
#:
#: **Widening deliberately takes no threshold at all.** It is *one side moved
#: and the other did not*, which is a fact about the log rather than a number
#: somebody chose, and the story's Ask-First list names any threshold that
#: decides widening. This one decides only when a quiet disagreement stops
#: being new.
#:
#: Fourteen days: two weeks in which a main did nothing on either side of a gap
#: Half noticed. Short enough that a fortnight-old tension is not still being
#: called `fresh` when the morning surface reaches for something to say, long
#: enough that an ordinary busy week does not reclassify everything at once.
#: The value is pinned and both sides of the boundary are asserted — anything
#: between roughly a week and a month passes the suite, which is a band rather
#: than a number, and a threshold nobody can be wrong about is a threshold
#: nobody chose.
PERSISTENCE_DAYS: Final[float] = 14.0

#: Why a tension could not be evaluated. A reason rather than a bare ``False``,
#: for the reason ``loops.timescale`` gives one: *"this tension names no pair"*
#: and *"this build cannot read its state"* want different answers from whoever
#: asks, and a caller handed only ``False`` could tell neither of them from
#: *"nothing has changed"*.
NO_PAIR: Final[str] = "no-pair"
UNKNOWN_STATE: Final[str] = "unknown-state"
RESOLVED_ALREADY: Final[str] = "resolved"
UNREADABLE_RECORDED_AT: Final[str] = "unreadable-recorded-at"
UNREADABLE_NOW: Final[str] = "unreadable-now"
UNREADABLE_SIDE: Final[str] = "unreadable-side"


@dataclass(frozen=True, slots=True)
class Evidence:
    """What one entry of a tension cited, then and now.

    A value, computed from the log every time it is wanted. ``before`` is the
    support the entry cited at the stamp on the tension's own record;
    ``now`` is what it cites in the log as it stands. Either being ``None``
    means *this build cannot tell* — an entry with no readable record at the
    baseline, or a record whose stamp is not a real instant — and every rule
    below treats that as *do not act*, never as zero.
    """

    id: str
    before: int | None = None
    now: int | None = None

    @property
    def readable(self) -> bool:
        """Whether both counts are known. False is never *"nothing changed"*."""
        return self.before is not None and self.now is not None

    @property
    def accumulated(self) -> bool:
        """Whether this entry cites evidence it did not cite at the baseline.

        Strictly greater. Support that *shrank* — a revision citing fewer
        sources — is not accumulation, and reading it as movement would report
        drift from Half tidying its own receipts.
        """
        if not self.readable:
            return False
        return self.now > self.before  # type: ignore[operator]


@dataclass(frozen=True, slots=True)
class Drift:
    """What the log says about one tension at one instant.

    Decides nothing and writes nothing; recomputed from the log every time.

    ``computable`` is false whenever the answer would have to be guessed, and
    ``reason`` then names which piece is missing. ``state`` is ``None`` while
    ``computable`` is false — there is no path here from *"we cannot tell"* to
    *"the gap is widening"*.
    """

    computable: bool = False
    #: The state the log computes to. May equal the tension's current state,
    #: which is what *"no transition is appended"* looks like from here.
    state: str | None = None
    #: Set only when ``computable`` is false. One of the module's reason
    #: constants.
    reason: str | None = None
    #: Days since the tension's own record, clamped at zero. ``None`` when
    #: undetectable.
    age_days: float | None = None
    #: Which entries accumulated evidence, **id-keyed**. A mapping rather than
    #: a pair, deliberately: a first and a second would give the two sides an
    #: order, and an order is one short step from a ranking. Nothing in the log
    #: ever carries this.
    accumulated: Mapping[str, bool] = field(default_factory=dict)


def supports(record: Mapping[str, Any] | Any) -> int | None:
    """How many distinct sources ``record`` cites, or ``None`` if it cannot say.

    Deduplicated, because ten mentions of one fact in one thread is one support
    (glossary, *independence*) and a list that repeats a source id is the
    cheapest possible way to fake accumulation.

    A bare string is accepted alongside a list, for the reason
    ``ladder.has_receipt`` accepts one: a log that wrote ``support="s_1"``
    cited a source, and refusing to read it would make that entry look
    permanently unmoved.
    """
    if not isinstance(record, Mapping):
        return None
    cited = record.get(SUPPORT)
    if cited is None:
        return 0
    if isinstance(cited, str):
        return 1 if cited.strip() else 0
    if isinstance(cited, (list, tuple)):
        return len({item for item in cited if isinstance(item, str) and item.strip()})
    return None


def evidence(
    history: Sequence[Mapping[str, Any]] | None, *, side: object, at: object
) -> Evidence:
    """What ``side`` cited at ``at``, and what it cites now, from ``history``.

    ``history`` is the main's belief records narrowed to ``id``, ``t`` and
    ``support`` — the log itself, in log order, not the fold. The fold holds
    only the *current* record for each entry, so it cannot answer *"what did
    this cite a week ago"*, and the alternative to reading the log is storing a
    counter for the pass to mutate, which is the AD-30 violation story 4 exists
    to have avoided.

    Every way this can fail to know produces a ``None`` count and never a zero:

    * ``side`` is not an id, or ``at`` is not a real instant;
    * the entry has no record in the log at all;
    * the entry has no record at or before ``at`` — the tension is older than
      the entry it names, so there is no baseline to compare against;
    * any record for the entry carries a stamp this build cannot read, which
      would silently move the baseline.
    """
    ident = side if isinstance(side, str) and side.strip() else None
    baseline = instant(at)
    if ident is None or baseline is None:
        return Evidence(id=str(side), before=None, now=None)

    rows = [
        row for row in (history or [])
        if isinstance(row, Mapping) and row.get("id") == ident
    ]
    if not rows:
        return Evidence(id=ident)

    before: int | None = None
    latest: int | None = None
    for row in rows:
        stamp = instant(row.get("t"))
        if stamp is None:
            # A stamp this build cannot read would move the baseline without
            # anyone seeing it. Refuse the whole entry rather than skip the
            # record: skipping is the guess.
            return Evidence(id=ident)
        counted = supports(row)
        if counted is None:
            return Evidence(id=ident)
        latest = counted
        if stamp <= baseline:
            before = counted
    if before is None:
        return Evidence(id=ident, before=None, now=latest)
    return Evidence(id=ident, before=before, now=latest)


def drift(
    *,
    state: object,
    recorded_at: object,
    sides: Sequence[Evidence] | None,
    now: object,
) -> Drift:
    """The state ``sides`` compute to at ``now``. Pure, and symmetric in the pair.

    ``state`` is the tension's current state and ``recorded_at`` the stamp on
    the record that set it — both read straight off the fold, so the same log
    and the same ``now`` give the same answer for ever.

    The rules, and every one of them counts sides rather than choosing between
    them:

    * **exactly one side accumulated** — `widening`. Evidence is arriving
      against an entry that has not moved, which is the gap growing. Which side
      it was is not recorded anywhere, because it is not Half's to say.
    * **both sides accumulated** — `closing`. The pair the tension links has
      been overtaken on both sides, so the disagreement *as recorded* is
      narrowing. This is the state *loop advancement is tensions closing* is
      counted from.
    * **neither side accumulated**, and the tension has stood for longer than
      ``PERSISTENCE_DAYS`` — `persistent`.
    * **neither side accumulated**, inside that window — the current state,
      unchanged. That is what *"no transition is appended"* looks like: a
      target identical to what is already there.

    ``computable=False``, with a reason and no state, for every case where the
    answer would be a guess: a tension that names no pair of entries, a state
    from a later build, a stamp on either side that is not a real instant, or an
    entry whose evidence cannot be counted. A tension that cannot be evaluated
    keeps the state it has.

    A `resolved` tension is reported as ``RESOLVED_ALREADY`` rather than
    evaluated. Resolution is the fold's answer to a correction, it is terminal,
    and there is no path back: a corrected entry does not return, and the main
    saying the thing again is a new entry and a new tension.
    """
    if not is_state(state):
        return Drift(reason=UNKNOWN_STATE)
    if state not in LIVE_STATES:
        return Drift(reason=RESOLVED_ALREADY)

    pair = list(sides or [])
    identifiers = {item.id for item in pair if isinstance(item, Evidence)}
    if len(pair) != SIDES or len(identifiers) != SIDES:
        return Drift(reason=NO_PAIR)

    since = instant(recorded_at)
    if since is None:
        return Drift(reason=UNREADABLE_RECORDED_AT)
    at = instant(now)
    if at is None:
        # The caller's own stamp, not the log's. Reported separately because
        # the fix is a different one: the log is fine and the caller is not.
        return Drift(reason=UNREADABLE_NOW)
    if not all(item.readable for item in pair):
        return Drift(reason=UNREADABLE_SIDE)

    # Clamped, so a tension recorded in the future — a skewed clock on some
    # other node — cannot buy itself negative age and look permanently fresh.
    # The same clamp ``loops.timescale.silence`` applies, for the same reason.
    age = max(0.0, (at - since) / DAY)
    moved = {item.id: item.accumulated for item in pair}
    count = sum(1 for accumulated in moved.values() if accumulated)

    if count == 1:
        target = TensionState.WIDENING.value
    elif count == SIDES:
        target = TensionState.CLOSING.value
    elif age > PERSISTENCE_DAYS:
        target = TensionState.PERSISTENT.value
    else:
        # Nothing to say. The target is what is already there, so the caller
        # appends nothing — which is what an idempotent pass over an unchanged
        # log looks like.
        target = str(state)

    return Drift(
        computable=True, state=target, age_days=age, accumulated=moved
    )
