"""The unsaid queue: what Half is holding, and what would release it (CAP-10).

CAP-10, CAP-5, AD-3, AD-18, AD-22, AD-28, AD-30. *"Insights above the current
license are queued **with release conditions**."* The withholding half was
already built and already enforced — story 4b splits a context by license,
story 5a's ladder decides the rung, AD-28's ceiling caps it — and none of it
could say what was being held or what would change. **Silently withheld is not
queued**, and this module is the difference.

**A view, never a route.** CAP-10's same sentence puts enforcement at context
construction and says so outright, because a queue with a delivery path is a
second route to the wire. So nothing here composes, sends, promotes, appends,
acknowledges or widens what may enter a context. There is no channel reachable
from this file, no store, and no value on it that carries a word of a claim —
an item is an opaque belief id, two rungs and a tuple of condition names, which
is the shape ``half.trust.unasked.Unasked`` has for the same reason (AD-22).
What to *do* when a condition is met is a product question and is deliberately
not answered here; story 11's question engine is the obvious partner, since a
question answered is exactly the acknowledgement a promotion needs.

**The release condition is the ladder's own refusal, asked rather than
restated.** ``half.governance.ladder`` already refuses for enumerable reasons —
the main has not acknowledged it, an `assert` cites nothing, the belief is
quarantined — and a held insight's release condition *is* the precondition its
promotion is missing. Restating those reasons beside the ladder would produce a
second list that agrees with the first until somebody edits one, which is the
failure this codebase has already caught in a denylist, a marker list and a
floor comment. So this module holds **no rule about what a rung requires**. It
holds three *repairs* — an acknowledgement, a citation, a lifted cap — and asks
the ladder, through ``half.context.build.resolve``, which of them the belief
still needs. If the ladder's rules change, the answers change with them on the
same commit.

**How a condition is found: leave one repair out.** A condition is named when
removing its repair from the full set lowers the rung the belief would reach.
That is *necessary in the presence of everything else*, and it is the only
formulation that answers the conjunctive case correctly: `assert` wants a
receipt **and** an acknowledgement, so a belief missing both is raised by
neither repair alone, and *"does this one repair help?"* would report neither as
missing. A belief refused for two reasons names both.

**Quarantine is terminal, and there is no branch here for it.** The pin is
permanent and no path lifts it, so a quarantined belief is not *waiting* for
anything, and listing it with a condition that could be met would be a queue
that lies about what it holds. It is absent, and it is absent because no repair
the ladder accepts raises it: the probe finds nothing, and a belief with no
condition is not an item. Written that way rather than as an ``if quarantined``
guard on purpose — a special case here would be a second reader of the pin with
its own idea of what counts, and a guard the rule above it already forbids the
case of is a guard that cannot fire.

**Computed from the log, never stored.** No queue record, no counter, no field
on ``State`` — the lesson 5b's balance, 9c's decay and 15a's mark all carry. The
only way to get the queue is to fold the log and ask, so a rebuilt store and a
fresh one give the same answer because neither is consulted. Reading it writes
nothing; a ceiling that lifts or an acknowledgement that lands shrinks the queue
on the next fold with no write of its own.

**The ceiling is applied where licenses are resolved** (AD-28), so an item's
rung is the *effective* one. A main capped at `behave` holds more unsaid and the
queue says so, rather than reporting the uncapped answer and being wrong in the
direction that matters. The cap is asked through ``resolve`` — the one door that
answers what rung a belief is effectively on — and never by reaching past it
into the ladder's rule set, which would be a second reader with the ceiling
capping only one of them.

**Depth is inspectable and its reasons are separable.** ``queue`` returns the
items rather than a number, and ``depths`` splits them by condition, because
*"eleven waiting on an acknowledgement"* and *"eleven waiting on a receipt"* are
different situations and a count that cannot tell them apart is the failure
5b's ``queue`` docstring names. Queue depth is itself a signal (glossary).

**What this build can and cannot put in the queue, stated plainly.** The ladder
holds the write monopoly on `license`, `support` and `known_to_main`, and
``promote`` is the only thing that reaches `assert` — so a belief this build
wrote can never be at `assert` while missing a precondition. The
acknowledgement and receipt conditions therefore describe a log **this build did
not write**: an earlier schema, another build, a hand-written record. That is
not a hypothetical to be pruned — ``ladder.own_rung``'s demotion branch exists
for exactly those records and runs on the turn's reply path — but it is worth
saying, because the condition reachable through this product's own doors today
is the ceiling, which aftercare lowers and raises on a live main.

Pure and clockless. No clock, no network, no ambient state, no model: the same
log gives the same queue for ever, and every condition here is structural
(AD-30, AD-4).
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass, field, fields as dataclass_fields
from typing import Any, Final

from half.context.build import resolve
from half.governance.ladder import KNOWN, SUPPORT, Ceiling, License, height
from half.store.fold import State

__all__ = [
    "ACKNOWLEDGEMENT", "CEILING", "CONDITIONS", "RECEIPT", "UNCAPPED",
    "Unsaid", "UnsaidView", "VISIBLE", "depth", "depths", "missing",
    "narrowed_for_unsaid", "queue", "view_fields", "waiting_on",
]


# -- the vocabulary -----------------------------------------------------------
#
# Three names, and **not three rules**. What each rung requires is the ladder's
# and is never written down here; these are the names of the three repairs
# below, so that a caller counting what is held counts constants rather than
# messages — an exception message quotes the value that caused it, and here
# that would be a record out of a main's own log (AD-22).


#: The main has not been told Half holds this. The second `assert` precondition,
#: and the one no amount of evidence pays for: *"the danger of assertion is
#: being unexpected, not being wrong"*. Released by an acknowledgement, which is
#: an event involving the main and is the one thing Half's own inference can
#: never supply.
ACKNOWLEDGEMENT: Final[str] = "acknowledgement"

#: The belief cites nothing in Half's own evidence. The first `assert`
#: precondition: *"an unsupported claim may be asked, never asserted."*
RECEIPT: Final[str] = "receipt"

#: This main's global cap is holding the belief below its own rung (AD-28).
#: Released by the cap being raised, which is aftercare's — story 6c — and
#: never this module's: nothing here can move a ceiling and there is no name for
#: one of the two operations that can.
CEILING: Final[str] = "ceiling"

#: Every condition an item may name, in the order items name them. Closed, and
#: ordered, because two builds folding one log must produce the same queue byte
#: for byte (AD-4, AD-30) and a set would order it by hash seeding.
CONDITIONS: Final[tuple[str, ...]] = (ACKNOWLEDGEMENT, RECEIPT, CEILING)

#: The counterfactual in which this main's cap has been lifted.
#:
#: A ceiling at the top rung, which by AD-28's own arithmetic caps nothing:
#: ``cap`` is a minimum taken against the belief's own license, so the strongest
#: rung subtracts nothing. Spelled as a value rather than as ``ceiling=None``
#: deliberately — inside ``half/`` a literal ``None`` there is a surface
#: declaring itself exempt from AD-28, which ``tests/test_ladder.py`` fails the
#: build for, and this module is asking a hypothetical rather than claiming an
#: exemption.
UNCAPPED: Final[Ceiling] = Ceiling()

#: A hypothetical citation. It is never written, never appended and never
#: returned: it exists only inside ``missing``'s probe, where the question is
#: *"would a receipt help?"* and any receipt answers it. ``has_receipt`` accepts
#: a bare string, so this is the smallest thing that is one.
_A_RECEIPT: Final[str] = "?"


#: What a repair does: a belief and a ceiling in, a belief and a ceiling out.
Repair = Callable[
    [Mapping[str, Any], Ceiling], tuple[Mapping[str, Any], Ceiling]
]


def _acknowledged(
    belief: Mapping[str, Any], ceiling: Ceiling
) -> tuple[Mapping[str, Any], Ceiling]:
    """The belief as it would be if the main had been told."""
    return {**belief, KNOWN: True}, ceiling


def _cited(
    belief: Mapping[str, Any], ceiling: Ceiling
) -> tuple[Mapping[str, Any], Ceiling]:
    """The belief as it would be if it cited Half's own evidence."""
    return {**belief, SUPPORT: [_A_RECEIPT]}, ceiling


def _lifted(
    belief: Mapping[str, Any], ceiling: Ceiling
) -> tuple[Mapping[str, Any], Ceiling]:
    """The belief as it would resolve if this main's cap were raised."""
    return belief, UNCAPPED


#: Each condition and the counterfactual that asks the ladder about it.
#:
#: **This is a list of repairs, not a list of rules**, and the distinction is
#: the whole design. Nothing here says what `assert` requires; each entry says
#: *what would change* and the ladder is then asked whether the change matters.
#: A precondition added to ``promote`` tomorrow makes every existing repair
#: insufficient — the probe finds no repair set that releases the belief, the
#: belief drops out of the queue rather than being listed with a condition that
#: would not release it, and the queue stays honest while it is incomplete.
#: The field names are the ladder's own constants, imported rather than spelled,
#: so a rename there is one edit and not a silently ungoverned probe.
_REPAIRS: Final[tuple[tuple[str, Repair], ...]] = (
    (ACKNOWLEDGEMENT, _acknowledged),
    (RECEIPT, _cited),
    (CEILING, _lifted),
)


# -- one item ------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class Unsaid:
    """One insight Half is holding, and what would release it.

    A value, and deliberately a thin one. It carries the belief's opaque id, the
    rung it is effectively on, the rung it would reach if every named condition
    were met, and the conditions themselves — **and no text**, no claim, no
    topic, no wording. That is not tidiness: it is why this queue cannot become
    a route. There is nothing on it to quote, so a caller that got hold of one
    and reached for a channel would have nothing to put on it (AD-22, CAP-10).

    ``rung`` is the *effective* rung, resolved under this main's ceiling, which
    is what AD-28 means by applying the cap where licenses are resolved. A main
    capped at `behave` sees `behave` here, not the uncapped answer.
    """

    belief_id: str
    #: Where the belief is now, under this main's cap.
    rung: License
    #: Where it would be with every named condition met and the cap lifted.
    would_reach: License
    #: The preconditions it is missing, in ``CONDITIONS`` order. Never empty:
    #: an item with nothing that would release it is not an item — see ``queue``.
    conditions: tuple[str, ...]


# -- what the queue is allowed to see -------------------------------------------


#: The fields of ``State`` the unsaid queue may consult. An allowlist, spelled
#: once, **read by ``narrowed_for_unsaid`` itself** and by
#: ``tests/test_unsaid.py`` — so a new field on ``State`` is invisible here
#: until somebody adds it on purpose.
#:
#: One entry, and that is the point. Story 10's review found ``if
#: state.aftercare is not None: return Silence(...)`` passing the whole suite
#: while permanently silencing a main, and the fix was not another scan: the
#: surface cannot reach what it is not handed. The same line here would be a
#: queue that quietly reported nothing held for a main in aftercare — which is
#: precisely the main holding the most. ``crisis``, ``aftercare``, ``schedule``,
#: ``spoke``, ``touches``, ``loops`` and ``tensions`` are not merely unread:
#: they are absent, and reaching for one is an ``AttributeError``.
VISIBLE: Final[tuple[str, ...]] = ("beliefs",)


@dataclass(frozen=True, slots=True)
class UnsaidView:
    """One main's state, narrowed to what the unsaid queue may consult.

    Frozen, so a caller cannot write into what it was handed and cannot pass a
    mutated copy to the next rule.
    """

    #: The claims Half holds. Not narrowed by field: the whole job here is to
    #: decide which of them is being withheld and why, so narrowing the license
    #: fields away would leave nothing to decide. What is *not* carried onto an
    #: item is the claim text, which is ``Unsaid``'s own rule.
    beliefs: Mapping[str, Mapping[str, Any]] = field(default_factory=dict)
    #: This main's global cap (AD-28). A rung and nothing else: the queue may
    #: know what is being held and may not know why the cap is there. There is
    #: deliberately no field here from which the reason could be inferred — a
    #: queue that could tell an aftercare cap from an operator one is a queue
    #: somebody will branch on.
    ceiling: Ceiling = field(default_factory=Ceiling)


def narrowed_for_unsaid(state: State, ceiling: Ceiling) -> UnsaidView:
    """``state`` reduced to what the queue may consult.

    Copies rather than references, so a view handed out cannot change under its
    reader while the actor keeps working.

    **Built from ``VISIBLE``**, not from a hard-coded keyword argument. That is
    what makes the allowlist load-bearing: adding a field to the constant is the
    whole of admitting it, and a field absent from the constant cannot arrive
    here by somebody widening the constructor call.
    """
    copied: dict[str, Any] = {
        name: {key: dict(value) for key, value in getattr(state, name).items()}
        for name in VISIBLE
    }
    return UnsaidView(ceiling=ceiling, **copied)


def view_fields() -> tuple[str, ...]:
    """The view's own field names. Read by the test that pins the allowlist."""
    return tuple(f.name for f in dataclass_fields(UnsaidView))


# -- the probe ------------------------------------------------------------------


def _rung(belief: Mapping[str, Any], ceiling: Ceiling) -> License:
    """The rung ``belief`` is effectively on under ``ceiling``.

    One call, one door. ``half.context.build.resolve`` is *the* place a license
    becomes a decision (story 4b) and the place AD-28's cap is applied, and
    every question this module asks — what is held, what would release it, what
    a repair would change — is that same question asked of a different
    hypothetical. ``ceiling`` is positional rather than keyword-only on purpose:
    a keyword-only ``ceiling`` would make this helper a *ceiling taker* in
    ``tests/test_ladder.py``'s AD-28 scan, and the scan reads call sites, so the
    starred call in ``missing`` below would read as a call that passes no cap at
    all — a gate failing on a shape it was not written about.
    """
    return resolve(belief, ceiling=ceiling)


def _repaired(
    belief: Mapping[str, Any], ceiling: Ceiling, applied: frozenset[str]
) -> tuple[Mapping[str, Any], Ceiling]:
    """``belief`` and ``ceiling`` with every repair in ``applied`` made.

    In ``_REPAIRS`` order, so the same set of names always produces the same
    hypothetical. The repairs commute today — one writes a field, one writes
    another, one replaces the cap — but relying on that would be a property
    nothing checks.
    """
    for name, repair in _REPAIRS:
        if name in applied:
            belief, ceiling = repair(belief, ceiling)
    return belief, ceiling


def missing(belief: Mapping[str, Any] | Any, *, ceiling: Ceiling) -> tuple[str, ...]:
    """The preconditions ``belief`` is missing, in ``CONDITIONS`` order.

    **Asked of the ladder, never restated.** Every answer here is
    ``half.context.build.resolve`` run over a hypothetical, so the rules about
    what a rung requires live in exactly one place and this function has none of
    them.

    A condition is named when **leaving its repair out lowers the rung the
    belief would otherwise reach** — necessary in the presence of everything
    else. That formulation is what makes the conjunctive case right: `assert`
    wants a receipt *and* an acknowledgement, so a belief missing both is raised
    by neither repair alone, and asking *"does this repair help?"* one at a time
    would report neither. A belief refused for two reasons names both.

    ``()`` — nothing is missing — covers two situations that are the same
    answer, and deliberately so:

    * the belief is already on the rung it would reach, so nothing is being
      held back; and
    * **nothing the ladder accepts would raise it**, which is what a quarantined
      belief is. The pin is permanent, no repair touches it, and the probe finds
      no repair set that helps — so there is no branch here for quarantine and
      no second reader of the pin. It is the same answer a future precondition
      this module knows no repair for would get: an honest silence rather than a
      condition that would not release anything.

    Never raises, on the same terms as ``resolve``: this is read on a main's own
    path and a malformed belief must cost a queue entry, not a turn.
    ``ceiling`` is keyword-only and undefaulted for ``resolve``'s reason — a
    caller that forgets it would compute the queue as though no cap existed,
    which is the one window AD-28 exists to close.
    """
    if not isinstance(belief, Mapping):
        return ()
    every = frozenset(name for name, _ in _REPAIRS)
    best = _rung(*_repaired(belief, ceiling, every))
    if height(best) <= height(_rung(belief, ceiling)):
        return ()
    return tuple(
        name
        for name, _ in _REPAIRS
        if height(_rung(*_repaired(belief, ceiling, every - {name})))
        < height(best)
    )


# -- the queue ------------------------------------------------------------------


def queue(view: UnsaidView) -> tuple[Unsaid, ...]:
    """Everything this main is holding below the rung it would reach, and why.

    **Computed, never stored** (AD-3, AD-30). There is no queue record, no
    counter and no field: the only way to get this is to fold the log and ask
    the ladder, so a ceiling that lifts or an acknowledgement that lands shrinks
    it on the next fold with no write of its own, and two builds reading one log
    produce the same queue.

    **An item is a belief with at least one condition that would release it**,
    and that single rule is the whole of *"quarantine is never an item"*: a
    pinned belief has no such condition, so it is absent — with no branch here
    for the pin, and therefore with no way for this module's idea of quarantine
    to drift from the ladder's. A queue that lied about what is waiting would be
    worse than the silent withholding it replaces.

    **Reading it writes nothing**, promotes nothing and acknowledges nothing.
    There is no store on this path, no channel, and no name here for an append.

    Ordered by belief id, so the queue is a value two folds of one log agree
    about byte for byte rather than one that depends on dict iteration (AD-4).
    A belief the log has erased is simply not in ``view.beliefs`` — the fold
    removes it — so tombstones are respected without a rule here about them.
    """
    found: list[Unsaid] = []
    for belief_id in sorted(view.beliefs):
        belief = view.beliefs[belief_id]
        conditions = missing(belief, ceiling=view.ceiling)
        if not conditions:
            continue
        found.append(
            Unsaid(
                belief_id=belief_id,
                rung=_rung(belief, view.ceiling),
                would_reach=_rung(
                    *_repaired(
                        belief,
                        view.ceiling,
                        frozenset(name for name, _ in _REPAIRS),
                    )
                ),
                conditions=conditions,
            )
        )
    return tuple(found)


def depth(items: Iterable[Unsaid] | None) -> int:
    """How many insights are being held. The signal the glossary names.

    A number, and on its own an inadequate one — which is why it sits beside
    ``depths`` rather than instead of it. *"Eleven insights waiting on an
    acknowledgement"* and *"eleven waiting on a receipt"* are different
    situations, and this cannot tell them apart.
    """
    return sum(1 for _ in (items or ()))


def depths(items: Iterable[Unsaid] | None) -> dict[str, int]:
    """How many are waiting on each condition, keyed by every condition.

    **Every condition, including the ones nobody is waiting on**, so that a
    reason with no items reads as zero rather than as absent — a caller
    comparing two mains, or one main across two days, must not have to tell a
    missing key from an empty one.

    The counts do **not** sum to ``depth`` and are not meant to: a belief
    refused for two reasons is one item and appears under both, which is the
    whole point of keeping the reasons separable.
    """
    held = tuple(items or ())
    return {
        condition: sum(1 for item in held if condition in item.conditions)
        for condition in CONDITIONS
    }


def waiting_on(items: Iterable[Unsaid] | None, condition: str) -> tuple[Unsaid, ...]:
    """The items naming ``condition``, in the order they were given.

    An unknown condition answers empty rather than raising: a caller reading a
    vocabulary this build does not have is asking about nothing Half holds, and
    the honest answer to that is nothing.
    """
    return tuple(item for item in (items or ()) if condition in item.conditions)
