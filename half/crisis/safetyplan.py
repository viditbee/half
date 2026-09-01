"""Holding a safety plan, and giving it back (CAP-12, story 6c).

**Half must not author one — that is clinical work.** Half *holds* one made
with a professional and can produce it instantly, and that is the entire point:
a safety plan in a drawer is useless at three in the morning. Steps three and
four of the Stanley–Brown plan — social distractions, social contacts — are
literally Half's own data, which is exactly what makes authoring feel one field
away, and a plan Half wrote would be produced at three in the morning carrying
the authority of one a clinician made.

**So there is no authoring surface, and that is a property of this file rather
than a rule about it.**

* Nothing here composes plan content. The only function that produces the
  fields of an append, ``held_fields``, copies the lines it was given and has
  no other argument — it cannot add a step, fill a gap, reorder, retitle, or
  summarise, because there is nothing for it to do any of that *from*.
* Nothing here knows the shape of a safety plan. The six Stanley–Brown section
  names appear nowhere in this module, so there is no template of a plan for a
  missing section to be filled against, and no heading Half could supply
  because the clinician did not. ``tests/test_safetyplan.py`` asserts their
  absence.
* Nothing here mends a plan. A line that could not be rendered does not get
  dropped, cleaned or replaced: the whole plan is withheld and Half says so.
  A document produced with a section missing is worse than one not produced,
  because the missing section is the one nobody notices is missing.
* ``held_fields`` is the single writer of the plan field in the package, which
  ``tests/test_safetyplan.py`` enforces over the whole tree the way the ladder's
  writer gate does. Adding a second writer is a diff that fails a test.

**Producing it is not ledger retrieval.** Crisis mode hard-disables retrieval
over the belief set (CAP-12, build requirement 3) because nothing true about
the main's past is safe to surface in the moment. A held plan is not that: it
is a document the main was given by a professional, looked up by field, never
ranked, never searched, never placed in a model's context — there is no model —
and the only records this path can see are the ones ``plan_projection`` already
narrowed to the plan and its pin. The same split the phone book made, one field
over.

**Quarantine still wins.** A plan the main pinned is a plan the main said to
leave alone, and this module has no path that produces one.

**Every line is checked before it is shown.** A plan reaches a main inside a
crisis reply, so its lines go through ``half.crisis.rows.plain`` like a
contact's name: one printable line each, no control character, none of the
separators a reply is joined from. That check is why the "verbatim" guarantee
can be stated at all — it is what makes ``is_plan_templated`` able to say that
every segment of a produced reply is either a reviewed paragraph or a line the
main's own clinician wrote.

Pure and stdlib-only: no clock, no network, no model, no ambient state.
"""

from __future__ import annotations

import logging
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any, Final, Mapping, Protocol, runtime_checkable

from half.crisis import respond, rows, templates
from half.crisis.rows import ROW
from half.governance import ladder
from half.store.records import PLAN

logger = logging.getLogger(__name__)

#: Between paragraphs. The same separator the opener and the door use.
SEPARATOR: Final[str] = rows.PARAGRAPH

#: How long one line of a plan may be. Longer than a name or a way to reach a
#: service, because a coping strategy is a sentence and sometimes two; bounded
#: anyway, because a reply that is mostly one line is unreadable at the moment
#: it has to be readable.
MAX_LINE: Final[int] = 400

#: How many lines a plan may hold. Six sections, each written out, with room
#: for a plan that lists several contacts on their own lines. Past this it is
#: not a safety plan and rendering it whole would bury the reply that carries
#: it — and, unlike a long line, there is no honest way to show part of it.
MAX_LINES: Final[int] = 40


@dataclass(frozen=True, slots=True)
class SafetyPlan:
    """One held plan, as it was written.

    ``lines`` are the clinician's own, in the clinician's own order. They are
    stored unchanged and carried here unchanged; whether they can be *rendered*
    is a separate question, asked once, by ``render``.
    """

    id: str
    lines: tuple[str, ...]
    #: When it was written, as the log stamped it, or ``None``. Carried so that
    #: "the newest plan wins" is a fact about time rather than about spelling.
    t: str | None = None


def plan_of(record: Mapping[str, Any] | Any) -> SafetyPlan | None:
    """``record`` as a held plan, or ``None`` if it is not one.

    ``None`` for a record without plan lines, for one the main pinned, and for
    one whose id cannot be read — never a repaired or partial plan, because a
    partial plan is the invented one this module exists to make impossible.
    """
    if not isinstance(record, Mapping):
        return None
    if ladder.quarantined(record):
        # The main said leave this alone. There is no path here that produces
        # it, and no path anywhere that clears the pin.
        return None
    lines = record.get(PLAN)
    if not isinstance(lines, (list, tuple)) or not lines:
        return None
    if any(not isinstance(line, str) for line in lines):
        return None
    ident = record.get("id")
    if not isinstance(ident, str) or not ident:
        return None
    stamp = record.get("t")
    return SafetyPlan(
        id=ident,
        lines=tuple(lines),
        t=stamp if isinstance(stamp, str) and stamp else None,
    )


def held(records: Sequence[Mapping[str, Any]]) -> SafetyPlan | None:
    """The plan this main is holding, or ``None``.

    **Ordered by when it was written**, and by id only to break a tie. The
    first version sorted by id alone and called the result supersession, which
    it was not: ids are opaque, so ``p_alpha`` written last lost to ``p_zebra``
    written first and a replaced document came back as current. A main whose
    clinician gave them a new plan has a new plan; producing the old one is
    producing a document that was withdrawn, under a sentence saying nothing
    was changed.

    A record with no readable stamp sorts before every dated one rather than
    after: it cannot be shown to be the newest, and the safe reading of "I
    cannot tell when this was written" is not "it is the current one".

    Nothing merges two. A merged plan is an authored plan.
    """
    found = [plan for plan in (plan_of(r) for r in records) if plan is not None]
    return max(found, key=lambda plan: (plan.t or "", plan.id)) if found else None


def line(text: str) -> str | None:
    """One plan line as it will be shown, or ``None`` if it cannot be shown.

    **The pinned format, and there is nothing in it.** A plan line renders as
    itself: no bullet, no number, no heading, no *"step three:"*. Every one of
    those is a word Half added to a clinical document, and ``is_plan_templated``
    compares against exactly this function, so adding one here fails rather
    than shipping blessed — the hole the handoff's guard had before it stopped
    recomputing its input through the renderer.

    ``rows.one_line`` and not ``rows.plain``: the row separators are refused in
    a value that is *joined into* a row, and a plan line is joined into
    nothing. An em dash in a clinician's sentence is ordinary prose, and
    withholding somebody's whole safety plan over one would be this module's
    strictness turned against the person it protects.
    """
    return rows.one_line(text, limit=MAX_LINE)


def render(plan: SafetyPlan) -> str | None:
    """``plan`` as the paragraphs a main receives, or ``None``.

    ``None`` when any line cannot be shown, or when there are more lines than a
    reply can carry. **Whole or not at all**: a plan produced with a section
    missing is the invented plan this module refuses, wearing the main's own
    clinician's name.
    """
    if not plan.lines or len(plan.lines) > MAX_LINES:
        return None
    shown = [line(text) for text in plan.lines]
    if any(text is None for text in shown):
        return None
    return SEPARATOR.join([
        templates.PLAN_OPEN.text,
        ROW.join(text for text in shown if text is not None),
        templates.PLAN_CLOSE.text,
    ])


def is_plan_templated(text: str, plan: SafetyPlan | None) -> bool:
    """Whether every segment of ``text`` is reviewed or is this plan's own line.

    The closed-set check, built the way the handoff's was repaired: it splits
    the way the renderer joins (``rows.segments``, on both separators), and it
    builds the admissible set from the plan's own data rather than by
    recomputing its input through ``render`` — which would be true by
    construction and would bless whatever ``render`` emitted.

    There is no third possibility. A segment is a paragraph a clinician
    reviewed for this product, or it is a line the main's own clinician wrote.
    """
    allowed = set()
    if plan is not None:
        allowed = {shown for shown in (line(t) for t in plan.lines) if shown}
    parts = rows.segments(text)
    return bool(parts) and all(
        part in templates.TEXTS or part in allowed for part in parts
    )


def held_fields(lines: Sequence[str]) -> dict[str, Any]:
    """The fields of the append that records a plan **exactly as it was given**.

    The only writer of the plan field there is, and the whole of it is a copy.
    One argument, so there is nothing to compose from; no default, so there is
    no empty plan to start filling in; no reformatting, no stripping, no
    ordering, no titles, no gaps noticed and no gaps filled.
    ``tests/test_safetyplan.py`` asserts that every call site under ``half/``
    hands it a value it was *given* rather than one built on the spot — the
    property, not the spelling, because a module composing lines out of Half's
    own ledger and passing them here would satisfy any check that only counted
    ways of writing the field.

    Refuses a plan that is not a sequence of lines, and refuses an empty one:
    "Half holds a plan with no steps in it" is a state whose only honest
    rendering is the absent line, and having two ways to be absent is how one
    of them stops being checked.

    **The size and shape limits are here, at the append, not at the render.**
    The log is append-only, so a forty-one-line plan or a line that cannot be
    shown would otherwise be stored permanently and be permanently
    unproducible — answered for ever with *"I cannot get to a safety plan for
    you right now"*, over a document the main can see is there. Refusing at
    intake tells them on the turn they hand it over, when they can do something
    about it.
    """
    if isinstance(lines, str) or not isinstance(lines, Sequence):
        raise TypeError("a safety plan is the lines it was written as")
    kept = list(lines)
    if not kept or any(not isinstance(text, str) for text in kept):
        raise ValueError(
            "a safety plan is a non-empty sequence of the lines it was written "
            "as; Half neither fills one in nor holds an empty one"
        )
    if len(kept) > MAX_LINES:
        raise ValueError(
            f"a safety plan of {len(kept)} lines is past the {MAX_LINES} this "
            "build can show whole, and a plan it cannot show whole is one it "
            "must not store"
        )
    unshowable = [text for text in kept if line(text) is None]
    if unshowable:
        raise ValueError(
            "a safety plan line has to be one printable line inside "
            f"{MAX_LINE} characters; {len(unshowable)} of these are not, and a "
            "plan with a line that cannot be shown is a plan that would be "
            "withheld for ever"
        )
    return {PLAN: kept}


#: What separates the marker line from the document. The main's own message,
#: exactly as their keyboard produced it.
INTAKE_BREAK: Final[str] = "\n"


def lines_from(text: str) -> list[str]:
    """The plan inside a message that hands one over. Verbatim.

    **A marker, not a parser.** Everything after the line the marker sits on is
    the document, kept exactly as it was sent. Half decides where the plan
    begins because the main said so, and nothing else about it: no heading is
    supplied, no step is numbered, no section is noticed as missing, and
    nothing is rewritten.

    Blank lines are dropped, and that is the only thing done to the text. A
    blank line is not a step, it cannot be rendered as one, and keeping it
    would mean refusing every plan a person typed with spacing in it.
    """
    if not isinstance(text, str):
        return []
    head, sep, rest = text.partition(INTAKE_BREAK)
    if not sep:
        return []
    return [part for part in rest.split(INTAKE_BREAK) if part.strip()]


@runtime_checkable
class Held(Protocol):
    """Whoever can produce a main's held plan.

    Deliberately not "the store", for the reason the handoff's ``Held`` is not:
    this path may see a held document and nothing else about the main, and the
    narrow protocol is what keeps the mode's retrieval disable honest rather
    than trusting every caller to look at one field.
    """

    def safetyplan_records(self, main_id: str) -> Sequence[Mapping[str, Any]]:
        """This main's plan records. Never a claim about the main."""
        ...

    async def hold_safetyplan(
        self, main_id: str, *, t: str, fields: Mapping[str, Any]
    ) -> None:
        """Store one plan, under the main's own mutex (AD-1).

        Takes the *fields* rather than the lines, so that ``held_fields``
        remains the only expression in the codebase that puts a value into the
        plan field — the store appends what it is handed and composes nothing.
        """
        ...


@dataclass(slots=True)
class Holder:
    """Produces the held plan for one turn. Never raises, never authors.

    Constructed with nothing at all in a caller that has not wired it, and then
    it holds nothing — which renders as the absent line, which is true: a Half
    with no store is a Half holding no plan.
    """

    #: Where the plan comes from. ``None`` means there is none.
    held: Held | None = None

    async def receive(self, main_id: str, text: str, *, t: str) -> str:
        """Take a plan the main has just handed over. Never raises.

        **This is the ingestion half, and without it the rest is unreachable.**
        A build where Half can produce a held plan but nothing can ever hold
        one answers every main with *"I am not holding a safety plan for you"*
        for ever, and the retrieval, the projection, the rendering and the
        quarantine rule are all dead code behind a sentence nobody can change.

        Half stores what it was sent and nothing else. The only judgement it
        makes is where the document starts, and the main made that judgement by
        typing the words that say so.

        A plan too long, or with a line that could not be shown, is refused
        *here* rather than stored and withheld for ever — and the main is told
        with the same sentence they would get later, on the turn they can still
        do something about it.
        """
        try:
            return await self._receive(main_id, text, t=t)
        except Exception as exc:
            # Content-free and subject-free (AD-22): nothing here names the
            # main and nothing repeats a line of what they sent — including
            # the exception's own text, which on this path would be a line of
            # the document the main just sent (story 6d, review round 1).
            logger.warning(
                "a safety plan could not be taken (%s); saying so rather than "
                "claiming to hold one", type(exc).__name__
            )
            return templates.PLAN_UNREADABLE.text

    async def _receive(self, main_id: str, text: str, *, t: str) -> str:
        if self.held is None:
            return templates.PLAN_UNREADABLE.text
        try:
            fields = held_fields(lines_from(text))
        except (TypeError, ValueError):
            # Refused rather than repaired. Half is not going to shorten
            # somebody's safety plan to fit, and it is not going to claim to
            # hold one it would never be able to show.
            return templates.PLAN_UNREADABLE.text
        await self.held.hold_safetyplan(main_id, t=t, fields=fields)
        return templates.PLAN_HELD_NOW.text

    def produce(self, main_id: str) -> str:
        """The plan, or the plain sentence that there is not one. Never empty.

        Never raises and never returns nothing: the main asked a direct
        question and going quiet is the documented catastrophic failure. The
        three answers are the plan, *"I am not holding one"*, and *"I cannot
        get to one"* — and the third is what a failure resolves to, because
        claiming to hold nothing when a plan exists is a lie told at the worst
        possible moment.
        """
        try:
            return self._produce(main_id)
        except Exception as exc:
            # Content-free and subject-free (AD-22): nothing here names the
            # main, so an ordinary log cannot be read backwards into who asked
            # for a safety plan — and the class only, never the exception's
            # own text, which here could quote the plan (story 6d).
            logger.warning(
                "a held safety plan could not be produced (%s); saying so "
                "rather than showing part of one", type(exc).__name__
            )
            return templates.PLAN_UNREADABLE.text

    def _produce(self, main_id: str) -> str:
        if self.held is None:
            return templates.PLAN_ABSENT.text
        plan = held(list(self.held.safetyplan_records(main_id)))
        if plan is None:
            return templates.PLAN_ABSENT.text
        shown = render(plan)
        if shown is None:
            return templates.PLAN_UNREADABLE.text
        if not is_plan_templated(shown, plan):
            # The rendering stopped being made of reviewed paragraphs and this
            # plan's own lines. Saying so beats showing it, on the same terms
            # as ``respond.reply_for``'s own check: a guard that only a test
            # runs is a guard a refactor removes.
            logger.error(
                "a safety plan rendering was neither reviewed nor the plan's "
                "own lines; saying so rather than showing it"
            )
            return templates.PLAN_UNREADABLE.text
        return shown


def is_absent(said: str) -> bool:
    """Whether ``said`` is Half saying it holds no plan. For callers that must
    distinguish the three answers without matching wording themselves."""
    return said == templates.PLAN_ABSENT.text


def is_templated(said: str) -> bool:
    """Whether ``said`` is made only of reviewed paragraphs — true for both
    sentences a plan-less main can receive, and false for a rendered plan,
    which carries lines nobody in this product reviewed and must not."""
    return respond.is_templated(said)
