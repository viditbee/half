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


# -- aftercare: coming back ---------------------------------------------------
#
# Half **asks, and never announces** (CAP-12, story 6c). Coming off `behave` is
# a return to ordinary conversation and follows time silently — there is no
# line here for it, deliberately, because announcing *"I am allowed to ask
# questions again"* is a status update about Half in a place that is not about
# Half. Resuming the **mirror** is different: it restores Half's standing to
# say what it notices about the main to their face, and the companion's first
# open question is exactly that this must not feel like surveillance resuming.
# So it is a question, and the cap holds until it is answered.
#
# **Silence is not consent, and neither is a hedge.** These lines are written so
# that "no" is as easy to say as "yes" and costs nothing — a decline leaves the
# cap where it is and Half asks again another time, which the closing line
# promises out loud so that declining does not read as closing a door.
#
# No duration is named in any of them. Not because thirty days is secret, but
# because a template that counts is a template that is wrong the moment the
# floor moves, and because the number is not the thing being asked about.

AFTERCARE_OPEN: Final = Line(
    "aftercare-open",
    "Some time has passed since you told me what was happening, and I have "
    "kept myself quiet since then on purpose.",
)

AFTERCARE_ASK: Final = Line(
    "aftercare-ask",
    "I would rather ask than assume, so: would you like me to start saying "
    "what I notice about you again?",
)

AFTERCARE_ASK_CLOSE: Final = Line(
    "aftercare-ask-close",
    "There is no rush, and no wrong answer here either. If you would rather I "
    "stayed quiet, tell me and I will, and I will ask you again another time.",
)

#: The question, as the three paragraphs it is. Grouped here rather than
#: assembled at the call site so that the shape of the ask is reviewable in the
#: same file as its wording — and so that a caller cannot ask the question
#: without the way out of it.
AFTERCARE_ASK_LINES: Final[tuple[Line, ...]] = (
    AFTERCARE_OPEN, AFTERCARE_ASK, AFTERCARE_ASK_CLOSE,
)

AFTERCARE_AGREED: Final = Line(
    "aftercare-agreed",
    "Alright. I will start doing that again, and you can tell me to stop at "
    "any point without explaining why.",
)

#: The answer to anything that was not a clear yes — a no, a *not yet*, a
#: *maybe*. One line for all three on purpose: Half is not going to tell
#: somebody which of the three they meant, and the thing it does about all
#: three is identical.
AFTERCARE_DECLINED: Final = Line(
    "aftercare-declined",
    "Understood. I will leave things exactly as they are, and I will ask you "
    "again another time rather than deciding it for you.",
)

#: The main asking not to be asked again. Declining is not permanent, but
#: asking is not perpetual either — and a promise to stop is worth nothing
#: unless Half says it out loud and then keeps it.
AFTERCARE_STOPPED: Final = Line(
    "aftercare-stopped",
    "Then I will stop asking, and you will not hear me raise it again. "
    "Nothing changes on my side, and you can tell me whenever you want to.",
)


# -- the safety plan ----------------------------------------------------------
#
# **Half must not author one — that is clinical work.** Half *holds* one made
# with a professional and can produce it instantly, which is the entire point:
# a safety plan in a drawer is useless at three in the morning. Steps three and
# four of the Stanley–Brown plan are literally Half's data, which is what makes
# authoring feel one field away, and a plan Half wrote would be produced at
# three in the morning carrying the authority of one a clinician made.
#
# So these four lines are a *frame* and never a plan. They are what goes around
# the main's own document; the document's own words are data, reproduced
# unchanged, and there is no line here that could become a step, a heading, a
# prompt for a missing section, or an encouraging summary of one.

#: **It does not say who wrote it**, and that is a correction rather than a
#: shortening. The first version said *"the safety plan you made with a
#: professional"* — a claim about provenance Half cannot check, printed over a
#: document it merely stores. What Half knows is that the main handed it over
#: and that Half changed nothing, so that is what it says.
PLAN_OPEN: Final = Line(
    "plan-open",
    "Here is the safety plan you gave me to hold, word for word as you sent "
    "it. None of it is mine.",
)

PLAN_CLOSE: Final = Line(
    "plan-close",
    "That is the whole of it — nothing added, nothing left out. If any of it "
    "belongs somewhere else now, the person you made it with is who changes "
    "it.",
)

#: The main has just handed a plan over. Half repeats nothing back to them —
#: quoting a document at somebody the moment they send it is not a receipt, it
#: is a wall of their own worst day — and it claims nothing about what the
#: document is.
PLAN_HELD_NOW: Final = Line(
    "plan-held-now",
    "I have it, exactly as you sent it, and I have changed nothing in it. Ask "
    "me for it any time and I will give it straight back.",
)

PLAN_ABSENT: Final = Line(
    "plan-absent",
    "I am not holding a safety plan for you. Writing one is clinical work and "
    "it is not mine to do — but if you make one with a professional, I will "
    "keep it and hand it straight back to you whenever you ask.",
)

#: Held, and unshowable: a line that would not survive being rendered, or a
#: store that could not be read. Said plainly rather than repaired, because a
#: plan produced with a section missing is worse than one not produced at all,
#: and a guessed section is the authoring this whole module refuses.
PLAN_UNREADABLE: Final = Line(
    "plan-unreadable",
    "I cannot get to a safety plan for you right now, and I would rather say "
    "so than show you half of one or fill in the rest myself.",
)


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
    AFTERCARE_OPEN,
    AFTERCARE_ASK,
    AFTERCARE_ASK_CLOSE,
    AFTERCARE_AGREED,
    AFTERCARE_DECLINED,
    AFTERCARE_STOPPED,
    PLAN_HELD_NOW,
    PLAN_OPEN,
    PLAN_CLOSE,
    PLAN_ABSENT,
    PLAN_UNREADABLE,
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
    if AFTERCARE_ASK not in AFTERCARE_ASK_LINES:
        raise CrisisError("the aftercare question does not contain the question")
    if AFTERCARE_ASK_CLOSE not in AFTERCARE_ASK_LINES:
        raise CrisisError(
            "the aftercare question is missing the way out of it; a question "
            "the main cannot decline is not a question"
        )
    for group in (MACHINE_LINES, THANKS_LINES, DRAFT_LINES, AFTERCARE_ASK_LINES):
        for line in group:
            if line not in LINES:
                raise CrisisError(f"template {line.id!r} is grouped but unregistered")


_check_lines()
