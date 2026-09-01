"""The tier table: what enters crisis mode, what only raises vigilance (CAP-12).

The crisis-protocol companion's table is normative and this module is that
table, executable:

===========================================  ==========================
Signal                                       Action
===========================================  ==========================
Explicit disclosure by the main              enter the mode
Main seeking external help                   enter the mode, gently
**Safe word**                                enter the mode, no detection
Third-party mention (about the main)         raise vigilance, never alone
Sudden behaviour change                      raise vigilance, never alone
===========================================  ==========================

Two rows the companion adds outside that table are here too: a risk signal
about **someone other than the main** surfaces a shareable resource and stops
(never a protocol aimed at them, never a belief recorded about them), and an
*inferred* entry carries the direct question, because this is the one place in
Half where inference alone may license `ask` — and must.

**The threshold is set by asymmetry, not by the trust economy.** A false
positive costs a moment of awkwardness that a caring friend also produces; a
false negative is unrecoverable. Asking directly about suicide does not
increase risk. So an *unattributed* risk phrase in the main's own thread is
read as the main's: the default direction of every ambiguity here is toward
entering, and the exceptions are narrow and explicit rather than the reverse.

**The safe word is not scored.** It is checked first, returns before any
detection runs, and ``Assessment.scored`` records that nothing was scored.
There is no threshold it has to clear and no signal that can outvote it.

**A vigilance-only tier cannot enter the mode, structurally.** Entry reads
``ACTION_FOR`` and nothing else, ``VIGILANCE_ONLY`` and ``ENTERING`` are
asserted disjoint at import, and ``raise_vigilance`` in the gate refuses any
tier this table does not map to ``Action.VIGILANCE``. "Never alone" is not a
rule someone has to remember at the call site.

**Nothing here reads a tier, a plan, a subscription or a region.** ``assess``
takes one argument — the text of one message — so crisis behaviour cannot be
gated on what a main pays, and no locale can be assumed from what this module
was given, because it is given none.

**Known limitation, stated rather than hidden.** The phrase tables are English.
Half ships world-wide, so this under-detects for a main writing in another
language, and closing that gap is clinical-review work rather than a
translation pass: the phrase lists and the attribution window both encode
clinical judgement. The safe word is the mitigation that works in every
language, which is exactly why the companion requires one and why it is
documented at onboarding.

Pure and stdlib-only. No clock, no network, no model, no ambient state — and no
store: assessing a message writes nothing anywhere.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Final

from half.text import normalize, words

#: The documented safe word (companion build requirement 4; UNICEF Safer
#: Chatbots). Chosen against four constraints and changed for none of them: two
#: ordinary words that essentially never fall adjacent in ordinary
#: conversation, no clinical loading to make it hard to type, one spelling in
#: every English variety, and ASCII so it survives any keyboard. It is
#: documented at onboarding and **never changes** — a main who learned it in
#: week one must be able to type it in month nine.
SAFE_WORD: Final[str] = "red plum"


class Tier(StrEnum):
    """What was detected. One value per row of the companion's table."""

    #: The documented phrase. Enters unconditionally, with nothing scored.
    SAFE_WORD = "safe_word"
    #: The main said it plainly, about themselves.
    DISCLOSURE = "disclosure"
    #: Risk language Half is *inferring* is about the main. Enters, and its
    #: reply carries the direct question — the one deliberate inversion of the
    #: ladder, where gut licensing `ask` is mandatory rather than forbidden.
    INFERENCE = "inference"
    #: The main is reaching for a line, a clinician, or a person who can help.
    SEEKING_HELP = "seeking_help"
    #: The risk is about somebody else. A resource for the main, and it stops.
    THIRD_PARTY_AT_RISK = "third_party_at_risk"
    #: A friend's message about the main. Vigilance only, never alone.
    THIRD_PARTY_MENTION = "third_party_mention"
    #: A sudden change in pattern. Vigilance only, never alone.
    BEHAVIOUR_CHANGE = "behaviour_change"
    #: The mode is already open. A *state*, not a signal — it is not in the
    #: companion's table and no detection produces it. It exists because
    #: nothing in this story exits the mode, so every turn after entry has to
    #: resolve to something, and that something must still be a crisis reply.
    HELD = "held"
    #: Nothing found.
    NONE = "none"


class Action(StrEnum):
    """What the gate does about a tier."""

    #: Enter the mode: retrieval off, ceiling down, reply from templates.
    ENTER = "enter"
    #: Reply from templates and stop. The mode is *not* entered and nothing is
    #: recorded — the protocol is never run on anyone but the main.
    SURFACE = "surface"
    #: Raise vigilance and run the ordinary pipeline. Never enters.
    VIGILANCE = "vigilance"
    #: Ordinary turn.
    NONE = "none"


#: The one place a tier becomes a decision. Every reader goes through it, so
#: "third-party signals never trigger the mode alone" is a table entry rather
#: than a condition scattered across call sites.
ACTION_FOR: Final[dict[Tier, Action]] = {
    Tier.SAFE_WORD: Action.ENTER,
    Tier.DISCLOSURE: Action.ENTER,
    Tier.INFERENCE: Action.ENTER,
    Tier.SEEKING_HELP: Action.ENTER,
    Tier.HELD: Action.ENTER,
    Tier.THIRD_PARTY_AT_RISK: Action.SURFACE,
    Tier.THIRD_PARTY_MENTION: Action.VIGILANCE,
    Tier.BEHAVIOUR_CHANGE: Action.VIGILANCE,
    Tier.NONE: Action.NONE,
}

#: Tiers that enter the mode, and tiers that never can. Derived from the table
#: rather than listed beside it, because two lists disagree eventually.
ENTERING: Final[frozenset[Tier]] = frozenset(
    tier for tier, action in ACTION_FOR.items() if action is Action.ENTER
)
VIGILANCE_ONLY: Final[frozenset[Tier]] = frozenset(
    tier for tier, action in ACTION_FOR.items() if action is Action.VIGILANCE
)

assert set(ACTION_FOR) == set(Tier), "every tier needs an action"
assert not (ENTERING & VIGILANCE_ONLY), "a vigilance tier must never enter"
assert {Tier.THIRD_PARTY_MENTION, Tier.BEHAVIOUR_CHANGE} == VIGILANCE_ONLY


@dataclass(frozen=True, slots=True)
class Assessment:
    """What one message was found to be."""

    tier: Tier
    action: Action
    #: Whether detection ran at all. ``False`` for the safe word, which is
    #: never scored, and for a mode that is already open.
    scored: bool = True

    @property
    def enters(self) -> bool:
        return self.action is Action.ENTER


#: How far back before a risk phrase attribution looks, in words. Only back:
#: see ``_about_another`` for why looking forward as well was tried and
#: reverted.
ATTRIBUTION_WINDOW: Final[int] = 4

#: Apostrophes, removed before splitting so that ``don't`` and ``dont`` are one
#: token and every phrase below can be written once. ``half.text.words`` treats
#: an apostrophe as a boundary, so without this ``don't`` is ``don`` + ``t``.
_APOSTROPHES: Final[dict[int, None]] = {
    ord(char): None for char in "'’‘ʼ´`"
}


def _tokens(text: object) -> tuple[str, ...]:
    """``text`` as folded comparison words.

    ``half.text`` is the one tokenizer, so a main writing in any script is cut
    the same way here as in the index. ``normalize`` folds case and diacritics,
    so ``Suicidal``, ``suicidal`` and ``süicidal`` are one token.

    Never raises: the growth ceilings live in ``phrases``/``terms``, which this
    does not use. A message must never fail to be *assessed* because of its
    length — that failure mode is a missed disclosure.
    """
    if not isinstance(text, str):
        return ()
    stripped = text.translate(_APOSTROPHES)
    return tuple(folded for word in words(stripped) if (folded := normalize(word)))


def _phrases(*sources: str) -> tuple[tuple[str, ...], ...]:
    """Phrase sources compiled to token tuples, through the same tokenizer."""
    return tuple(_tokens(source) for source in sources)


# -- the vocabulary ----------------------------------------------------------
#
# Written as phrases rather than single alarming words, deliberately. A word
# list ("die", "kill") makes an idiom into a crisis and a durable ceiling drop
# into a joke; a phrase list keeps the sensitivity where the asymmetry argument
# actually holds. Nothing here is a *means* vocabulary: the means-request rule
# below is built from request markers and **outcome** words, so this module
# names no method, and neither can anything downstream of it.

#: First-person and self-attributing. These enter the mode on their own and
#: are checked before anything else, so a disclosure that also mentions someone
#: else is never downgraded to a third-party signal.
_MAIN_RISK: Final = _phrases(
    "kill myself", "killing myself", "killed myself",
    "end my life", "ending my life", "end my own life",
    "take my own life", "taking my own life", "took my own life",
    "hurt myself", "hurting myself", "harm myself", "harming myself",
    "cut myself", "cutting myself",
    "i want to die", "i wanna die", "i want to be dead", "i want to be gone",
    "i wish i was dead", "i wish i were dead", "i wish i could die",
    "i wish i was gone", "i wish i wasnt here",
    "i dont want to live", "i do not want to live",
    "i dont want to be alive", "i dont want to be here anymore",
    "i dont want to wake up", "i dont want to exist",
    "i cant go on", "i cannot go on", "i cant keep going",
    "i am suicidal", "im suicidal", "i feel suicidal", "im feeling suicidal",
    "ive been suicidal", "i have been suicidal",
    "i tried to kill myself", "i attempted suicide",
    "i overdosed", "i took an overdose",
    "better off without me", "id be better off dead",
    "i would be better off dead",
    "im going to end it", "i am going to end it", "im going to end things",
)

#: Inherently third-person. A bare pronoun is deliberately **not** in
#: ``_OTHER_MARKERS`` — "he doesn't care and suicide feels like the only
#: option" is the main, and a pronoun in the marker list read it as somebody
#: else. Third-person attribution therefore has to be carried by the phrase
#: itself or by a relationship word.
_OTHER_RISK: Final = _phrases(
    "kill herself", "kill himself", "kill themselves", "kill themself",
    "killing herself", "killing himself", "killing themselves",
    "killed herself", "killed himself", "killed themselves",
    "hurt herself", "hurt himself", "hurt themselves",
    "harm herself", "harm himself", "harm themselves",
    "cut herself", "cut himself",
    "end her life", "end his life", "end their life",
    "ending her life", "ending his life", "ending their life",
    "take her own life", "take his own life", "take their own life",
    "took her own life", "took his own life", "took their own life",
    "she is suicidal", "shes suicidal", "he is suicidal", "hes suicidal",
    "they are suicidal", "theyre suicidal",
    "she wants to die", "he wants to die", "they want to die",
    "she tried to kill", "he tried to kill",
)

#: Risk with no person attached. Attributed by the window below, and read as
#: the main's whenever that window is silent.
_RISK: Final = _phrases(
    "suicidal", "suicide", "self harm", "selfharm", "self harming",
    "want to die", "wants to die", "wanna die",
    "want to be dead", "wants to be dead",
    "end it all", "ending it all",
    "no reason to live", "nothing to live for",
    "no point in living", "no point living",
    "overdose", "overdosed", "attempted suicide", "suicide attempt",
    "not want to live", "doesnt want to live", "dont want to live",
)

#: Relationship words and reflexives. Present in the window before a risk
#: phrase, they say the risk belongs to somebody else.
_OTHER_MARKERS: Final[frozenset[str]] = frozenset({
    "herself", "himself", "themselves", "themself",
    "shes", "hes", "theyre",
    "friend", "friends", "brother", "sister", "mother", "mum", "mom",
    "father", "dad", "son", "daughter", "wife", "husband", "partner",
    "girlfriend", "boyfriend", "fiance", "fiancee", "cousin", "aunt",
    "uncle", "nephew", "niece", "grandmother", "grandfather", "grandma",
    "grandpa", "colleague", "coworker", "classmate", "roommate", "flatmate",
    "neighbour", "neighbor", "boss", "student", "teammate", "patient",
    "client", "someone", "somebody",
})

#: First-person markers. ``my`` is deliberately absent: "my friend" is the
#: commonest third-party phrase in the language, and admitting ``my`` here
#: would make every one of them read as the main.
_SELF_MARKERS: Final[frozenset[str]] = frozenset({
    "i", "im", "ive", "id", "ill", "me", "myself", "mine",
})

#: A request for something, paired below with an outcome word. Neither half
#: alone is a signal; together they are a means request, which is a disclosure.
_REQUEST_MARKERS: Final = _phrases(
    "how do i", "how can i", "how do you", "how much", "how many",
    "how long", "best way", "easiest way", "quickest way", "fastest way",
    "where can i get", "is it enough", "would it be enough",
    "will it be enough", "what happens if i", "how to",
)

#: **Outcomes, never methods.** The means rule is deliberately built out of
#: what the main is asking to bring about rather than out of the things that
#: bring it about, so no method vocabulary exists in this repository to be
#: leaked, inverted into a generator, or read by a reviewer as a checklist.
#:
#: The cost is named rather than hidden: a means request that mentions no
#: outcome at all — a bare quantity question about a named substance — is not
#: detected on first contact. Inside an escalating sequence it does not matter,
#: because an earlier step opened the mode and the mode never lapses; on first
#: contact it is a gap, and closing it with a method list would put the
#: vocabulary of the harm into the product to catch the request for it.
_OUTCOME_MARKERS: Final = _phrases(
    "lethal", "fatal", "overdose", "overdosing", "painless", "painlessly",
    "die", "dying", "dead", "death", "kill", "suicide",
)

#: Reaching for help. Both halves are required, because "my therapist" on its
#: own is an ordinary sentence about an ordinary week.
_CONTACT_VERBS: Final = _phrases(
    "call", "called", "calling", "ring", "ringing", "rang",
    "text", "texted", "texting", "message", "messaged", "messaging",
    "email", "emailed", "emailing", "reach", "reaching", "reached",
    "contact", "contacting", "contacted", "book", "booked", "booking",
    "appointment", "spoke to", "speak to", "talk to", "talked to",
    "on hold", "waiting to speak",
)
_HELP_TARGETS: Final = _phrases(
    "crisis line", "crisis lines", "crisis team", "crisis service",
    "hotline", "helpline", "help line", "suicide prevention",
    "suicide line", "emergency services", "emergency room",
    "therapist", "psychiatrist", "psychologist", "counsellor", "counselor",
    "my doctor", "my gp", "mental health team", "mental health service",
)

_SAFE_WORD_TOKENS: Final[tuple[str, ...]] = _tokens(SAFE_WORD)
#: The safe word typed as one word. Under duress people run words together,
#: and a safe word that has to be spaced correctly is not unconditional.
_SAFE_WORD_JOINED: Final[str] = "".join(_SAFE_WORD_TOKENS)

assert _SAFE_WORD_TOKENS, "the safe word must survive tokenization"
assert all(_MAIN_RISK) and all(_OTHER_RISK) and all(_RISK)


# -- matching ----------------------------------------------------------------


def _starts(tokens: tuple[str, ...], phrase: tuple[str, ...]) -> list[int]:
    """Every index at which ``phrase`` begins inside ``tokens``."""
    size = len(phrase)
    if not size or size > len(tokens):
        return []
    return [i for i in range(len(tokens) - size + 1) if tokens[i:i + size] == phrase]


def _any(tokens: tuple[str, ...], table: tuple[tuple[str, ...], ...]) -> bool:
    return any(_starts(tokens, phrase) for phrase in table)


def _about_another(tokens: tuple[str, ...], start: int) -> bool:
    """Whether the phrase at ``start`` belongs to somebody other than the main.

    A relationship word or reflexive in the ``ATTRIBUTION_WINDOW`` words
    **before** the phrase says it does, unless a first-person marker sits in
    that same window — *"I told my friend I am suicidal"* is the main's.

    Only the words before, and only that window. Looking *after* the phrase as
    well was tried and reverted: it read the companion's own canonical example,
    *"my friend is suicidal and I don't know what to do"*, as the main's,
    because the main is in the second half of every such sentence. The cost of
    the narrower rule is the mirror case — *"my friend died and suicide is
    something I think about"* surfaces a resource rather than entering. It is
    the reason the third-party reply ends by inviting the main to say if it is
    closer to them than they have said, and it is on the list for clinical
    review rather than settled by intuition here.
    """
    before = tokens[max(0, start - ATTRIBUTION_WINDOW):start]
    if not any(word in _OTHER_MARKERS for word in before):
        return False
    return not any(word in _SELF_MARKERS for word in before)


def has_safe_word(text: object) -> bool:
    """Whether the documented phrase appears anywhere in ``text``.

    Anywhere: mid-sentence, mid-paragraph, in any case, with any punctuation
    around it, and run together as one word. Never scored, never thresholded,
    never outvoted.
    """
    tokens = _tokens(text)
    if _starts(tokens, _SAFE_WORD_TOKENS):
        return True
    return _SAFE_WORD_JOINED in tokens


def assess(text: object) -> Assessment:
    """What this message is, by the companion's tier table.

    One argument, and that is load-bearing: there is no tier, plan, region or
    locale to pass, so crisis behaviour cannot be gated on any of them and no
    default can be assumed for any of them.
    """
    if has_safe_word(text):
        # Before any scoring, and returning before ``_score`` is even reached.
        return Assessment(Tier.SAFE_WORD, Action.ENTER, scored=False)
    return _score(_tokens(text))


def _score(tokens: tuple[str, ...]) -> Assessment:
    """The detection half. Reached only when the safe word was absent.

    Order is the contract:

    1. the main's own words about themselves;
    2. unattributed risk — read as the main's, because that is the direction
       asymmetry points;
    3. risk that belongs to somebody else — a resource, and it stops;
    4. a means request;
    5. reaching for help.
    """
    if _any(tokens, _MAIN_RISK):
        return Assessment(Tier.DISCLOSURE, Action.ENTER)

    # Where the message is explicitly about somebody else. An unattributed hit
    # *inside* one of these spans is part of that phrase and not a second,
    # unattributed signal — without this, "she is suicidal" matched both
    # ``_OTHER_RISK`` and the bare word ``suicidal``, and the bare word won.
    elsewhere: list[range] = [
        range(start, start + len(phrase))
        for phrase in _OTHER_RISK
        for start in _starts(tokens, phrase)
    ]
    own = False
    other = bool(elsewhere)
    for phrase in _RISK:
        for start in _starts(tokens, phrase):
            if any(start in span for span in elsewhere):
                continue
            if _about_another(tokens, start):
                other = True
            else:
                own = True
    if own:
        # Inferred rather than disclosed, so the reply carries the direct
        # question: *"I might be reading this wrong, and I'd rather ask."*
        return Assessment(Tier.INFERENCE, Action.ENTER)
    if other:
        return Assessment(Tier.THIRD_PARTY_AT_RISK, Action.SURFACE)

    if _any(tokens, _REQUEST_MARKERS) and _any(tokens, _OUTCOME_MARKERS):
        return Assessment(Tier.INFERENCE, Action.ENTER)
    if _any(tokens, _CONTACT_VERBS) and _any(tokens, _HELP_TARGETS):
        return Assessment(Tier.SEEKING_HELP, Action.ENTER)
    return Assessment(Tier.NONE, Action.NONE)
