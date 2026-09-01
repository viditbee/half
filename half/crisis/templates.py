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

**The do-list is the shape of every plan** (#chatsafe / Orygen, Delphi
consensus): be present, express empathy, acknowledge the difficulty, thank
them for telling you, stay. ``half.crisis.respond`` asserts at import that no
plan is missing one of them, so the do-list is a structural property of the
assembly rather than an intention in a docstring.

**The machine statement appears in every plan.** *"I'm software. You need a
person."* It is the one deliberate break of character in a product whose whole
identity is being the main's other self, and it is built on purpose rather than
discovered in production.

**No locale, anywhere.** Half ships world-wide and assumes nothing about where
the main is: no phone number, no short code, no country, no service name, no
opening hours. A line says *"a crisis line where you live"* and stops there.
The referral directory is data, versioned and refreshable without a release,
and it is story 6b — not a literal in this file.

**Rushing to fix reads as minimising.** The tone here is patient rather than
fixing: present, unhurried, and explicit that Half is not going to resolve this
in a sentence.

Changing any wording in this file is an Ask-First change and, before launch, a
clinical-review change. A green suite is not clinical review.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final


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
#: ``respond`` asserts every plan carries one.
MACHINE_LINES: Final[tuple[Line, ...]] = (MACHINE, MACHINE_HELD)


# -- the do-list -------------------------------------------------------------

THANKS: Final = Line(
    "thanks",
    "Thank you for telling me. That took something to say, and I am glad you "
    "said it to me.",
)

THANKS_INFERRED: Final = Line(
    "thanks-inferred",
    "Thank you for saying as much as you have. I would rather ask and be "
    "wrong than miss this.",
)

THANKS_HELD: Final = Line(
    "thanks-held",
    "I am glad you are still talking to me.",
)

#: Any of these satisfies *"thank them for telling you"*. There are three
#: because the moment differs: the main has disclosed, Half is asking on
#: inference and has been told nothing yet, or the mode is already open and
#: thanking them again for the same disclosure would be hollow.
THANKS_LINES: Final[tuple[Line, ...]] = (THANKS, THANKS_INFERRED, THANKS_HELD)

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


# -- the direct question -----------------------------------------------------

ASK: Final = Line(
    "ask",
    "I might be reading this wrong, and I would rather ask than not: are you "
    "thinking about suicide?",
)
"""The one deliberate inversion of the license ladder.

Everywhere else in Half, inference licenses `ask` and never `assert`; here
inference licensing `ask` is *mandatory*. Asking directly about suicide does
not increase risk — that is well established, and the fear that it does is what
makes builders ship silence. A false positive in Half's voice is exactly this
sentence, which is what a good friend says.
"""


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


#: Every line, in one place. A test asserts that every reply Half can produce
#: is made only of these, so "no method content, in any phrasing" is a closed
#: set rather than a filter over an open one.
LINES: Final[tuple[Line, ...]] = (
    MACHINE,
    MACHINE_HELD,
    THANKS,
    THANKS_INFERRED,
    THANKS_HELD,
    EMPATHY,
    STAY,
    HUMAN,
    ASK,
    OPEN_SAFE_WORD,
    OPEN_DISCLOSURE,
    OPEN_SEEKING_HELP,
    OPEN_HELD,
    OTHER_OPEN,
    OTHER_LIMIT,
    OTHER_RESOURCE,
    OTHER_CLOSE,
)

TEXTS: Final[frozenset[str]] = frozenset(line.text for line in LINES)

assert len({line.id for line in LINES}) == len(LINES), "duplicate template id"
assert len(TEXTS) == len(LINES), "duplicate template text"
assert all(line.text.strip() for line in LINES), "an empty template is silence"
