"""What a pass compares, and against what (CAP-7, story 9d).

**This module is the bound.** CAP-7's success criterion is not that tensions
get minted — it is that the pass *"runs within a fixed per-user cost budget
because comparison is bounded to new or changed entries against the loop set
and against beliefs sharing a subject … never all-pairs"*. Every one of those
clauses is a function here, and nothing downstream can widen them: the judge is
handed couples, and a couple that was never produced can never be paid for.

**Never all-pairs is a statement about growth, not about a number.** A ledger of
ten beliefs with two changed produces the same count whether the code compares
2×N or N², which is why ``tests/test_candidates.py`` asserts the *derivative*:
double the ledger with entries that neither sit on a loop nor share a subject
and the comparison count must not move at all. The rule that makes that true is
one line — an entry reaches ``couples`` only through ``on_a_loop`` or
``sharing_subject`` — and it is the line to read if this file is ever
rewritten.

**And growth is not the whole bound, because CAP-7's second comparison set is
degenerate.** Every production belief carries ``subject="self"``, so *"beliefs
sharing a subject"* is the whole stated ledger and a first pass produced the
complete pair set — ``n(n-1)/2``, measured. ``CEILING`` is the bound that does
not depend on either comparison set, spent before it is exceeded, and reported
when it is reached. The degenerate subject set is CAP-7's own defect and is
recorded as deferred; the ceiling is what makes the pass safe regardless of how
it is eventually fixed.

**Nothing here is expensive and nothing here decides.** No model, no store, no
clock: ``now`` and the log's own stamps are arguments (AD-30), and the whole
module is a pure function from four narrowed mappings to a tuple of couples.
Whether two entries *disagree* is a semantic call this file never makes and has
nowhere to make it — that is ``half.consolidate.port``'s, and story 9e's.

**Two entries, in no order.** A ``Couple`` holds ``both`` and offers no way to
ask which is first: there is no accessor, no index, and the id it derives is
built by **exclusive-or over the two digests** rather than by sorting them, so
order-independence is arithmetic rather than a convention somebody has to keep.
``key_of(a, b) == key_of(b, a)`` is asserted, and the whole point is that it
could not have been otherwise.

*"Compared against the loop set"*, read the only way it can be built: a wanting
lives in the log as a belief carrying the loop it belongs to — *"said he would
start running in March"* with ``loop="run-weekly"`` — so the loop set is the
entries this main's live loops are made of. The loop **table** is not touched,
read, or written by this module or anything downstream of it, which is CAP-6's
firewall from the only side this story can breach it from.
"""

from __future__ import annotations

import hashlib
from collections.abc import Collection, Iterable, Mapping
from dataclasses import dataclass, field
from typing import Any, Final

from half.civil import instant
from half.loops.ledger import LOOP
from half.store.records import CLAIM, LEDGER, SUBJECT

#: How many entries a tension links. One number, and it is two — spelled here
#: so the pairing and ``half.tensions.widening.SIDES`` cannot drift into
#: disagreeing about what a tension *is*.
BOTH: Final[int] = 2

#: How many couples one pass may produce, **whatever its comparison sets come
#: to**. The second bound CAP-7 needs and does not name, added by the spec's
#: 2026-09-04 amendment.
#:
#: CAP-7's two comparison sets cannot hold the count down on the data Half
#: actually writes: ``half/actor/runtime.py:700`` sets ``subject="self"`` on
#: every inbound belief and is the only production belief-subject writer, so
#: *"beliefs sharing a subject"* is the whole stated ledger. On a first pass
#: — ``since is None``, every belief on one subject — ``couples`` therefore
#: produced exactly ``n(n-1)/2``: not *"scaling with the ledger"* but literally
#: the complete pair set, measured at 20 → 190, 40 → 780, 80 → 3160, and 398k
#: couples in 8.9s and 79MB at four thousand beliefs. The judgement budget
#: bounded the *bill* while the memory and the CPU were unbounded. That subject
#: set being degenerate is CAP-7's defect and is recorded as deferred; this is
#: the bound that makes the pass safe in the meantime, and it is deliberately
#: **independent of both comparison sets** so that no widening or narrowing of
#: either can move it.
#:
#: **Two thousand and forty-eight.** The judgement budget is twenty-four and
#: roughly half of what the bound produces survives the cheap filter, so a queue
#: of about fifty already saturates the spending — this is forty times that, so
#: no ordinary night and no busy one reaches it, and only the degenerate shape
#: above does. It is half a percent of the pair set an unbounded first pass on
#: four thousand beliefs built, and it holds the arithmetic to single-digit
#: milliseconds.
#:
#: **It cuts before the ranking, and that is the honest trade.** The surprisal
#: order can only rank what the ceiling admitted, so a pass that reaches the
#: ceiling ranks the couples the fold happened to list first rather than the
#: whole set. A ceiling that ranked first would have to build the whole set to
#: rank it, which is the cost this exists to refuse. The pass says when it
#: reached the ceiling for exactly this reason.
#:
#: Pinned by value in ``tests/test_candidates.py`` the way ``JUDGEMENTS`` is.
CEILING: Final[int] = 2048


@dataclass(frozen=True, slots=True)
class Entry:
    """One belief as the minter sees it, and no more of one than that.

    Built from ``records.mint_projection``, so a field that is not on
    ``MINT_VISIBLE`` cannot arrive here even by accident — the narrowing is at
    the door and this type is the shape that fits through it.

    Every field but the id is optional and tolerant, because this is on the read
    path and the read path is tolerant: one belief whose ``subject`` is a number
    must cost that belief its comparison, never the main their pass.
    """

    id: str
    #: The stamp of the belief's most recent record — what *changed since* is
    #: measured against.
    at: str | None = None
    claim: str = ""
    subject: str | None = None
    ledger: str | None = None
    loop: str | None = None


@dataclass(frozen=True, slots=True)
class Couple:
    """Two entries a pass may compare. **The order carries no meaning.**

    There is deliberately no accessor for either half and no positional read
    anywhere in this package: a first and a second is one short step from a
    winner and a loser, and ``half/tensions/widening.py`` records what that step
    costs on an append-only log.
    """

    both: tuple[Entry, ...] = ()

    @property
    def names(self) -> tuple[str, ...]:
        """The two entry ids, in the order they arrived — which means nothing."""
        return tuple(item.id for item in self.both)

    @property
    def id(self) -> str:
        """The tension id this couple would mint, derived from the two ids.

        Derived rather than generated, and that is what makes minting
        idempotent across passes and replayable across builds (AD-30): the same
        two entries always name the same tension, so a second pass over one log
        recognises what the first one wrote rather than minting a duplicate
        under a fresh id. Nothing here reads a clock or a counter.
        """
        return key_of(*self.names)


@dataclass(frozen=True, slots=True)
class Comparison:
    """Every pair one pass may compare, and whether the ceiling cut it short.

    A value rather than a bare tuple, for the reason ``mint.Slate`` is one: a
    pass that stopped at its ceiling and a pass that had exactly that many
    couples to make are different nights, and ``len(within) == CEILING`` cannot
    tell them apart. CAP-7's amended row asks the pass to *say* when it reached
    the ceiling, and a caller can only say what it was told.
    """

    #: The couples, in the belief table's order — which is the fold's, which is
    #: the log's. Never longer than the ceiling.
    within: tuple[Couple, ...] = ()
    #: Whether the ceiling stopped this from producing more. **Not** *"the
    #: ceiling was exactly filled"*: false when the bound had nothing further
    #: to offer, however full it came out.
    ceiling_reached: bool = False


@dataclass(frozen=True, slots=True)
class MintView:
    """One consistent read of everything the minting half needs. Narrowed.

    An allowlist in the shape of a type, following ``half.surface.view``: what
    is not a field here is unreachable from the minter rather than merely
    unread, so a rule that wanted the license, the ceiling or the crisis record
    would have to add a field with a reviewer on it rather than reach through
    an already-open door.
    """

    #: Belief id -> ``records.mint_projection`` of the folded record.
    beliefs: Mapping[str, Mapping[str, Any]] = field(default_factory=dict)
    #: The folded tension table — states and pairs, so a couple that already
    #: carries a live tension is recognised before anything is spent on it.
    tensions: Mapping[str, Mapping[str, Any]] = field(default_factory=dict)
    #: The slugs of this main's live loops. Slugs only: what state a loop is
    #: in, when it last moved and how long its timescale is are CAP-6's
    #: questions, and a minter that could read them could start answering them.
    loops: tuple[str, ...] = ()
    #: The stamp of every ``schedule`` record in this main's log — when each
    #: pass marked itself as having run. Stamps and nothing else (AD-22).
    passes: tuple[str, ...] = ()
    #: Belief and tension ids the main has genuinely erased. An erasure has to
    #: stay an erasure: a couple whose tension was expunged is never minted
    #: again.
    gone: frozenset[str] = frozenset()


#: How much of the exclusive-or the tension id keeps, in hex digits.
#:
#: **It was twelve — forty-eight bits — and that is not enough here.** A couple
#: id is not a display name: ``slate`` reads ``couple.id in view.tensions`` and
#: a hit means *already linked*, so two different pairs that collided would put
#: the second one in ``standing`` — recognised as a disagreement Half has
#: already recorded, never judged, never minted, and silent. There is no
#: message, no count and no way for the main or an operator to see it, which is
#: what makes the width worth arguing about rather than the odds.
#:
#: This is not a claim that a collision has happened. It is that the failure is
#: undetectable, so the width should be one nobody has to compute a birthday
#: bound for: at forty-eight bits a main who accumulates a few hundred thousand
#: couples over a few years is already at a probability with a leading digit.
#: Thirty-two digits is a hundred and twenty-eight bits, where the same
#: arithmetic gives a number no amount of use reaches.
KEY_DIGITS: Final[int] = 32


def key_of(one: str, other: str) -> str:
    """The tension id two entries name, **in no order**.

    Exclusive-or over the two digests rather than a hash of the sorted pair,
    and the difference is the whole neutrality rule made structural: sorting
    would put the two entries in an order, in the one function every mint runs
    through, and a reviewer would have to keep noticing that the order was only
    used for a hash. XOR is commutative, so there is no order to notice.

    **What a collision would do**, said because the truncation makes it a
    question somebody has to answer: two different pairs sharing an id would
    make the second look, to ``mint.slate``, like a couple the fold already
    holds a tension over. It would land in ``standing`` — nothing judged,
    nothing minted, nothing logged, nothing anybody could see. That is why
    ``KEY_DIGITS`` is wide rather than short; a truncation whose failure is
    silent has to be one nobody has to reason about.
    """
    mixed = 0
    for ident in (one, other):
        mixed ^= int(hashlib.sha256(ident.encode("utf-8")).hexdigest(), 16)
    return f"x_{mixed:064x}"[:2 + KEY_DIGITS]


def read(rows: Mapping[str, Mapping[str, Any]] | None) -> dict[str, Entry]:
    """The narrowed belief table as ``Entry`` values, id-keyed. Never raises.

    Tolerant in the way ``half.tensions.ledger.read`` is tolerant, and for the
    same reason: one malformed record must cost that belief its comparison and
    not the whole pass. A field of the wrong type is dropped, not coerced —
    ``subject=7`` is not a subject and inventing ``"7"`` would put that belief
    into a comparison set with everything else numbered seven.
    """
    if not isinstance(rows, Mapping):
        return {}
    found: dict[str, Entry] = {}
    for ident, row in rows.items():
        key = ident if isinstance(ident, str) else str(ident)
        if not key.strip():
            continue
        fields: Mapping[str, Any] = row if isinstance(row, Mapping) else {}
        found[key] = Entry(
            id=key,
            at=_text(fields.get("t")),
            claim=_text(fields.get(CLAIM)) or "",
            subject=_text(fields.get(SUBJECT)),
            ledger=_text(fields.get(LEDGER)),
            loop=_text(fields.get(LOOP)),
        )
    return found


def watermark(stamps: Iterable[object], *, now: object) -> float | None:
    """When this main's **last pass ran**, or ``None`` if none ever has.

    The newest stamp strictly before ``now``. The scheduler writes a main's next
    due time *before* it runs their work (``half.schedule.tick``'s at-most-once
    rule), so the newest stamp of all is this pass's own marker and the one
    before it is the previous pass — which is exactly the line *"new or changed
    since this main's last pass"* has to be drawn at.

    **The stamps are the ones whose tick actually ran a pass**, filtered at the
    door in ``ActorRegistry.mint_view``. They used to be every schedule stamp,
    and the scheduler writes one for the unscheduled, the missed and the
    suspended mains too — so this answered *"when did the scheduler last touch
    this main"*, and a main suspended for one night lost that night's beliefs
    for ever.

    ``None`` means *everything is new*, which is the right answer for a main
    whose first pass this is and the only honest one: a first pass with no prior
    watermark that treated nothing as changed would never mint anything for
    anybody, for ever, and would look exactly like a quiet night.

    **A ``now`` this build cannot read also means ``None``**, and it used to
    mean the opposite. ``edge`` was ``None``, the guard against reading this
    pass's own marker was skipped, and the newest stamp of all — the marker the
    tick had just written — became the watermark: nothing was ever new, and
    nothing said so. Between the two wrong answers, the one that re-derives
    what it already knows beats the one that silently mints nothing for ever,
    and the couple ceiling is what makes it affordable.

    Never raises: a non-iterable ``stamps`` is a view this build cannot read,
    which costs this main their pass's watermark and not their night.
    """
    edge = instant(now) if isinstance(now, str) else None
    if edge is None:
        return None
    found: float | None = None
    try:
        offered = list(stamps)
    except TypeError:
        return None
    for stamp in offered:
        at = instant(stamp) if isinstance(stamp, str) else None
        if at is None or at >= edge:
            continue
        if found is None or at > found:
            found = at
    return found


def fresh(known: Mapping[str, Entry], *, since: float | None) -> tuple[Entry, ...]:
    """The candidate set: every entry new or changed since ``since``.

    ``since is None`` admits everything — see ``watermark``.

    An entry whose stamp this build cannot read is **not** a candidate, and that
    is a deliberate choice between two wrong-looking answers. Admitting it would
    put it into every pass's candidate set for ever, since nothing about it will
    ever come to parse; excluding it costs that one entry its comparison until
    something touches it again, which is the failure that stays bounded.
    """
    return tuple(
        item for item in known.values()
        if _after(item.at, since)
    )


def on_a_loop(
    known: Mapping[str, Entry], *, loops: Collection[str]
) -> tuple[Entry, ...]:
    """CAP-7's first comparison set: the entries this main's live loops are of.

    A wanting is not a row in some other table that a tension could point at —
    it is a belief carrying the loop it belongs to, and *"a disagreement with a
    wanting is mintable"* means a couple one of whose halves is one of these.

    **Nothing here touches the loop table.** The slugs arrive as strings and
    leave unread; no state is consulted, no timescale, no last movement, and
    nothing is written back. A tension is a link between two entries and never
    demotes, freezes or refutes a wanting (CAP-6), and the way that rule breaks
    is a minter that acquired a reason to look at the loop itself.
    """
    try:
        live = {slug for slug in loops if isinstance(slug, str) and slug.strip()}
    except TypeError:
        # A view this build cannot read costs this main their loop set, never
        # their night. ``read`` and ``mint.linked`` already guarded and this did
        # not, so ``slate``'s *"never raises"* was an overclaim: a ``loops``
        # that was not iterable came out of here as a ``TypeError``, through a
        # function whose whole contract is that it does not raise.
        return ()
    if not live:
        return ()
    return tuple(item for item in known.values() if item.loop in live)


def sharing_subject(
    known: Mapping[str, Entry], *, subject: object
) -> tuple[Entry, ...]:
    """CAP-7's second comparison set: the beliefs sharing ``subject``.

    An entry with no subject shares one with nobody — not even with another
    entry that also has none. Two claims Half could not say what they were about
    are not two claims about the same thing, and treating absence as a shared
    value would make the subject set the entire ledger for every unlabelled
    belief in it.
    """
    if not isinstance(subject, str) or not subject.strip():
        return ()
    return tuple(item for item in known.values() if item.subject == subject)


def couples(
    known: Mapping[str, Entry],
    *,
    since: float | None,
    loops: Collection[str],
    ceiling: int = CEILING,
) -> Comparison:
    """Every pair one pass may compare, **and nothing else** (CAP-7).

    One candidate — new or changed — against the loop set and against the
    beliefs sharing its subject. An entry that is on neither list is never
    compared with anything, however large the ledger grows, which is the whole
    of *"never all-pairs"*: the count is a function of the candidate set and of
    the two comparison sets, and adding an unrelated belief adds nothing to any
    of the three.

    Deduplicated by the couple's own derived id, so two candidates that share a
    subject produce one couple rather than two, and a pair reached through both
    the loop set and the subject set is produced once. Order is the belief
    table's, which is the fold's, which is the log's — deterministic, and
    nothing sorts.

    **And it stops at ``ceiling``, which is spent before it is exceeded.** The
    two comparison sets cannot bound this on real data — every production belief
    carries ``subject="self"``, so the subject set is the whole stated ledger and
    a first pass built the complete pair set — so the return is capped, and the
    cap is enforced by *not building* couple number ``ceiling + 1`` rather than
    by trimming a list that was built first. Trimming afterwards would be a
    report rather than a bound, and the 79MB the unbounded version held at four
    thousand beliefs was held before any trimming could have run.
    """
    against = on_a_loop(known, loops=loops)
    found: dict[str, Couple] = {}
    for item in fresh(known, since=since):
        for other in (*against, *sharing_subject(known, subject=item.subject)):
            if other.id == item.id:
                continue
            couple = Couple(both=(item, other))
            if couple.id in found:
                continue
            if len(found) >= ceiling:
                # Spent before it is exceeded: this couple is not built, not
                # held, and not counted.
                return Comparison(within=tuple(found.values()),
                                  ceiling_reached=True)
            found[couple.id] = couple
    return Comparison(within=tuple(found.values()))


def _after(at: object, since: float | None) -> bool:
    """Whether ``at`` is a readable stamp **at or after** ``since``.

    Inclusive, and it was strict. A stamp carries whole seconds, so an entry
    written in the same second as the previous pass's marker compared equal and
    was never a candidate — not on that pass, which had not seen it, and not on
    any later one, which measures against a mark that has moved past it. One
    second of a main's log, gone silently.

    The cost of the inclusive reading is that an entry stamped in exactly that
    second may be offered twice, on two consecutive passes. That costs a
    filter pass and, at worst, one judgement — and the couple that carries a
    live tension is recognised before either — which is the failure that stays
    bounded.
    """
    when = instant(at) if isinstance(at, str) else None
    if when is None:
        return False
    return since is None or when >= since


def _text(value: object) -> str | None:
    """A field as a non-empty string, or ``None``. Never raises."""
    if isinstance(value, str) and value.strip():
        return value
    return None


__all__ = [
    "BOTH",
    "CEILING",
    "KEY_DIGITS",
    "Comparison",
    "Couple",
    "Entry",
    "MintView",
    "couples",
    "fresh",
    "key_of",
    "on_a_loop",
    "read",
    "sharing_subject",
    "watermark",
]
