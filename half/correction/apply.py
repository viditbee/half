"""What a correction becomes: one append, and the claim Half shows (CAP-11).

Three things live here, and each is a rule the story states:

**A correction that reached this path only through inference cannot be
applied, and neither can an erasure however it was recognised.** ``plan``
refuses both unless the main answered — not by convention but by raising, so an
unconfirmed removal of either kind is unrepresentable rather than merely
discouraged.

The second refusal is a deliberate tightening past the story's own matrix, and
the reason is that the recovery argument below is **false for exactly one of
the four meanings**. A `retract` or a `revise` can be corrected by the main
correcting the correction, because the claim is still in the log; an `expunge`
tombstones the body, so there is nothing left to reverse and nothing left to
show. CAP-10's rule is *never act on inference alone*; this is the same rule
one step further — *never destroy a body without the main's answer*. This is CAP-10's quarantine rule applied to the same class
of problem: *detection produces a candidate and Half asks*. A new inference
route added by a later story reaches this function like every other and is
refused by it, which is what makes the rule structural instead of a paragraph
about today's callers.

**Removal does not wait on attribution.** ``plan`` takes a meaning and produces
a removal whatever the cause turns out to be; ``WRONG`` — the main negating the
belief without saying which — removes it and records the cause as not yet known.
The alternative is a Half that answers *"that's wrong"* with a clarifying
question before doing anything, which leaves a known-wrong belief shaping
contexts while the exchange resolves.

**What Half shows is the removed claim, quoted.** ``shown`` renders one line:
the op's own name from the closed vocabulary, the belief's id, and the claim
**exactly as the record holds it**. There is no sentence here, no template and
no language — the same shape ``half.context.channels.render_line`` already puts
on the wire, and for the same reason. Composing prose about a correction is
where an apology gets invented for a main who simply changed.

**Why quoting the claim is not the AD-18 hole it resembles.** AD-18 forbids
`behave` text inside a *constructed context* — the thing a model is handed and
may quote from. Nothing on this path constructs one: no model runs, no context
is built, and the string is a rendering of a record the main has just told Half
is wrong. CAP-11 requires it in as many words (*"Half shows what it removed"*),
and it is also the one thing that makes a mis-aimed correction visible: the main
sees what left and can correct the correction. Withholding it would trade an
audit the main can perform for a rule that was written about a different object.

**An erasure shows no claim.** ``expunge`` tombstones the body, and echoing the
text back on the turn the main asked for it to be gone is the one place quoting
would be wrong. The line names the op and the id, which is the *distinct in what
Half says* the glossary asks for.

Pure. No clock, no store, no model, no network — ``fields`` and ``record_id``
take the caller's ``t``, and the append itself happens where the main's mutex is
already held (``half.actor.runtime._pipeline``).
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from enum import StrEnum
from typing import Any, Final

from half.correction.attribute import Attribution, fields_for, op_for
from half.correction.signals import Meaning
from half.errors import CorrectionError
from half.retrieval.strands import STRAND_FLOOR
from half.store.ops import Op
from half.store.records import LEDGER, STATED, TARGET

#: The field a belief's own words live in.
CLAIM: Final[str] = "claim"

#: The prefix an appended correction's record id carries. Two letters and the
#: caller's stamp, exactly as ``touch`` (``tc_``) and ``asked`` (``qa_``) build
#: theirs: the id names the *append* and never the belief, so a tombstone on one
#: cannot land in the belief namespace.
ID_PREFIX: Final[str] = "co_"

#: What ``shown`` puts around an id, and what marks a line as a **proposal**
#: rather than a removal. Punctuation, deliberately: this module contains no
#: word a main could read that is not either the op's own name from the closed
#: vocabulary or the claim as the record holds it.
_OPEN: Final[str] = "["
_CLOSE: Final[str] = "]"
_JOIN: Final[str] = ": "
_ASKING: Final[str] = "?"

#: Every character that starts a new line somewhere. Folded out of a claim
#: before it is shown — see ``_flattened``.
_LINE_BREAKS: Final[frozenset[str]] = frozenset(
    "\n\r\u2028\u2029\u0085\v\f"
)


class Source(StrEnum):
    """How a correction reached this path. Two values, and they are not equal.

    ``TABLE`` is the offline table's answer: an explicit correction, acted on
    directly. ``INFERRED`` is the classifier's, and it is a **candidate** — see
    ``plan``, which refuses to build a removal from one the main has not
    answered.
    """

    TABLE = "table"
    INFERRED = "inferred"


#: The meanings that may **not** be applied without the main's answer, whatever
#: recognised them. One entry, and it is the erasure: an erasure destroys the
#: body, so *"the main can correct the correction"* — the argument that makes a
#: mis-aimed removal recoverable — is not available for it.
NEEDS_ANSWER: Final[frozenset[Meaning]] = frozenset({Meaning.ERASE})

#: Which meaning becomes which attribution. ``WRONG`` maps to the honest doubt,
#: which is the one entry in this table that is a decision rather than a
#: translation: the main said it is wrong and did not say why, so nothing here
#: says why either.
ATTRIBUTION_FOR_MEANING: Final[dict[Meaning, Attribution]] = {
    Meaning.NEVER_TRUE: Attribution.HALF_WAS_WRONG,
    Meaning.CHANGED: Attribution.MAIN_CHANGED,
    Meaning.WRONG: Attribution.NOT_YET_KNOWN,
    Meaning.ERASE: Attribution.NOT_YET_KNOWN,
}


@dataclass(frozen=True, slots=True)
class Removal:
    """One belief leaving the fold: what, how, why, and the words to show.

    Frozen, and every field is decided at construction. Nothing downstream may
    turn a retract into a revise or attach a cause afterwards — an attribution
    that can be edited after the fact is an attribution somebody can supply
    later from something other than the main's own words.
    """

    target: str
    op: Op
    attribution: Attribution
    #: What the main's message meant. Carried so that a proposal can be applied
    #: as *itself* once the answer comes back, rather than re-derived from a
    #: message that no longer exists — an erasure the main confirmed has to
    #: erase, not retract.
    meaning: Meaning = Meaning.WRONG
    #: The belief's claim exactly as the record holds it, or ``""`` for an
    #: erasure, whose body is tombstoned.
    claim: str = ""
    source: Source = Source.TABLE

    @property
    def erases(self) -> bool:
        """Whether this is an erasure rather than a correction.

        The caller dispatches on it: an erasure goes through the store's own
        validate-then-erase path, which tombstones the bodies, where a
        correction is an ordinary append.
        """
        return self.op is Op.EXPUNGE


def aim(candidates: Iterable[Any], *, exclude: Iterable[str] = ()) -> str:
    """Which belief this turn's correction is about, or ``""``. Pure.

    **A correction is about what the conversation is about**, and that is the
    whole rule. Two filters, and each was a defect before it was a filter.

    *A relevance floor.* ``Candidate.weights["strand"]`` is
    ``STRAND_FLOOR`` for a belief on no strand the live conversation touches,
    and above it for one on a strand it does. Taking the top of the ranked set
    without looking meant a message about email expunged *"keeps bees in the
    garden"*: with no term match the backstop supplies every belief the main
    has, in an order that says nothing about this turn. The floor is
    ``half.retrieval``'s own — not a number invented here — and above it the
    ranked order decides, because that is what ranking is for.

    A bare *"that's wrong"* in a fresh conversation therefore aims at **nothing**
    and removes nothing, which is correct: *that* has no antecedent, and Half
    inventing one is how a correction lands on a belief the main never
    questioned.

    *Not the message that carried it.* Every inbound message is recorded as a
    belief on the stated ledger, so the second *"that's wrong"* in a
    conversation retracted the belief holding the text *"that's wrong"*. This
    turn's own id is excluded by the caller, and the newest stated-ledger record
    — the previous turn's message — is excluded here, because a correction is
    never about the sentence that provoked it.

    Never raises: it runs on the turn's own path over values ranking produced,
    and a candidate this build cannot read is one it does not aim at.
    """
    skip = set(exclude)
    kept: list[Any] = []
    newest_stated: tuple[str, str] | None = None
    for candidate in candidates or ():
        ident = getattr(candidate, "id", "")
        if not isinstance(ident, str) or not ident or ident in skip:
            continue
        record = getattr(candidate, "belief", None)
        if isinstance(record, Mapping) and record.get(LEDGER) == STATED:
            stamp = record.get("t")
            if isinstance(stamp, str) and (
                newest_stated is None or stamp > newest_stated[0]
            ):
                newest_stated = (stamp, ident)
        weights = getattr(candidate, "weights", None)
        strand = weights.get("strand") if isinstance(weights, Mapping) else None
        if not isinstance(strand, (int, float)) or isinstance(strand, bool):
            continue
        if strand <= STRAND_FLOOR:
            continue
        kept.append(candidate)
    latest = newest_stated[1] if newest_stated is not None else None
    for candidate in kept:
        if candidate.id != latest:
            return str(candidate.id)
    return ""


def plan(
    meaning: Meaning,
    *,
    target: str,
    belief: Mapping[str, Any] | None,
    source: Source = Source.TABLE,
    confirmed: bool = False,
) -> Removal | None:
    """The removal ``meaning`` calls for, or ``None`` if there is nothing to do.

    ``None`` covers two matrix rows at once, and neither is an error:

    * **no such belief.** A correction naming nothing Half holds removes
      nothing, and the main is not shown an error — being told *"I have no
      record of that"* in answer to *"that's wrong"* is Half arguing.
    * **already corrected.** The belief has already left the fold, so ``belief``
      is absent and there is no second removal and no second message. Idempotent
      by the same branch, because *"gone"* and *"never held"* are the same
      question asked of the current fold.

    **Refuses an inferred correction the main has not answered.** That is the
    story's central rule and it is enforced here — at the one function that
    turns a meaning into a removal — rather than at the caller, because a caller
    is a thing a later story adds another of.
    """
    if source is Source.INFERRED and not confirmed:
        raise CorrectionError(
            "an inferred correction may not be applied. Detection past the "
            "offline table produces a candidate: Half shows what it would "
            "remove and asks, and the main's answer decides (CAP-10). Acting "
            "on an inferred negation deletes something the main actually "
            "believes"
        )
    if meaning in NEEDS_ANSWER and not confirmed:
        raise CorrectionError(
            "an erasure may not be applied without the main's answer, however "
            "it was recognised. Every other correction is recoverable because "
            "the claim stays in the log and the main can correct the "
            "correction; an erasure tombstones the body, so a mis-aimed one "
            "leaves nothing to reverse and nothing to show"
        )
    if not isinstance(target, str) or not target.strip():
        return None
    if not isinstance(belief, Mapping):
        return None
    attribution = ATTRIBUTION_FOR_MEANING[meaning]
    op = Op.EXPUNGE if meaning is Meaning.ERASE else op_for(attribution)
    claim = belief.get(CLAIM)
    return Removal(
        target=target,
        op=op,
        attribution=attribution,
        meaning=meaning,
        claim="" if op is Op.EXPUNGE or not isinstance(claim, str) else claim,
        source=source,
    )


def proposal(
    target: str,
    belief: Mapping[str, Any] | None,
    *,
    meaning: Meaning = Meaning.WRONG,
    source: Source = Source.INFERRED,
) -> Removal | None:
    """What a correction Half must **ask** about would do, as a candidate.

    A ``Removal`` built for showing and never for appending: it carries no
    confirmation, so handing it to ``fields`` is fine — that only reads the
    target and the attribution — while re-planning it without the main's answer
    raises.

    Two routes reach it, and the ``meaning`` is what tells them apart once the
    answer comes back. A **classifier** reading produces ``WRONG`` with the
    cause unknown, because a model's reading of a message settles neither
    whether Half was wrong nor whether the main changed. The **table** reaches
    it only for an erasure, which is applied as an erasure or not at all.
    """
    if not isinstance(target, str) or not target.strip():
        return None
    if not isinstance(belief, Mapping):
        return None
    attribution = ATTRIBUTION_FOR_MEANING[meaning]
    op = Op.EXPUNGE if meaning is Meaning.ERASE else op_for(attribution)
    claim = belief.get(CLAIM)
    return Removal(
        target=target,
        op=op,
        attribution=attribution,
        meaning=meaning,
        claim="" if op is Op.EXPUNGE or not isinstance(claim, str) else claim,
        source=source,
    )


def fields(removal: Removal, *, t: str) -> dict[str, Any]:
    """The record fields this correction appends.

    The target, and the attribution's stamp if there is one. Nothing else: a
    correction says what left and why, and a claim, a license or a support set
    written here would be belief content copied onto the record that removed it
    — permanent, and unreachable by any later correction (AD-22).
    """
    return {TARGET: removal.target, **fields_for(removal.attribution, t=t)}


def record_id(removal: Removal, *, t: str) -> str:
    """The append's own id. Never the belief's.

    Built from the stamp **and the target**, so a tombstone on this record
    enters nothing into the belief namespace — the failure ``fold._APPEND_KEYED``
    exists for, avoided here by construction instead of by joining that set.

    The target is the discriminator, in the shape ``Store.expunge`` already uses
    (``x_<target>_<t>``). Without it two corrections landing inside one second —
    two messages, two different beliefs — shared an id and were appended
    silently, which is two records the log cannot tell apart.
    """
    return f"{ID_PREFIX}{removal.target}_{t}"


def shown(removal: Removal | None) -> str:
    """The one line Half says about a removal, or ``""``.

    ``op[target]: claim`` — the op's name from the closed vocabulary, the id,
    and the claim as the record holds it. An erasure shows no claim.

    The three ops stay distinct in what Half says because the op's own name is
    what the line is built from: there is no branch here that could render a
    ``revise`` and a ``retract`` identically, and no sentence either could be
    dressed in.
    """
    if removal is None:
        return ""
    return _line(removal, asking=False)


def proposed(removal: Removal | None) -> str:
    """The one line Half says when it is **asking**, or ``""``.

    The same rendering with a question mark on the op, and **without the
    claim** — which is the one asymmetry between the two, and it is the bound on
    the route this story opens through AD-18.

    A *removal* shows the claim because the main needs the words to catch a
    mis-aim: the belief is gone, and seeing what went is the only audit they
    have. A *proposal* is Half asking, on a turn where nothing was removed and
    the main may have said nothing corrective at all — a classifier reading an
    ordinary message would otherwise put a `behave` claim on the wire. The id is
    enough to ask about.
    """
    if removal is None:
        return ""
    return _line(removal, asking=True)


def _line(removal: Removal, *, asking: bool) -> str:
    """The single serialization, shared by both callers.

    One function for the reason ``half.actor.runtime.question_line`` gives:
    two renderings of one item is how a guard that scans one string ends up
    admitting a different one.
    """
    mark = _ASKING if asking else ""
    head = f"{removal.op.value}{mark}{_OPEN}{removal.target}{_CLOSE}"
    if asking or not removal.claim:
        return head
    return f"{head}{_JOIN}{_flattened(removal.claim)}"


def _flattened(claim: str) -> str:
    """``claim`` with every line break folded to a space.

    **The one thing done to the claim, and it is a forgery guard rather than
    tidiness.** The marker is what distinguishes a real removal from an invented
    one, and a claim carrying a newline forges a second marker line:

        noted.
        retract[b_x]: line one
        retract[b_fake]: totally made up

    Claims come from the main's own messages *and* from ingested sources, so the
    text is attacker-influenced. Folding the breaks keeps the whole claim — no
    truncation, no escaping scheme to get wrong — while making it structurally
    impossible for one claim to occupy two lines.

    The same characters ``half.text`` treats as invisible are folded here, for
    the reason ``half.crisis.signals`` folds them: a line separator that is not
    ``\n`` is still a line break to whatever renders the message.
    """
    return "".join(" " if char in _LINE_BREAKS else char for char in claim)
