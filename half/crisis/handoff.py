"""The warm handoff: assembling the offer and the draft (CAP-12, AD-25).

Half's role in the moment is not counsellor; it is *the warm handoff*. A
personal introduction to a human rather than a phone number more than tripled
the odds of somebody attending a first appointment, and the one-tap prefilled
draft is what makes that possible on a messaging platform: **Half writes the
hardest message a person will ever send, and the main presses send.**

**Half contacts nobody, and that is structural rather than obeyed.** There is
no send path here to forget to guard: this module produces text and links, it
has no channel, no transport, no ``await`` and no recipient. The only thing it
asks of the outside world is ``Channel.draft_link`` — a function that returns a
string. Auto-alerting can out a person, and the closest person is sometimes the
problem, so the human act is not a policy in front of the send; the send does
not exist (AD-25).

**Two or three doors, and the main picks.** Never one — a single name reads as
an instruction. Never a ranked best pushed at them either, which is why a
clinician is *ordered* first and flagged in the data rather than argued for in
prose: the companion says the main's own therapist is the highest-value door,
and it also says control matters most exactly here. Putting a recommendation
into words would honour the first and break the second.

**A person is always offered beside something that is not a person**, where
there is something to offer. That is the same rule read from the other side:
the closest person is sometimes the problem, so a door that is not a person is
kept in the offer wherever one exists.

**Fewer than two doors is no offer at all.** Not silence — 6a's opener still
lands whole, and its wording already points at both a person the main trusts
and a crisis line where they live. That generic line is what stands whenever a
region was never told, the file could not be read, or only one door could be
assembled. The honest generic sentence beats a lone name that reads as an
instruction, and it beats a guessed continent by more than that.

**Every paragraph is a reviewed line, and every option is reconstructible.**
The prose comes from ``half.crisis.templates`` and nowhere else. The option
rows are not prose: they are a name and a way to reach it, rendered by one
total function over data the main confirmed or a curator wrote down.
``is_offer_templated`` checks a rendered offer against exactly that — every
paragraph is a template line, or it is byte-identical to this module's own
rendering of the offer's own options. There is no third possibility, and so no
seam where a sentence nobody reviewed could arrive.

**The draft says the same thing to everybody.** No greeting, no name, no
detail, nothing carried over from the message that opened the mode. A draft
that interpolated would be a generator aimed at the worst sentence anybody ever
writes, and the main's own words would come back out of it.

**Two questions this module does not answer, recorded rather than settled.**

*The whole offer repeats on every turn the mode is open.* That is deterministic
and testable, and it may also be wrong: re-serving a list of doors after every
message is a way of hurrying somebody, and the companion's tone correction is
explicit that rushing to fix reads as **minimising** and is counterproductive.
The alternatives all encode a clinical judgement — offer once and then only on
request, thin it after the third turn, repeat only the people — and picking one
in a code comment would be answering a clinical question by accident, exactly
as a mode-exit timeout would. It goes to the reviewer with the wording. What is
*not* in question is that the door must not vanish silently: a handoff the main
had to catch on the first turn is a handoff for somebody who was reading
carefully, which is nobody here.

*A crisis line renders as a string the main copies.* The highest-volume door
therefore asks the most of somebody least able to give it — typing digits at
three in the morning. A tappable form is possible (``tel:``, or a prefilled
message), but writing a person's opening words to a crisis service is a
different act from writing them to their brother, and the Ask-First rule covers
adding a contact channel beyond a link the main taps. Deferred to the reviewer
with the same wording, not decided here.

Pure and stdlib-only apart from the directory's file read: no clock, no
network, no model, no ambient state, and nothing here writes to a store.
"""

from __future__ import annotations

import logging
from collections.abc import Sequence
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path
from typing import Any, Final, Mapping, Protocol, runtime_checkable

from half.crisis import contacts, directory, rows, templates
from half.crisis.contacts import OFFER_MAX, OFFER_MIN, Contact
from half.crisis.directory import Directory, Listing
from half.crisis.rows import ROW
from half.crisis.templates import Line
from half.errors import CrisisError

logger = logging.getLogger(__name__)

#: Between paragraphs. The same separator ``half.crisis.respond`` uses, so the
#: opener and the door are one message taken apart the same way.
SEPARATOR: Final[str] = rows.PARAGRAPH


class Kind(StrEnum):
    """What a door is."""

    #: Somebody the main confirmed. Carries a prefilled draft the main sends.
    PERSON = "person"
    #: A crisis line from the versioned directory. Carries no draft: a line is
    #: something the main calls or messages themselves, and writing their side
    #: of that conversation would be putting words in their mouth to a stranger.
    LINE = "line"


@dataclass(frozen=True, slots=True)
class Option:
    """One door, as the main sees it.

    **Every string on it is checked at construction and refused if it could
    not be rendered as one line.** The guard belongs at the sources too — a
    contact's name and a directory entry both go through ``rows.plain`` — and
    it is repeated here because this is the last place before a value reaches
    a main, and defence at exactly one layer is defence a refactor removes.
    """

    kind: Kind
    #: The person's name as the main gave it, or the service's name as the
    #: directory states it — in whatever script that is, unchanged.
    label: str
    #: What the main taps or dials. A draft link for a person, the directory's
    #: own reach string for a line.
    reach: str
    #: What the directory says about a line — hours, languages, cost. The
    #: detail a person in crisis most needs and the first version parsed,
    #: typed, tested and then never showed anybody.
    note: str | None = None
    #: The main's own clinician. Ordered first; never argued for.
    clinician: bool = False

    def __post_init__(self) -> None:
        checked = (
            rows.plain(self.label, limit=rows.MAX_LABEL),
            rows.plain(self.reach, limit=rows.MAX_LINK),
            None if self.note is None else rows.plain(self.note, limit=rows.MAX_NOTE),
        )
        if checked[0] is None or checked[1] is None:
            raise CrisisError(
                "a door must be one printable line a main can read: no line "
                "break, no control character, and none of the separators a row "
                "is joined from"
            )
        if self.note is not None and checked[2] is None:
            raise CrisisError("a door's note must be one printable line")


@dataclass(frozen=True, slots=True)
class Offer:
    """What the handoff produced for one turn.

    ``version`` is always set — including to ``directory.UNKNOWN_VERSION`` —
    so *"which set of lines was this person handed"* has an answer even when
    the answer is that the file could not be read.
    """

    options: tuple[Option, ...] = ()
    version: str = directory.UNKNOWN_VERSION
    #: The main told Half where they are and this directory had nothing for
    #: there. Distinct from *nowhere told*, and said out loud rather than
    #: swallowed: a person who answered the question deserves to know the
    #: answer went nowhere, and silently nothing reads as Half having decided
    #: they were not worth a line.
    unlisted: bool = False

    def __post_init__(self) -> None:
        # The upper bound is an invariant of the object, not a habit of the
        # one function that builds it. A nine-option offer was constructible
        # and rendered all nine, and *"two or three"* is the rule the whole
        # story turns on: a list is a search result, not a choice.
        if len(self.options) > OFFER_MAX:
            raise CrisisError(
                f"an offer may hold at most {OFFER_MAX} doors; more than that "
                "is a list, and a list is not a choice"
            )

    @property
    def offered(self) -> bool:
        """Whether there is a door to show. ``False`` means 6a's generic
        wording stands, whole and unchanged."""
        return len(self.options) >= OFFER_MIN

    @property
    def speaks(self) -> bool:
        """Whether anything at all follows the opener."""
        return self.offered or self.unlisted

    @property
    def has_person(self) -> bool:
        return any(option.kind is Kind.PERSON for option in self.options)

    @property
    def has_line(self) -> bool:
        return any(option.kind is Kind.LINE for option in self.options)


#: The offer that is no offer. Never ``None``, for the reason
#: ``directory.EMPTY`` is not: a caller that has to check for one can forget.
NONE_OFFERED: Final[Offer] = Offer()


@runtime_checkable
class Held(Protocol):
    """Whoever can produce a main's phone book.

    Deliberately not "the store". The crisis path may read a confirmed name and
    a told place, and nothing else about the main — ledger retrieval is
    hard-disabled in the mode, and this narrow protocol is what keeps the
    disable honest rather than trusting every caller to look at two fields.
    """

    def handoff_records(self, main_id: str) -> Sequence[Mapping[str, Any]]:
        """This main's phone-book records: contacts, and where they said they
        are. Never a claim about the main."""
        ...


@runtime_checkable
class Drafter(Protocol):
    """The one operation the outside world provides here — ``Channel``
    satisfies it. It returns a string; there is nothing to await and no way to
    send (AD-7, AD-25)."""

    def draft_link(self, text: str, *, to: str | None = None) -> str:
        ...


def draft_for(contact: Contact) -> Line:
    """The reviewed line the main would send to ``contact``.

    Two lines, chosen by kind and by nothing else. Not by name, not by
    relationship, and not by what the main just typed — there is no argument
    here through which any of that could reach the message.
    """
    return templates.DRAFT_CLINICIAN if contact.clinician else templates.DRAFT_PERSON


def option_for(contact: Contact, drafter: Drafter) -> Option:
    """``contact`` as a door: their name, and a link that prefills the draft.

    The link is produced, never followed. ``draft_link`` hands back a URL for
    the main to tap; nothing in this module or below it opens it, and no code
    path anywhere sends its contents (AD-25).
    """
    return Option(
        kind=Kind.PERSON,
        label=contact.name,
        reach=drafter.draft_link(draft_for(contact).text, to=contact.handle),
        clinician=contact.clinician,
    )


def option_for_listing(listing: Listing) -> Option:
    """``listing`` as a door: the service's name, how to reach it, and what the
    directory says about it — hours, languages, whether it is free. That last
    part is what a person in crisis most needs and the first version of this
    module parsed, typed, tested and then showed to nobody."""
    return Option(kind=Kind.LINE, label=listing.name, reach=listing.reach,
                  note=listing.note)


def _doors(built: Sequence[Any]) -> list[Option]:
    """Every door that could be built, dropping the ones that could not.

    Per-row, like the directory's own degradation, and for the same reason: a
    single unrenderable handle used to collapse the whole offer — including
    the crisis lines, which had nothing to do with it — because one exception
    inside one comprehension reached the desk's broad ``except``. One bad
    contact costs one door.
    """
    found: list[Option] = []
    for build in built:
        try:
            found.append(build())
        except Exception:
            # No name, no value, no message text (AD-22).
            logger.warning("a door could not be built; the rest stand")
    return found


def compose(
    people: Sequence[Contact],
    listings: Sequence[Listing],
    *,
    drafter: Drafter | None,
    version: str,
    unlisted: bool = False,
) -> Offer:
    """The doors for one turn, in the order the main sees them.

    **Confirmation is re-checked here.** ``Desk`` passes only what
    ``contacts.confirmed`` returned, but this function is public and a second
    caller that skipped that step would offer a name nobody agreed to — so the
    rule lives at the place that builds the offer rather than at one route into
    it.

    A person is only a door if there is something to tap, so a caller with no
    drafter gets lines and no people rather than names that go nowhere.

    One slot is kept for a line wherever a line exists — the closest person is
    sometimes the wrong one, and an offer made entirely of people has quietly
    removed the door that exists for exactly that case.
    """
    doors: list[Option] = []
    if drafter is not None:
        doors = _doors([
            lambda contact=contact: option_for(contact, drafter)
            for contact in people if contact.confirmed
        ])

    room_for_people = OFFER_MAX - 1 if listings else OFFER_MAX
    chosen = doors[:room_for_people]
    chosen += _doors([
        lambda listing=listing: option_for_listing(listing)
        for listing in listings[: OFFER_MAX - len(chosen)]
    ])

    if len(chosen) < OFFER_MIN:
        # One door is not a choice, and a choice is the point. 6a's opener
        # already names both kinds of door in prose, so this costs the main a
        # tap rather than the information.
        return Offer(version=version, unlisted=unlisted)
    return Offer(options=tuple(chosen), version=version, unlisted=unlisted)


def render(offer: Offer) -> str:
    """``offer`` as the paragraphs that follow the opener.

    Empty string for an offer with nothing to say, so the caller appends
    nothing and 6a's reply is byte-identical to what it was before this story.

    An offer with no doors but an unmatched region still speaks: the main
    answered a question and the answer went nowhere, and telling them so is the
    difference between an honest gap and Half appearing to have decided they
    were not worth a line.
    """
    if not offer.speaks:
        return ""
    parts: list[str] = []
    if offer.offered:
        parts += [templates.OFFER_OPEN.text, render_options(offer.options)]
        if offer.has_person:
            parts.append(templates.OFFER_DRAFT.text)
        if offer.has_line:
            parts.append(templates.OFFER_LINES.text)
    if offer.unlisted:
        parts.append(templates.OFFER_UNLISTED.text)
    if offer.offered:
        parts.append(templates.OFFER_CLOSE.text)
    return SEPARATOR.join(parts)


def render_options(options: Sequence[Option]) -> str:
    """The option rows, as one paragraph. The only non-template text a main
    receives here, and every character of it is checked."""
    return ROW.join(render_option(option) for option in options)


def render_option(option: Option) -> str:
    """One row: a name, the way to reach it, and what is known about it.

    The format itself lives in ``half.crisis.rows``, which is also what the
    guard compares against — so a clause appended *here* (a response time, a
    relationship, *"this is the one I would start with"*) fails the check
    rather than shipping blessed. That was the hole: the guard recomputed its
    input through this function, which made it true by construction.
    """
    return rows.row(option.label, option.reach, option.note)


def paragraphs(text: str) -> list[str]:
    """``text`` split the way ``render`` joined paragraphs. Kept because the
    guard needs the finer split — see ``rows.segments`` — and a reader looking
    for paragraphs should not silently get lines."""
    return [part for part in text.split(SEPARATOR) if part]


def is_offer_templated(text: str, offer: Offer) -> bool:
    """Whether every segment of ``text`` is reviewed or is a pinned row.

    The closed-set check, repaired twice over.

    **It splits the way the renderer joins.** The first version split on a
    blank line while ``render_options`` joined rows with a single newline, so
    a contact called ``"Mum\\nTake thirty of them"`` produced a line of its own
    inside a crisis reply and this function returned ``True``.
    ``rows.segments`` splits on both, which is total because no reviewed
    template line contains a newline — asserted at import in
    ``half.crisis.templates``.

    **It does not recompute its input through the renderer.** The first version
    compared each candidate row against ``render_options``, which made it true
    by construction: appending *"(they usually reply within a few minutes)"* —
    or *"(this is the one I would start with)"*, which breaks the
    never-a-ranked-best rule outright — inside ``render_option`` shipped
    blessed. The admissible set is built here from ``rows.row``, the pinned
    format, over the offer's own option data. A clause added in the renderer
    now fails; a clause added to the format fails a literal in the suite.

    Runs on the production path, in the gate, for the reason
    ``respond.is_templated`` does: a version of it that answered ``True``
    unconditionally must break a real reply and not only a test's.
    """
    allowed = {
        rows.row(option.label, option.reach, option.note)
        for option in offer.options
    }
    parts = rows.segments(text)
    return bool(parts) and all(
        part in templates.TEXTS or part in allowed for part in parts
    )


@dataclass(slots=True)
class Desk:
    """Assembles the handoff for one turn. Never raises, never sends.

    Constructed with nothing at all in a caller that has not wired it, and then
    it offers nothing — which is the same outcome as a main who has confirmed
    nobody and told Half nowhere, and is exactly 6a's behaviour. A handoff that
    failed loudly when unwired would be a handoff that cost somebody their
    reply on the day it was half-deployed.
    """

    #: Where the phone book comes from. ``None`` means there is none.
    held: Held | None = None
    #: How a draft becomes a link. ``None`` means people are not offered.
    drafter: Drafter | None = None
    #: The directory file. ``None`` is the packaged default, found at read
    #: time so that replacing the file needs no restart.
    path: Path | str | None = None
    #: Read at the moment of the offer rather than cached — see
    #: ``half.crisis.directory``. Injectable so a test can hand one over
    #: without a filesystem; production leaves it alone.
    loader: Any = field(default=None)

    def offer(self, main_id: str) -> Offer:
        """The doors for ``main_id``, or none. Never raises.

        Broad on purpose, and for the reason the gate's suspension is broad: a
        corrupt log, a missing file, a refactored signature, a full disk. On
        the one path where going quiet is a documented catastrophic failure,
        the set of exceptions worth losing a reply over is empty. Degrading
        here costs a tap; raising here costs the reply.
        """
        try:
            return self._offer(main_id)
        except Exception as exc:
            # Content-free *and* subject-free — see ``_record``. Nothing here
            # names the main, so an ordinary log cannot be read backwards into
            # who was in crisis, and the class crosses rather than the
            # exception's own text, which on this path could carry a contact's
            # name (story 6d). The main still gets the opener, whole.
            logger.warning(
                "a handoff could not be assembled (%s); the generic line "
                "stands", type(exc).__name__
            )
            return NONE_OFFERED

    def _offer(self, main_id: str) -> Offer:
        if self.held is None:
            return NONE_OFFERED
        records = list(self.held.handoff_records(main_id))
        people = contacts.confirmed(records)
        place = contacts.region_of(records)

        if place is None:
            # Nothing was told, or two things were, and Half does not break the
            # tie. No file is read: there is nothing to look up, and a version
            # recorded for a lookup that did not happen would be noise in the
            # one record a reviewer will actually read.
            found: Directory = directory.EMPTY
        else:
            found = self._load()

        listings = found.listings_for(place)
        offer = compose(
            people,
            listings,
            drafter=self.drafter,
            version=found.version,
            # Said out loud only when there was a real table to miss. A
            # directory that could not be read, or one nobody has reviewed, is
            # Half's problem and not a gap in what exists — telling the main
            # *"I have nothing listed for where you are"* on that evidence
            # would be blaming the file's absence on their answer.
            unlisted=place is not None and found.usable and not listings,
        )
        self._record(offer)
        return offer

    def _record(self, offer: Offer) -> None:
        """The version used, recorded content-free **and subject-free** (AD-22).

        The first version wrote ``"crisis handoff offered for main=%s"`` at
        INFO. That carries no content and it is still the wrong line: it says
        *this named person is in crisis* into ordinary application logs, in a
        product whose founding premise is that being outed is the catastrophic
        harm. Counts and a directory version answer the reviewer's question —
        *which set of lines was handed out* — without answering *to whom*, and
        DEBUG keeps it out of an ordinary production stream entirely.
        """
        if not offer.speaks:
            return
        logger.debug(
            "handoff assembled: doors=%d unlisted=%s directory=%s",
            len(offer.options), offer.unlisted, offer.version,
        )

    def _load(self) -> Directory:
        loader = self.loader if self.loader is not None else directory.load
        return loader(self.path)
