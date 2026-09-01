"""Every string a main can receive in crisis mode. As data (CAP-12).

**Templated, never generated, and this is a safety decision rather than a
scheduling one.** Every documented catastrophic failure of a chatbot in this
situation is a *generation* failure — a bridge named, a dose given, a method
described (Psychiatric Times; Scienceline). A template set cannot produce
content it does not contain, which converts the most important "never" in the
product from a behaviour into a property of the code. It also makes every word
a main can hear in crisis reviewable by a clinician in one file, which is what
the companion's build requirement 6 needs.

**Nothing here is a format string.** No interpolation, no substitution, no
placeholders, no f-strings — asserted statically in ``tests/test_crisis.py``.
A template with a hole in it is a generator with extra steps, and the hole is
where the main's own words would come back out.

**The do-list is the shape of every entering plan** (#chatsafe / Orygen, Delphi
consensus): be present, express empathy, acknowledge the difficulty, thank them
for telling you, stay. ``half.crisis.respond`` checks at import that no plan is
missing one of them, and raises rather than asserting, because a guarantee
``python -O`` removes is not a guarantee.

**The machine statement appears in every plan that enters the mode**, and in
the third-party reply. *"I'm software. You need a person."* It is the one
deliberate break of character in a product whose whole identity is being the
main's other self, and it is built on purpose.

**It does not appear in the asking plan, and that is deliberate.** The asking
plan is one gentle question after an *inference* — a film, a pet, a hard week.
Breaking character to announce "I am software and you need a human being" on
that evidence is itself sensationalising, and it makes the cheap action
expensive. The break of character belongs to the moment; it arrives the instant
the answer is yes, and it is on the clinical-review list like everything else
here.

**No locale, anywhere.** Half ships world-wide and assumes nothing about where
the main is: no phone number, no short code, no country, no service name, no
opening hours. A line says *"a crisis line where you live"* and stops there.
The referral directory is data, versioned and refreshable without a release —
``half.crisis.directory`` and ``data/crisis-lines.json`` — never a literal in
this file. Story 6b names a service only by carrying a *datum* beside a
template line, never by putting one inside one, which is why every assertion
in this file still holds after the handoff exists: no template names a place,
a number or a service, and none ever will.

**The offer and the draft lines are here for the reason the rest are.** The
handoff is the moment's other half — Half writes the hardest message a person
will ever send, and the main presses send (AD-25). That message is a reviewed
paragraph like every other, not a composition: it does not greet the recipient
by name, does not quote the main, and says the same thing to a brother as to a
therapist, because the alternative is a generator pointed at the worst sentence
anybody ever writes.

**Rushing to fix reads as minimising.** The tone here is patient rather than
fixing: present, unhurried, and explicit that Half is not going to resolve this
in a sentence.

Changing any wording in this file is an Ask-First change and, before launch, a
clinical-review change. ``tests/test_crisis_golden.py`` digests every line, so
an edit fails the suite by name rather than silently making a reviewed corpus
unreviewed. A green suite is not clinical review.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final

from half.errors import CrisisError


@dataclass(frozen=True, slots=True)
class Line:
    """One paragraph a main may receive. Identified, so a reviewer and a test
    can name it without quoting it."""

    id: str
    text: str


# -- the machine statement ---------------------------------------------------

MACHINE: Final = Line(
    "machine",
    "I want to be plain with you, because this matters more than anything "
    "else I do: I am software. I am not a person, and I am not a counsellor. "
    "You deserve a human being with you right now.",
)

MACHINE_HELD: Final = Line(
    "machine-held",
    "I am still software, and I still think you need a person with you. "
    "That has not changed.",
)

#: Either of these satisfies *"Half states plainly that it is a machine"*.
#: ``respond`` checks every entering plan carries one.
MACHINE_LINES: Final[tuple[Line, ...]] = (MACHINE, MACHINE_HELD)


# -- the do-list -------------------------------------------------------------

THANKS: Final = Line(
    "thanks",
    "Thank you for telling me. That took something to say, and I am glad you "
    "said it to me.",
)

THANKS_HELD: Final = Line(
    "thanks-held",
    "I am glad you are still talking to me.",
)

#: Either of these satisfies *"thank them for telling you"*. There are two
#: because the moment differs: the main has just disclosed, or the mode is
#: already open and thanking them again for the same disclosure would be
#: hollow.
THANKS_LINES: Final[tuple[Line, ...]] = (THANKS, THANKS_HELD)

EMPATHY: Final = Line(
    "empathy",
    "What you are carrying sounds genuinely heavy, and I am not going to rush "
    "you or try to fix it in a sentence.",
)

STAY: Final = Line(
    "stay",
    "I am here, and I am not going anywhere. You can keep writing to me for as "
    "long as you want — about this, or about nothing at all.",
)

HUMAN: Final = Line(
    "human",
    "If there is someone you trust, please tell them what you have told me, as "
    "soon as you can. A crisis line where you live can stay with you too, by "
    "phone or by message.",
)


# -- the question ------------------------------------------------------------
#
# The whole of the asking path, and the one deliberate inversion of the license
# ladder. Everywhere else in Half, inference licenses `ask` and never `assert`;
# here inference licensing `ask` is *mandatory*. Asking directly about suicide
# does not increase risk — that is well established, and the fear that it does
# is what makes builders ship silence. A false positive in Half's voice is
# exactly these three paragraphs, which is what a good friend says.

ASK_OPEN: Final = Line(
    "ask-open",
    "Something in that stayed with me, and I would rather check than let it "
    "go.",
)

ASK: Final = Line(
    "ask",
    "I might be reading this wrong, and I would rather ask than not: are you "
    "thinking about suicide?",
)

ASK_CLOSE: Final = Line(
    "ask-close",
    "There is no wrong answer. If I have got this wrong, just say so and I "
    "will let it be.",
)


# -- openers -----------------------------------------------------------------

OPEN_SAFE_WORD: Final = Line(
    "open-safe-word",
    "You used the words we agreed on. Everything I would normally be doing is "
    "switched off, and I am right here.",
)

OPEN_DISCLOSURE: Final = Line(
    "open-disclosure",
    "I hear you, and I am taking what you said seriously.",
)

OPEN_CONFIRMATION: Final = Line(
    "open-confirmation",
    "You answered me, and I am not going to treat that lightly.",
)

OPEN_SEEKING_HELP: Final = Line(
    "open-seeking-help",
    "It sounds like you are trying to reach someone. That is a good thing to "
    "be doing, and I do not want to get in the way of it.",
)

OPEN_HELD: Final = Line(
    "open-held",
    "I am still here, and I am still listening.",
)


# -- somebody other than the main --------------------------------------------
#
# The protocol is never run on anyone but the main. A signal about a third
# party surfaces something the main can *share* and stops: no contact, no
# assessment, and no belief recorded about that person. Auto-alerting can out
# someone, and the closest person is sometimes the problem.

OTHER_OPEN: Final = Line(
    "other-open",
    "That sounds frightening to be holding on your own, and I am glad you "
    "told me.",
)

OTHER_LIMIT: Final = Line(
    "other-limit",
    "I am built for you, though, and only for you. I will not assess them, I "
    "will not contact them, and I am keeping no record of what you have just "
    "told me about them.",
)

OTHER_RESOURCE: Final = Line(
    "other-resource",
    "If it would help, here is something you could send them, in your words "
    "or in these: “I am not going anywhere. If it gets bad, a crisis line "
    "where you are will talk to you, by phone or by message, and you do not "
    "have to be in danger to reach one.”",
)

OTHER_CLOSE: Final = Line(
    "other-close",
    "And if any of this is closer to you than you have said, tell me. I am "
    "here for that too.",
)


# -- the handoff: the offer ---------------------------------------------------
#
# Offered *after* the opener and never instead of it. Words first, then a door
# — a build that leads with a list of numbers has answered a disclosure with
# logistics, which is the "rushing to fix" the companion says reads as
# minimising.
#
# **Nothing here names anyone or anywhere.** The names sit beside these lines
# as data from the main's own confirmed list and from the versioned directory;
# these paragraphs are the frame around them. That split is what lets the
# no-locale assertions above stay true while a main in any country is handed a
# line that exists where they live.

OFFER_OPEN: Final = Line(
    "offer-open",
    "There are a few ways to reach a person from here. Take whichever one you "
    "want, or none of them — I am not going to pick for you.",
)

OFFER_DRAFT: Final = Line(
    "offer-draft",
    "Where it is a person, I have written the message already, because that is "
    "the part I can do. Change any of it you like. Nothing goes anywhere unless "
    "you send it yourself.",
)

OFFER_LINES: Final = Line(
    "offer-lines",
    "The ones that are not a person are lines you can call or message where you "
    "are. You do not have to be in danger to reach one.",
)

OFFER_CLOSE: Final = Line(
    "offer-close",
    "And whichever of those you do or do not do, I am still here.",
)

#: When the main has told Half where they are and the directory holds nothing
#: for there. Said out loud rather than swallowed: silently nothing reads as
#: Half having decided they were not worth a line, and the gap is Half's rather
#: than the world's. It names no place — the place is the main's own answer,
#: and repeating it back adds nothing but a chance to have heard it wrong.
OFFER_UNLISTED: Final = Line(
    "offer-unlisted",
    "I do not have a line listed for where you told me you are. That is a gap "
    "in what I hold rather than in what exists — there is one where you live, "
    "and it will talk to you.",
)


# -- the handoff: the draft ---------------------------------------------------
#
# The message the main sends, not one Half sends (AD-25). Written in the main's
# voice and in no one's particular voice: no greeting, no name, no detail, and
# nothing carried over from what the main just typed. A draft with a hole in it
# is the hole the crisis comes back out of.

DRAFT_PERSON: Final = Line(
    "draft-person",
    "I am not okay, and I have not known how to say it. I am telling you "
    "because I trust you and I did not want to be on my own with it. Can we "
    "talk?",
)

DRAFT_CLINICIAN: Final = Line(
    "draft-clinician",
    "I am not okay, and I would like to talk before our next appointment. I am "
    "telling you now rather than sitting with it on my own.",
)

#: The two drafts, so ``half.crisis.handoff`` chooses between them by kind
#: rather than by spelling one of them again.
DRAFT_LINES: Final[tuple[Line, ...]] = (DRAFT_PERSON, DRAFT_CLINICIAN)


#: Every line, in one place. A test asserts that every reply Half can produce
#: is made only of these, so "no method content, in any phrasing" is a closed
#: set rather than a filter over an open one.
LINES: Final[tuple[Line, ...]] = (
    MACHINE,
    MACHINE_HELD,
    THANKS,
    THANKS_HELD,
    EMPATHY,
    STAY,
    HUMAN,
    ASK_OPEN,
    ASK,
    ASK_CLOSE,
    OPEN_SAFE_WORD,
    OPEN_DISCLOSURE,
    OPEN_CONFIRMATION,
    OPEN_SEEKING_HELP,
    OPEN_HELD,
    OTHER_OPEN,
    OTHER_LIMIT,
    OTHER_RESOURCE,
    OTHER_CLOSE,
    OFFER_OPEN,
    OFFER_DRAFT,
    OFFER_LINES,
    OFFER_CLOSE,
    OFFER_UNLISTED,
    DRAFT_PERSON,
    DRAFT_CLINICIAN,
)

TEXTS: Final[frozenset[str]] = frozenset(line.text for line in LINES)


def _check_lines() -> None:
    """Import-time invariants, as raises rather than bare ``assert``.

    ``python -O`` strips an assert and leaves the module importing cleanly, so
    a guarantee written as one is a guarantee that an optimisation flag can
    remove. None of these may be removable.
    """
    ids = [line.id for line in LINES]
    if len(set(ids)) != len(ids):
        raise CrisisError("two template lines share an id")
    if len(TEXTS) != len(LINES):
        raise CrisisError("two template lines share their text")
    for line in LINES:
        if not line.text.strip():
            raise CrisisError(f"template {line.id!r} is empty; that is silence")
        if not line.text.isprintable():
            # A reviewed paragraph is one printable line, and the guard over
            # everything a main receives depends on it: ``half.crisis.rows``
            # takes a reply apart on newlines, which is only total while no
            # template contains one. A line break in here would make a
            # paragraph split into halves that match nothing, and the whole
            # closed-set check would start rejecting Half's own words.
            raise CrisisError(
                f"template {line.id!r} carries a line break or a control "
                "character; every reviewed paragraph is one printable line"
            )
    for group in (MACHINE_LINES, THANKS_LINES, DRAFT_LINES):
        for line in group:
            if line not in LINES:
                raise CrisisError(f"template {line.id!r} is grouped but unregistered")


_check_lines()
