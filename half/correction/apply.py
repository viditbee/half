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

**What Half shows is the removed claim, and nothing around it.** ``shown``
renders the claim **exactly as the record holds it** and not one character more:
no op name, no belief id, no bracket, no framing word, in any language. Until
story 13b it rendered ``retract[b_land]: has not walked that plot since March``
— the internal serialization, on the wire, to a person — and that was the
launch blocker 13b closes. It is now the **fallback** rather than the primary
rendering: the turn composes prose around the claim
(``half.voice.turn``), and where generation fails this is what goes out. The
claim alone degrades to *Half echoes what it knows*, which is honest; a written
sentence would be one language's phrasing shipped worldwide, and silence would
read as broken to somebody who has just written.

**``shows`` is the requirement the composed replacement must satisfy** (CAP-11).
A composed reply must contain the removed claim verbatim, checked before it is
sent, because CAP-11's success criterion is that the main can *see the belief
actually change* — and story 12's aim, the top-ranked belief above a relevance
floor, can mis-target. The main is the only one who can catch that and they can
only catch it if they are shown the words. Prose that says *"I've taken that
out"* without saying *what* sounds better than the claim and verifies nothing.

**The check and the fallback are one function apart, deliberately.** ``shows``
is defined over ``shown``'s own output, so the fallback satisfies the check by
construction: there is no claim for which the check can refuse everything the
turn is able to send. A check and a fallback that could disagree is a check that
silences a main every time it fires.

**Why quoting the claim is not the AD-18 hole it resembles.** AD-18 forbids
`behave` text inside a *constructed context* — the thing a model is handed and
may quote from. Nothing on this path constructs one: no model runs, no context
is built, and the string is a rendering of a record the main has just told Half
is wrong. CAP-11 requires it in as many words (*"Half shows what it removed"*),
and it is also the one thing that makes a mis-aimed correction visible: the main
sees what left and can correct the correction. Withholding it would trade an
audit the main can perform for a rule that was written about a different object.

**An erasure shows the claim too, and this reverses story 12.** That story
argued that echoing the text back on the turn the main asked for it to be gone
was the one place quoting would be wrong, and rendered the op and the id
instead. Story 13b's matrix says otherwise — *the claim is shown before the
body is gone* — and the argument for the reversal is the one CAP-11 rests on
everywhere else, holding here with more force rather than less. An erasure is
the **only** removal that cannot be corrected by correcting the correction: the
body is tombstoned and there is nothing left to reverse and nothing left to
show. So the confirmation turn is the last moment at which a mis-aimed erasure
can be caught, and under story 12 that moment carried no words at all —
``expunge?[b_x]`` on the asking turn and ``expunge[b_x]`` on the confirming
one, so a main destroyed a belief they were never shown. The claim is read off
the fold *before* ``Store.expunge`` runs, which is why it can be shown at all.

What stays distinct between the three ops is what the log records — the op
itself, and the attribution stamps ``half.correction.attribute`` folds — rather
than a marker on the wire. The wire carries prose or the claim, and neither has
a place for an op name that is not a word in anybody's language.

Pure. No clock, no store, no model, no network — ``fields`` and ``record_id``
take the caller's ``t``, and the append itself happens where the main's mutex is
already held (``half.actor.runtime._pipeline``).
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from enum import StrEnum
from typing import Any, Final

from half.context.channels import sanitize
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

#: What ``proposed`` puts around an id, and what marks its line as a
#: **proposal**. Punctuation, deliberately: this module contains no word a main
#: could read that is not either the op's own name from the closed vocabulary or
#: the claim as the record holds it.
#:
#: **Nothing in ``shown`` uses them any more** (story 13b). A removal is now the
#: claim and nothing else, because a bracket and an op name on the wire are the
#: internal serialization reaching a person. The proposal still renders one, and
#: that is recorded as **deferred** rather than fixed: a proposal deliberately
#: withholds the claim (see ``proposed``), so there is nothing to compose prose
#: around and nothing to fall back to — dropping the line would silence the one
#: question that stands between an inference and a destroyed body. It needs its
#: own story, not a commit inside this one.
_OPEN: Final[str] = "["
_CLOSE: Final[str] = "]"
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
    #: The belief's claim exactly as the record holds it, or ``""`` when the
    #: record has none this build can read.
    #:
    #: **An erasure carries it too** (story 13b), and it is read off the fold
    #: *before* ``Store.expunge`` tombstones the body — which is the whole of
    #: why the ordering matters. The confirmation turn is the last moment a
    #: mis-aimed erasure can be caught, and it is the one removal that cannot be
    #: undone by correcting the correction.
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
        claim=claim if isinstance(claim, str) else "",
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

    **It carries no claim, and that is the AD-18 bound made structural.**
    ``proposed`` renders the op and the id and deliberately not the claim — a
    proposal is Half *asking*, on a turn where nothing was removed and a
    classifier may have read an ordinary message as a correction, so quoting a
    `behave` belief there would put its text on the wire for an inference. With
    the field populated that bound was one function call from being broken:
    ``shown`` on a candidate would have rendered it. Until story 13b the
    emptying was here and applied to erasures only; that story needed
    ``plan``'s erasure to carry the claim — the confirming turn is the last
    moment a mis-aimed erasure can be caught — and dropped it from both. A
    proposal has no reader for it either way: ``half.actor.runtime._removal``
    reads a standing candidate's ``target``, ``meaning`` and ``source``, and the
    claim it eventually shows is read off the fold by ``plan`` when the main
    answers.

    So it is also one less copy of a belief's own words held in memory across
    turns — for a candidate that is, half the time, a proposal to destroy the
    body it came from.
    """
    if not isinstance(target, str) or not target.strip():
        return None
    if not isinstance(belief, Mapping):
        return None
    attribution = ATTRIBUTION_FOR_MEANING[meaning]
    op = Op.EXPUNGE if meaning is Meaning.ERASE else op_for(attribution)
    return Removal(
        target=target,
        op=op,
        attribution=attribution,
        meaning=meaning,
        claim="",
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
    """The claim Half shows for a removal, or ``""``. **The fallback** (13b).

    The claim as the record holds it and nothing around it: no op name, no
    belief id, no bracket, no framing word, in any language. Until story 13b
    this rendered ``retract[b_land]: has not walked that plot since March`` and
    that string went to a person, which is the launch blocker 13b closes.

    It is the fallback rather than the primary rendering. ``half.voice.turn``
    composes prose around the claim and sends this when it cannot — the claim
    is already in the main's own language, because it came from them, so it
    needs no template and belongs to no locale.

    ``""`` is the answer for a record whose claim this build cannot read, and it
    is the one case where a waiting main is answered with silence rather than
    with a word of Half's own.

    **Flattened, and the flattening is a fixed point of
    ``half.context.channels.sanitize``.** That is not tidiness and it is not the
    forgery guard it used to be — with the marker gone there is no second line
    to forge. It is what keeps ``shows`` and the composed reply from disagreeing:
    the claim reaches the model through a ``Content``, which sanitizes at
    construction, and a check looking for an unsanitized string against text
    built from a sanitized one would refuse every composed correction reply ever
    written, for ever, with a green suite. Sharing the function rather than
    approximating it is the same choice ``half.voice.leak`` makes about the
    withheld rule.
    """
    if removal is None:
        return ""
    return _flattened(removal.claim)


def shows(text: object, removal: Removal | str | None) -> bool:
    """Whether ``text`` shows what ``removal`` removed (CAP-11).

    **This is the check that runs**, and story 13b's review loop is why that
    sentence is here. The first build of the turn re-implemented the comparison
    inline (``if show and show not in composed.text``) while every *"verbatim
    means verbatim"* case in the suite was written against this function. The
    two agreed by coincidence and nothing held them together: re-casing one of
    them left the whole suite green and let
    ``HAS NOT WALKED THAT PLOT SINCE MARCH — taken out.`` through as a composed
    reply. So ``half.voice.turn`` calls this, and the second argument is a
    ``Removal`` where the caller holds one and the **claim ``shown`` already
    rendered** where it holds that instead — one comparison, reachable from both
    of the two places that need it.

    **The requirement a composed correction reply must satisfy, checked before
    it is sent** — a property of what goes on the wire rather than a hope about
    what was generated. CAP-11 exists so the main can *see the belief actually
    change*; story 12 aims at the top-ranked belief above a relevance floor and
    can mis-target; the main is the only one who can catch that, and only if
    they are shown the words. *"I've taken that out"* sounds better than the
    claim and verifies nothing.

    Defined over ``shown``'s own output, so **the fallback satisfies it by
    construction**. There is deliberately no second normalization here: a check
    that folded, trimmed or re-cased before comparing would accept prose that
    does not actually contain the main's words, which is the whole thing being
    checked.

    ``True`` when there is nothing to show — a record with no readable claim
    removes nothing anybody can be shown, and refusing every possible reply for
    it would answer a main's correction with silence.
    """
    claim = _flattened(removal) if isinstance(removal, str) else shown(removal)
    if not claim:
        return True
    return isinstance(text, str) and claim in text


def proposed(removal: Removal | None) -> str:
    """The one line Half says when it is **asking**, or ``""``.

    The op's name with a question mark on it and the belief's id, and **not the
    claim** — which is the bound on the route story 12 opens through AD-18.

    A *removal* shows the claim because the main needs the words to catch a
    mis-aim: the belief is gone, and seeing what went is the only audit they
    have. A *proposal* is Half asking, on a turn where nothing was removed and
    the main may have said nothing corrective at all — a classifier reading an
    ordinary message would otherwise put a `behave` claim on the wire. The id is
    enough to ask about.

    **This line is still the internal serialization, and story 13b does not fix
    it.** Recorded here rather than discovered later: 13b's Never list forbids a
    label or a belief id on the wire, and this is one. It is left because
    neither available answer is right inside this story. Composing prose needs
    something to compose *from*, and a proposal withholds the claim by design,
    so the material is an op name and an opaque id; and dropping the line
    silences the one question that stands between an inference and a destroyed
    body (``NEEDS_ANSWER``). What it needs is a story that decides what Half may
    show when it is asking about a belief it may not quote — which is a licence
    question, not a wording one, and belongs beside CAP-10's quarantine rule
    rather than inside a story about prose.
    """
    if removal is None:
        return ""
    mark = _ASKING
    return f"{removal.op.value}{mark}{_OPEN}{removal.target}{_CLOSE}"


def _flattened(claim: str) -> str:
    """``claim`` with everything that could start a line folded to a space.

    ``half.context.channels.sanitize``, imported rather than approximated. It
    replaces every breaking character — the control characters, the line and
    paragraph separators — with one space and trims the ends, keeping every
    printable character in order: no truncation, and no escaping scheme to get
    wrong.

    **Sharing it is what makes the inclusion check possible at all.** The claim
    reaches the model as a ``Content``, which sanitizes at construction, so a
    fallback normalized any other way would be a string the composed reply can
    never contain — the check would refuse everything and every correction
    would fall back, for ever, with nothing failing.

    A claim with a line break in it is still folded to one line, which is what
    keeps a removal one message rather than two. What it no longer guards
    against is a forged marker line, because story 13b took the marker off the
    wire: there is nothing left to forge.
    """
    return sanitize(claim) if isinstance(claim, str) else ""
