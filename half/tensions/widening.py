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

import re
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
#: **Exact spellings are the seed, never the rule.** Review found the gate was
#: an exact-string membership test, so ``winner`` failed and ``winner_id``,
#: ``winning_side``, ``is_winner``, ``side_that_won``, ``more_credible``,
#: ``truer_side``, ``moved_side`` and ``which_moved`` were all accepted and
#: durable — including the one ``widening`` itself names as the likely breach,
#: *a helpful line recording which entry the evidence went against*. The rule is
#: ``ranks_a_side`` below, which reads a name as words; this set is the list of
#: spellings the suite drives it over, and every one of them must still fail.
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

#: Words that rank one thing over another wherever they appear in a name. One
#: of these as a *word* — ``winner_id``, ``is_winner``, ``side_that_won`` — is
#: enough on its own, because there is no innocent reason for a tension to say
#: any of them about its two entries.
RANKING_WORDS: Final[frozenset[str]] = frozenset(
    {
        "win", "wins", "winner", "winners", "winning", "won",
        "lose", "loses", "loser", "losers", "losing", "lost",
        "beat", "beats", "beaten", "defeat", "defeats", "defeated",
        "strong", "stronger", "strongest", "weak", "weaker", "weakest",
        "outrank", "outranks", "outranked",
        "rank", "ranks", "ranked", "ranking", "rankings",
        "primary", "secondary", "dominant", "dominates",
        "prevail", "prevails", "prevailing", "prevailed",
        "prefer", "prefers", "preferred",
        "favour", "favours", "favoured", "favor", "favors", "favored",
        "favourite", "favorite",
        "correct", "incorrect", "wrong", "wrongly", "right",
        "mistaken", "discredited", "refuted", "disproven", "verdict",
        "truer", "truest", "credible", "credibility",
        "better", "worse", "best", "worst", "superior", "inferior",
        "supersede", "supersedes", "superseded",
    }
)

#: Words that name *one of the two* — half of a pair.
SIDE_WORDS: Final[frozenset[str]] = frozenset({"side", "sides", "entry", "entries"})

#: Words that *choose*. Harmless alone — the pass's own result says ``moved``,
#: and a mapping of ids says ``sides`` — and a verdict when combined: ``moved``
#: plus ``side`` is the line the constitution forbids, and ``which`` plus
#: ``moved`` is the same sentence with the noun dropped.
SELECTOR_WORDS: Final[frozenset[str]] = frozenset(
    {
        "which", "whichever", "whose", "that",
        "moved", "mover", "moving", "shifted", "changed",
        "more", "most", "less", "least",
        "chosen", "choose", "chose", "pick", "picked", "picks",
        "true", "real", "good", "bad",
    }
)

#: ``winnerId`` and ``winner_id`` are the same field with two house styles.
_WORDS = re.compile(r"[A-Z]?[a-z]+|[A-Z]+(?![a-z])|[0-9]+")


def words_in(name: object) -> tuple[str, ...]:
    """``name`` split into lowercase words, on underscores and camel humps.

    Public because the neutrality guards in ``tests/test_tensions.py`` read
    *identifiers* out of an AST with the same rule the append gate reads
    *fields* with. One vocabulary, two readers: review found the two had
    drifted, so ``stronger_side`` was refused as a record field and accepted as
    a function name in the very package that defines the denylist.
    """
    if not isinstance(name, str):
        return ()
    return tuple(word.lower() for word in _WORDS.findall(name))


def ranks_a_side(name: object) -> bool:
    """Whether ``name`` ranks one side of a tension over the other.

    Two rules, both read over the *words* of the name rather than the whole
    string:

    * any word that ranks on its own — ``winner_id``, ``is_winner``,
      ``side_that_won``, ``more_credible``, ``truer_side``;
    * two or more words drawn from the vocabulary of *choosing between two*,
      at least one of which does the choosing — ``moved_side``,
      ``which_moved``, ``which_side``. Neither half fails alone, deliberately:
      ``sides`` is what a symmetric computation calls its pair and ``moved`` is
      what a count of transitions is called, and forbidding either would forbid
      the honest code as well as the verdict.

    Never raises, and false for anything that is not a string.
    """
    found = set(words_in(name))
    if found & RANKING_WORDS:
        return True
    chosen = found & SELECTOR_WORDS
    return bool(chosen) and len(found & (SELECTOR_WORDS | SIDE_WORDS)) >= 2


def ranked_names(names: object) -> tuple[str, ...]:
    """Every name in ``names`` that ranks a side, sorted. Never raises."""
    try:
        return tuple(sorted(name for name in names if ranks_a_side(name)))
    except TypeError:  # pragma: no cover - a caller handing a non-iterable
        return ()

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
#:
#: **Pinned to this value, exactly.** An earlier comment here described a band —
#: *"anything between roughly a week and a month passes the suite"* — which the
#: suite does not permit and never did: ``tests/test_tensions.py`` asserts the
#: constant by value and asserts both sides of the boundary against it, so
#: moving it is a red test rather than a quiet reclassification of every
#: standing disagreement a main has. Changing it is an Ask-First change.
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
#: The tension's own record is stamped *after* ``now``. A baseline in the future
#: is not a baseline: every record for both sides is at or before it, so both
#: counts read as unmoved and the tension cannot widen however much evidence
#: arrives. Reported rather than folded into *"nothing changed"*, because
#: *"neither side moved"* and *"we cannot yet tell whether either side moved"*
#: are different facts and only one of them is a gap. Self-healing — the next
#: pass after ``now`` passes the stamp evaluates it normally.
RECORDED_IN_FUTURE: Final[str] = "recorded-in-future"
#: A transition the ledger refused. Unreachable from ``drift``, which never
#: computes `resolved` and never leaves the vocabulary; kept because the
#: alternative to catching it is one malformed tension ending the pass for every
#: other one this main has. A **constant**, because ``Plan.incomputable``'s
#: reasons are logged as a closed set and an exception message routinely quotes
#: the value that caused it (AD-22).
REFUSED_TRANSITION: Final[str] = "refused-transition"
#: Not a tension at all, from a table this build was handed rather than folded.
NOT_A_TENSION: Final[str] = "not-a-tension"

#: Every reason a tension may be left alone, as a closed set. ``Plan`` and the
#: pass both log these; nothing else may reach ``incomputable``.
REASONS: Final[frozenset[str]] = frozenset(
    {
        NO_PAIR, UNKNOWN_STATE, RESOLVED_ALREADY, UNREADABLE_RECORDED_AT,
        UNREADABLE_NOW, UNREADABLE_SIDE, RECORDED_IN_FUTURE,
        REFUSED_TRANSITION, NOT_A_TENSION,
    }
)


def pair_of(fields: Mapping[str, Any] | Any) -> tuple[str, ...]:
    """The entries a tension record names, as ids. Tolerant; never raises.

    **One reading of ``between``, for every caller.** ``half.store.fold``
    resolves a tension by asking whether a corrected entry is one of its sides,
    and ``half.tensions.ledger`` reads the same field back for the pass; review
    found two implementations of that question which disagreed on hostile input
    — one matched the raw list, the other a list already filtered to non-empty
    strings — so a tension whose ``between`` held a blank string resolved under
    one and not the other. There is one now, and it is here, beside the
    ``BETWEEN`` constant it reads.

    Order is preserved because the log's order is preserved, not because it
    means anything: nothing reads ``pair_of(...)[0]`` as the first, the stated,
    the true or the winning side.
    """
    if not isinstance(fields, Mapping):
        return ()
    value = fields.get(BETWEEN)
    if isinstance(value, (list, tuple)):
        return tuple(item for item in value if isinstance(item, str) and item.strip())
    return ()


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
    if record.get("tombstone") is True:
        # An erased body cites nothing because there is no body, which is not
        # the same fact as *"this entry cited no sources"*. Reading it as zero
        # would move the entry's current count down and make the next honest
        # append look like accumulation.
        return None
    cited = record.get(SUPPORT)
    if cited is None:
        # A **known** zero, and deliberately not ``None``: a belief admitted
        # with no receipt genuinely cites nothing, and its first source
        # arriving is real accumulation that a ``None`` here would hide for
        # ever. The ``None`` cases are the ones where the count cannot be read
        # at all — a row that is not a record, an erased body, or a ``support``
        # of a type this build does not understand.
        return 0
    if isinstance(cited, str):
        return 1 if cited.strip() else 0
    if isinstance(cited, (list, tuple)):
        return len({item for item in cited if isinstance(item, str) and item.strip()})
    return None


def by_entry(
    history: Sequence[Mapping[str, Any]] | None,
) -> dict[str, tuple[Mapping[str, Any], ...]]:
    """``history`` indexed by entry id, each entry's rows in stamp order.

    Built **once per pass** rather than per side: ``evidence`` used to filter
    the whole narrowed log for each of a tension's two entries, so a main with
    forty tensions read their log eighty times a night for an answer that does
    not change between the reads.

    **Stamp order, not append order.** The log is ordered by append and its
    stamps need not be monotonic — the scheduler's own notes say a backward
    clock jump leaves them out of order — and ``evidence`` reads *the last row
    at or before the baseline* and *the last row of all*. Taking those in
    append order picks the wrong records and reports accumulation that did not
    happen. Rows whose stamp this build cannot read sort last and keep their
    relative order; ``evidence`` refuses the whole entry when it meets one.
    """
    found: dict[str, list[Mapping[str, Any]]] = {}
    for row in history or ():
        if not isinstance(row, Mapping):
            continue
        ident = row.get("id")
        if isinstance(ident, str) and ident:
            found.setdefault(ident, []).append(row)
    return {
        ident: tuple(
            # ``sorted`` is stable, so rows sharing a stamp — and every row
            # whose stamp is unreadable — keep the order the log wrote them in.
            sorted(rows, key=lambda row: (instant(row.get("t")) is None,
                                          instant(row.get("t")) or 0.0))
        )
        for ident, rows in found.items()
    }


def evidence(
    history: Sequence[Mapping[str, Any]] | Mapping[str, Any] | None,
    *,
    side: object,
    at: object,
) -> Evidence:
    """What ``side`` cited at ``at``, and what it cites now, from ``history``.

    ``history`` is the main's belief records narrowed to ``id``, ``t`` and
    ``support`` — the log itself, not the fold. The fold holds only the
    *current* record for each entry, so it cannot answer *"what did this cite a
    week ago"*, and the alternative to reading the log is storing a counter for
    the pass to mutate, which is the AD-30 violation story 4 exists to have
    avoided.

    Accepts either the narrowed rows or the ``by_entry`` index over them. The
    index is what a pass hands down, so the log is walked once for a main
    rather than twice for every tension; a bare sequence is indexed here, which
    keeps every caller that holds only the rows working unchanged.

    Every way this can fail to *know* the count produces a ``None`` and never a
    zero:

    * ``side`` is not an id, or ``at`` is not a real instant;
    * the entry has no record in the log at all;
    * the entry has no record at or before ``at`` — the tension is older than
      the entry it names, so there is no baseline to compare against;
    * any record for the entry carries a stamp this build cannot read, which
      would silently move the baseline;
    * any record for the entry is an erased body, or cites its sources in a
      shape this build cannot count.

    An entry that cites *nothing* is a zero rather than a ``None``, because
    that is a thing this build knows.
    """
    ident = side if isinstance(side, str) and side.strip() else None
    baseline = instant(at)
    if ident is None or baseline is None:
        return Evidence(id=str(side), before=None, now=None)

    if isinstance(history, Mapping):
        rows: Sequence[Mapping[str, Any]] = history.get(ident, ())
    else:
        rows = by_entry(history).get(ident, ())
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

    ``computable=False``, with a reason out of ``REASONS`` and no state, for
    every case where the answer would be a guess: a tension that names no pair
    of entries, a state from a later build, a stamp on either side that is not
    a real instant, a tension stamped after ``now``, or an entry whose evidence
    cannot be counted. A tension that cannot be evaluated keeps the state it
    has.

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
    if since > at:
        # A tension recorded in the future — a skewed clock on some other node,
        # or a hand-written stamp. Reported rather than clamped to age zero,
        # which is what this used to do: with the baseline ahead of ``now``,
        # *every* record for both sides is at or before it, so both counts read
        # as unmoved and the tension cannot widen however much evidence
        # arrives. The clamp made that look like a `fresh` tension nothing had
        # happened to. It says so instead, and the next pass after ``now``
        # passes the stamp evaluates it normally.
        return Drift(reason=RECORDED_IN_FUTURE)
    if not all(item.readable for item in pair):
        return Drift(reason=UNREADABLE_SIDE)

    age = (at - since) / DAY
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
