"""The license ladder: which rung a belief may occupy (CAP-10, AD-28).

Story 4b made ``half.context.build.resolve`` the single place a license becomes
a decision. It read a field. This module is the rule set that decision now
consults, and the difference is the whole story: `assert` stops being a field
anyone can set and becomes something a belief has to *earn*.

**Two independent preconditions for `assert`, and both are required.** A
citation into Half's own evidence — the support set — *and* the main already
knowing Half holds the belief. The constitution states them separately because
they fail separately: *"assert only with receipts"* and *"the danger of
assertion is being unexpected, not being wrong"*. A correct, well-evidenced
claim the main has never heard Half think is exactly the trust-destroying case,
so being right is not sufficient and is not treated as sufficient here.

**Half's own inference never licenses assertion.** Nothing in this module reads
``independent``, ``last_corroborated``, or any other count. There is no
threshold that promotes, because a threshold would make promotion something
Half does to itself while the main is absent. Promotion takes an
acknowledgement, and ``promote`` refuses without one.

**A belief that cannot assert may still ask.** An `assert`-licensed belief
failing either precondition resolves to `ask`, not to silence:
*"an unsupported claim may be asked, never asserted."* `ask` material reaches a
context as a topic and never as wording, so nothing it carries is quotable —
the demotion costs Half the right to state the claim, not the right to raise
it. A *malformed* license is different and resolves to `behave`: unknown is
unknown, and the weakest rung is what unknown means.

**Quarantine is a pinned field, not an exception list.** One flag on the belief,
pinning it at `behave` permanently. An exception list is a second place state
lives, which the fold does not describe and replay does not reproduce.
Inference may produce a *candidate*; applying one takes a candidate **and** an
affirmative answer from the main, which is why ``quarantine`` cannot be called
with either missing. Nothing here clears the flag — permanence is the absence
of a function, not a check somebody has to remember.

**The ceiling caps and never promotes** (AD-28). One per actor, applied here,
where licenses are resolved — never where messages are composed. That placement
is the whole of AD-28: aftercare implemented as per-feature suppression is
forgotten by the next feature, so a new surface must not be *able* to bypass
it. Raising the ceiling lifts nothing: it is a minimum taken against a belief's
own rung, so the belief's own license is always the upper bound.

**Every uncertainty resolves downward.** Unknown, missing and malformed
licenses are `behave`. An unreadable quarantine flag is a quarantine flag. A
ceiling whose value this build cannot parse is `behave` — the most restrictive
reading, because a ceiling exists to restrict. But a *permission-granting*
field is read strictly in the other direction: only an explicit ``True``
records that the main knows.

Pure and stdlib-only. No clock, no network, no ambient state, no model, and
nothing here writes: the writing half returns the **fields of an append** and
the caller appends them (AD-3, AD-30). A license change is therefore a log
record like any other, and replay reproduces it rather than re-deriving it.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from typing import Any, Final

from half.errors import LadderError
from half.store.records import QUARANTINED, RESERVED, pinned


class License(StrEnum):
    """What a belief or tension permits (CAP-10, glossary).

    Ordered weakest first, and the weakest is the default *and* the failure
    mode: an unknown, missing or malformed value resolves to `BEHAVE`, never
    upward. Defined here rather than beside the context channels because the
    rungs are the ladder's own vocabulary — ``half.context.channels``
    re-exports it, so every existing importer is unaffected.
    """

    #: Half acts on it silently. Most beliefs never leave this rung.
    BEHAVE = "behave"
    #: Half may raise it as a question.
    ASK = "ask"
    #: Half may state it. Rare, and only when the main already knows.
    ASSERT = "assert"


#: The rungs, weakest first. The single ordering: everything that compares two
#: licenses does it through this tuple, so there is no second opinion about
#: which of two rungs is stronger.
RUNGS: Final[tuple[License, ...]] = (License.BEHAVE, License.ASK, License.ASSERT)

#: The default, and the failure mode.
FLOOR: Final[License] = RUNGS[0]

#: The strongest rung — and therefore the ceiling that caps nothing.
TOP: Final[License] = RUNGS[-1]

_HEIGHT: Final[dict[License, int]] = {rung: i for i, rung in enumerate(RUNGS)}

#: Belief fields the ladder reads. Named once so a rename is one edit and a
#: typo is not a silently ungoverned belief. ``QUARANTINED`` is imported from
#: ``half.store.records`` rather than spelled again here: the fold has to carry
#: that field forward to make the pin permanent, so both layers need the name
#: and only one of them may own it.
LICENSE: Final[str] = "license"
SUPPORT: Final[str] = "support"
KNOWN: Final[str] = "known_to_main"

#: The field a ceiling record carries.
RUNG: Final[str] = "rung"


# -- reading: the rung a belief actually permits ------------------------------


def height(rung: License) -> int:
    """How far up the ladder ``rung`` sits. Comparison, not arithmetic."""
    return _HEIGHT[rung]


def weaker(one: License, other: License) -> License:
    """The lower of two rungs. The only way two licenses are ever combined —
    there is no operation here that returns the stronger of two."""
    return one if _HEIGHT[one] <= _HEIGHT[other] else other


def rung_of(value: object) -> License:
    """The rung ``value`` names, or `behave`.

    Absent, misspelled, wrongly typed, or a value from a future schema all
    resolve to `behave`. Never raises: the only caller is on the turn's reply
    path, ahead of the append that records the main's message, so an exception
    here costs the main both their answer and their message.
    """
    if isinstance(value, License):
        return value
    if isinstance(value, str):
        try:
            return License(value.strip())
        except ValueError:
            # `shout`, `Assert`, `assert ` with a stray character: unknown is
            # unknown, and the weakest rung is what unknown means.
            return FLOOR
    return FLOOR


def quarantined(belief: Mapping[str, Any]) -> bool:
    """Whether the log pinned this belief at `behave`.

    The predicate is ``half.store.records.pinned`` — the same one the fold uses
    to carry the field forward, because a pin the fold and the ladder disagree
    about is not a pin.
    """
    return pinned(belief.get(QUARANTINED))


def has_receipt(belief: Mapping[str, Any]) -> bool:
    """Whether this belief cites evidence — the first `assert` precondition.

    The support set, and nothing else. Corroboration counts are deliberately
    unread: ``independent`` says how *many* separate sources agree, which is
    Half's own inference about its own evidence, and no amount of it is a
    receipt. A citation is a citation or it is absent.

    A bare string is accepted alongside a list, for the same reason
    ``half.context.build`` accepts one for ``topics``: a log that wrote
    ``support="s_1"`` cited a source, and refusing to read it would not be the
    safe direction — it would be a receipt Half holds and cannot see.
    """
    support = belief.get(SUPPORT)
    if isinstance(support, str):
        return bool(support.strip())
    if isinstance(support, (list, tuple)):
        return any(isinstance(item, str) and item.strip() for item in support)
    return False


def known_to_main(belief: Mapping[str, Any]) -> bool:
    """Whether the main already knows Half holds this — the second precondition.

    Strictly ``True``, and strictness is the point. Every other reader in this
    module fails *closed* by treating an uninterpretable value as the
    restrictive one; this field grants a permission, so the restrictive reading
    is the opposite: anything that is not an explicit ``True`` — a truthy
    string, a date, a count, a value from a schema this build does not know —
    is not knowledge the main has, and the belief stays below `assert`.
    """
    return belief.get(KNOWN) is True


def own_rung(belief: Mapping[str, Any] | Any) -> License:
    """The rung this belief permits on its own, before any ceiling.

    Quarantine wins over the stated rung, in one direction: a quarantined
    belief is `behave` even if its license field says `assert`, and the reverse
    — a quarantine flag promoting anything — is not expressible here.

    An `assert` that has not earned both preconditions lands on `ask`. It is
    still a demotion: nothing in this function returns a rung above the one the
    field states.
    """
    if not isinstance(belief, Mapping):
        return FLOOR
    if quarantined(belief):
        return FLOOR
    rung = rung_of(belief.get(LICENSE))
    if rung is License.ASSERT and not (has_receipt(belief) and known_to_main(belief)):
        # Refused, not silenced. The constitution's own remedy for a claim Half
        # cannot state is to ask it.
        return License.ASK
    return rung


def permitted(
    belief: Mapping[str, Any] | Any, *, ceiling: "Ceiling | None"
) -> License:
    """The rung ``belief`` permits under this actor's ceiling.

    The single function the rest of Half asks *what may this belief do*, and
    the reason the ceiling cannot be forgotten: there is no route to a rung
    that does not pass through here, and ``ceiling`` has no default, so a new
    surface that omits it fails rather than silently running uncapped.

    ``ceiling=None`` is the *configured* absence — a main with no ceiling set —
    and resolves to the belief's own license, never above it.
    """
    return cap(own_rung(belief), ceiling)


def cap(rung: License, ceiling: "Ceiling | None") -> License:
    """``rung`` capped by ``ceiling``. A minimum, so it can only ever lower."""
    return rung if ceiling is None else weaker(rung, ceiling.rung)


@dataclass(frozen=True, slots=True)
class Ceiling:
    """One global license cap, belonging to one main (AD-28).

    Per main, not per worker, and not per feature. Per worker would let one
    main's aftercare silence every other main the process is serving — the
    failure a single shared retrieval switch already caused once. Per feature is
    the failure AD-28 names outright: aftercare implemented as scattered
    suppression that the next feature forgets to honour.

    Caps; never promotes. ``rung`` is an upper bound taken as a minimum against
    each belief's own license, so raising it back to `assert` restores nothing
    that was not already permitted.

    **Frozen, and it has exactly two ways to move.** ``lowered_to`` only lowers.
    ``released`` is the named exception that raises it, and it demands a reason
    — there is no setter, and assigning ``ceiling.rung`` raises
    ``FrozenInstanceError`` rather than quietly un-suppressing a main whose
    ceiling object somebody was handed. Both return a *new* ceiling, so a cap
    that was read stays the cap that was read.

    **Durable, and the object is not where it is kept.** The authority is a
    ``ceiling`` record in the log, folded into ``State.ceiling`` and re-read at
    hydration — because eviction is routine at any real capacity, and a
    thirty-day aftercare cap that lifts itself when a worker gets busy is worse
    than no cap at all: it reads as protection. This object is the parsed value,
    not the storage.
    """

    #: The strongest rung this actor may reach. `assert` is no cap at all.
    rung: License = TOP

    def __post_init__(self) -> None:
        # Parsed rather than trusted, and fail-closed in the restrictive
        # direction: a ceiling this build cannot read caps everything at
        # `behave`, because a ceiling exists to restrict and an unreadable one
        # must not be an absent one. ``None`` is the one value that means *no
        # ceiling has ever been set* rather than *unreadable*, so that a main
        # with no ceiling is not born capped.
        object.__setattr__(
            self, "rung", TOP if self.rung is None else rung_of(self.rung)
        )

    @property
    def capping(self) -> bool:
        """True when this ceiling can lower something."""
        return self.rung is not TOP

    def lowered_to(self, to: License) -> "Ceiling":
        """A ceiling no higher than ``to``. Only ever lowers: asking for
        `assert` on a ceiling already at `behave` returns `behave`."""
        return Ceiling(weaker(self.rung, _rung_arg(to, "lowered_to")))

    def released(self, *, because: str, to: License = TOP) -> "Ceiling":
        """Raise the cap — the one operation that can, and never a setter.

        ``because`` is required and must say something. Lowering a ceiling is
        a safety act and needs no justification; *raising* one ends a
        suppression that something deliberate put in place, and a build where
        that is a bare assignment is a build where a stray line un-suppresses a
        main mid-aftercare. No belief moves either way: the cap is a minimum,
        so lifting it can only stop subtracting.

        Aftercare is what calls this, and aftercare is story 6. Nothing in this
        module calls it.
        """
        if not isinstance(because, str) or not because.strip():
            raise LadderError(
                "released: raising a ceiling requires a stated reason; it ends "
                "a suppression something deliberate put in place"
            )
        return Ceiling(_rung_arg(to, "released"))


def ceiling_fields(ceiling: Ceiling, *, because: str) -> dict[str, Any]:
    """The fields of the append that records ``ceiling`` (AD-28, AD-3).

    Returns fields; writes nothing, like every other writing entry point here.
    The reason travels into the log because a ceiling outlives whoever set it —
    thirty days later the question *"why is this main capped?"* has to be
    answerable from the log alone.
    """
    if not isinstance(because, str) or not because.strip():
        raise LadderError("ceiling_fields: a ceiling record must say why")
    return {RUNG: str(ceiling.rung), "because": because.strip()}


# -- writing: a license change is an append, never an edit (AD-3) ------------
#
# Every function below returns the *fields of an append* and writes nothing.
# Together they are the only way any of `license`, `support`, `known_to_main`,
# the quarantine field or a ceiling's `rung` reaches the log, and
# `tests/test_ladder.py` fails the build if another module spells one of them
# into a record. Read-side enforcement alone would leave `assert` a field
# anyone can set — it would merely raise the price from one field to three.


def admitted(*, support: Any = None) -> dict[str, Any]:
    """The license fields a *new* belief is born with.

    Always the weakest rung. There is no argument that raises it, and that is
    the whole content of the function: a belief cannot be admitted at `assert`,
    because both preconditions are things that happen *after* a belief exists —
    evidence is cited and the main is told. Anything stronger is a promotion,
    and a promotion is an event.

    ``support`` is accepted here because a receipt is known at admission and is
    one of the four gated fields, so the ladder has to be the one that writes
    it. Carrying a receipt grants nothing on its own.
    """
    fields: dict[str, Any] = {LICENSE: str(FLOOR)}
    if support is not None:
        fields[SUPPORT] = list(support) if isinstance(support, tuple) else support
    return fields


def promote(
    belief: Mapping[str, Any], *, to: License, acknowledged: bool
) -> dict[str, Any]:
    """The fields of the append that promotes ``belief`` to ``to``.

    Returns fields; writes nothing. The caller appends them under the belief's
    own id, so the fold replaces the record and replay reproduces the promotion
    rather than re-deriving it (AD-3, AD-30). Every field the belief already
    carried travels forward — a promotion that dropped the claim would be a
    correction wearing a promotion's name.

    Refused, loudly, when:

    * the belief is quarantined — the pin is permanent and no path lifts it;
    * ``to`` is not above the rung the belief is *effectively* on — a demotion
      has its own function, and a "promotion" that lowers is a caller confused
      about which it is doing;
    * ``acknowledged`` is not ``True`` — promotion is an event involving the
      main, so there is no argument here that a corroboration count could
      satisfy;
    * ``to`` is `assert` and the belief cites nothing.

    **Compared against the effective rung, not the stated field.** A belief
    stating `assert` with no receipt *resolves* to `ask`, and comparing against
    the field would refuse its promotion as `assert -> assert` — a message that
    misdirects, on a belief whose only route upward would then be a demotion
    followed by a promotion. There is one answer to what rung a belief is on and
    ``own_rung`` gives it.

    **An acknowledgement earns only the rung it was given for.** ``known_to_main``
    is written for an `assert`-level promotion and for nothing weaker: the main
    permitting Half to *ask* about something is not the main knowing Half holds
    it, and recording it as such would leave a receipt as the only thing between
    a question and a statement. The two preconditions are independent, and
    letting one pay for the other collapses them into one.
    """
    fields = _carried(belief, "promote")
    target = _rung_arg(to, "promote")
    if quarantined(belief):
        raise LadderError(
            "promote: this belief is quarantined and is pinned at 'behave' "
            "permanently; nothing promotes it"
        )
    current = own_rung(belief)
    if height(target) <= height(current):
        raise LadderError(
            f"promote: this belief is on {current}; {current} -> {target} is "
            "not a promotion. Demotion is always permitted and has its own path"
        )
    if acknowledged is not True:
        raise LadderError(
            "promote: promotion is an event involving the main. Half's own "
            "inference never licenses a higher rung, however well corroborated"
        )
    if target is License.ASSERT and not has_receipt(belief):
        raise LadderError(
            "promote: 'assert' requires a citation into Half's own evidence; "
            "an unsupported claim may be asked, never asserted"
        )
    fields[LICENSE] = str(target)
    if target is License.ASSERT:
        fields[KNOWN] = True
    return fields


def demote(belief: Mapping[str, Any], *, to: License) -> dict[str, Any]:
    """The fields of the append that demotes ``belief`` to ``to``.

    Always permitted, and takes no acknowledgement: nothing is owed for saying
    less. The only refusal is a ``to`` that is not below the rung the belief is
    effectively on, which is a caller that meant ``promote`` — compared against
    ``own_rung`` for the reason ``promote`` is, so that the two functions and
    ``resolve`` give one answer rather than three.
    """
    fields = _carried(belief, "demote")
    target = _rung_arg(to, "demote")
    current = own_rung(belief)
    if height(target) >= height(current):
        raise LadderError(
            f"demote: this belief is on {current}; {current} -> {target} does "
            "not lower anything. Promotion is never permitted by default and "
            "has its own path"
        )
    fields[LICENSE] = str(target)
    return fields


@dataclass(frozen=True, slots=True)
class QuarantineCandidate:
    """A belief inference thinks should be left alone, and a reason.

    A candidate is not a quarantine. It carries no authority and changes
    nothing — it exists so that *"a name that goes from daily to zero
    overnight"* has somewhere to land while Half asks about it. The asking is
    story 5b and story 11; this type is the handoff.
    """

    belief_id: str
    reason: str


def quarantine_candidate(
    belief: Mapping[str, Any], *, reason: str
) -> QuarantineCandidate | None:
    """A candidate for ``belief``, or ``None`` if there is nothing to propose.

    Pure and inert: it reads the belief, returns a value, and pins nothing.
    ``None`` for a belief already quarantined — there is no second pin — and
    for a belief with no id, which cannot be asked about.
    """
    if not isinstance(belief, Mapping):
        return None
    if quarantined(belief):
        return None
    belief_id = belief.get("id")
    if not isinstance(belief_id, str) or not belief_id:
        return None
    if not isinstance(reason, str) or not reason.strip():
        return None
    return QuarantineCandidate(belief_id=belief_id, reason=reason.strip())


def quarantine(
    belief: Mapping[str, Any], *, candidate: QuarantineCandidate, answered: bool
) -> dict[str, Any]:
    """The fields of the append that pins ``belief`` at `behave`, permanently.

    Both arguments are required and neither has a default, which is the rule
    *"Half never quarantines on inference alone"* expressed as a signature
    rather than as a check somebody has to remember: applying a quarantine
    needs a candidate to have been raised **and** the main to have answered.

    The pin is a field on the belief, so it survives the fold, the replay and
    the export, and it is visible to anything that reads the record. There is
    no path in this module that clears it.
    """
    fields = _carried(belief, "quarantine")
    if not isinstance(candidate, QuarantineCandidate):
        raise LadderError(
            "quarantine: inference alone never quarantines; a candidate must "
            "have been raised and put to the main"
        )
    if candidate.belief_id != belief.get("id"):
        raise LadderError(
            f"quarantine: candidate names {candidate.belief_id!r}, not "
            f"{belief.get('id')!r}"
        )
    if answered is not True:
        raise LadderError(
            "quarantine: applying a candidate requires the main's answer; "
            "detection produces a candidate and Half asks"
        )
    fields[QUARANTINED] = True
    fields[LICENSE] = str(FLOOR)
    return fields


def _rung_arg(value: object, what: str) -> License:
    """``value`` as a rung, refusing anything that is not one.

    ``rung_of`` folds an unreadable value to `behave` because a *stored* license
    it cannot read means the weakest rung. An unreadable **argument** is a
    different thing: a caller that wrote ``to="bahave"`` gets a refusal, not a
    silent demotion to the rung the typo happened to fold to.
    """
    rung = rung_of(value)
    if not isinstance(value, (License, str)) or str(rung) != str(value).strip():
        raise LadderError(
            f"{what}: {value!r} is not a rung; the ladder is "
            f"{', '.join(str(r) for r in RUNGS)}"
        )
    return rung


def _carried(belief: Mapping[str, Any], what: str) -> dict[str, Any]:
    """Every field of ``belief`` that travels into the next append.

    ``t``, ``op``, ``id`` and ``v`` are the record's own structure and belong to
    the append, not to the belief — passing them through would make
    ``Record.id`` disagree with ``data["id"]``.
    """
    if not isinstance(belief, Mapping):
        raise LadderError(f"{what}: a belief record is required, got {type(belief).__name__}")
    return {k: v for k, v in belief.items() if k not in RESERVED}
