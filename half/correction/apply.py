"""What a correction becomes: one append, and the claim Half shows (CAP-11).

Three things live here, and each is a rule the story states:

**A correction that reached this path only through inference cannot be
applied.** ``plan`` refuses it unless the main answered — not by convention but
by raising, so an unconfirmed inferred removal is unrepresentable rather than
merely discouraged. This is CAP-10's quarantine rule applied to the same class
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
already held (``half.actor.runtime``'s turn path).
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from typing import Any, Final

from half.correction.attribute import Attribution, fields_for, op_for
from half.correction.signals import Meaning
from half.errors import CorrectionError
from half.store.ops import Op
from half.store.records import TARGET

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


class Source(StrEnum):
    """How a correction reached this path. Two values, and they are not equal.

    ``TABLE`` is the offline table's answer: an explicit correction, acted on
    directly. ``INFERRED`` is the classifier's, and it is a **candidate** — see
    ``plan``, which refuses to build a removal from one the main has not
    answered.
    """

    TABLE = "table"
    INFERRED = "inferred"


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
        claim="" if op is Op.EXPUNGE or not isinstance(claim, str) else claim,
        source=source,
    )


def proposal(target: str, belief: Mapping[str, Any] | None) -> Removal | None:
    """What an **inferred** correction would remove, as a candidate.

    A ``Removal`` built for showing and never for appending: it carries
    ``Source.INFERRED`` and no confirmation, so handing it to ``fields`` is
    fine — that only reads the target and the attribution — while re-planning
    it without the main's answer raises. The op is a plain ``retract`` with the
    cause unknown, because a model's reading of a message settles neither
    whether Half was wrong nor whether the main changed.
    """
    if not isinstance(target, str) or not target.strip():
        return None
    if not isinstance(belief, Mapping):
        return None
    claim = belief.get(CLAIM)
    return Removal(
        target=target,
        op=op_for(Attribution.NOT_YET_KNOWN),
        attribution=Attribution.NOT_YET_KNOWN,
        claim=claim if isinstance(claim, str) else "",
        source=Source.INFERRED,
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

    Built from the stamp, so a tombstone on this record enters nothing into the
    belief namespace — the failure ``fold._APPEND_KEYED`` exists for, avoided
    here by construction instead of by joining that set.
    """
    return f"{ID_PREFIX}{t}"


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

    The same rendering with a question mark on the op, so what Half shows the
    main is exactly what it would remove — the claim as recorded, never a
    paraphrase of it — and the difference between a proposal and a removal is
    one character rather than two renderings that could drift.
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
    if not removal.claim:
        return head
    return f"{head}{_JOIN}{removal.claim}"
