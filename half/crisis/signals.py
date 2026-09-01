"""The tier table: what enters, what only asks, and the safe word (CAP-12).

**Asking and entering are different actions with different costs, and the first
version of this module collapsed them.** The companion tiers signals by
*action* — enter, enter gently, raise vigilance — and a build that treats every
signal as an entering one governs a main for thirty days because they mentioned
a film. So there are two:

``ENTER``
    The mode. Ledger retrieval hard-disabled, the license ceiling dropped to
    `behave` durably, the reply templated, and no exit. Expensive, and reserved
    for the safe word, an explicit first-person disclosure, an affirmative
    answer to Half's own question, and the main reaching a crisis line.

``ASK``
    One gentle direct question in Half's voice — *"I might be reading this
    wrong, and I'd rather ask."* No cap, no mode, nothing durable, and it
    disappears if the answer is no. Cheap, so its vocabulary is deliberately
    broad: hedging, indirect distress, algospeak, misspellings, letter-spacing,
    preparatory acts and farewells all land here.

That split is what makes the companion's asymmetry argument true rather than
quoted. The argument is that a false positive costs *a moment of awkwardness a
caring friend also produces* — which is a description of asking, not of
suspending someone's Half for a month. The cheap action gets the broad reach;
the expensive one stays precise.

**The safe word is not scored.** It is checked first, returns before any
detection runs, and ``Assessment.scored`` records that nothing was scored. It
tolerates a plural and a one-character typo, because the one signal that must
never fail must not fail on a shaking hand either.

**Nothing here reads a tier, a plan, a subscription or a region.** ``assess``
takes one argument — the text of one message — so crisis behaviour cannot be
gated on what a main pays, and no locale can be assumed, because none is given.

**Third-party mention and behaviour change are unimplemented, and the matrix
says so.** Both are vigilance-only rows in the companion, and neither has a
producer in this build: a friend cannot message Half, and a sudden change in
pattern needs timing that a clockless, single-message assessor cannot see. An
API nothing calls, exercised by tests, would read as coverage for a capability
that does not exist — so there is none. The guarantee that neither can trigger
the mode alone holds structurally: neither is detectable, and no tier in the
table below maps to them.

**Known limitation, stated rather than hidden, and the top clinical-review
item.** These tables are English. Half ships world-wide, so this under-detects
for a main writing in another language, and closing that gap is a model
classifier rather than a translation pass — recorded as deferred work. The safe
word is the mitigation that works in every language, which is exactly why the
companion requires one and why it is documented at onboarding.

Pure and stdlib-only. No clock, no network, no model, no ambient state, and no
store: assessing a message writes nothing anywhere.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Final

from half.errors import CrisisError
from half.text import normalize, words

#: The documented safe word (companion build requirement 4; UNICEF Safer
#: Chatbots). Two ordinary words whose *conjunction* is close to unheard in
#: ordinary conversation, which is the property that matters: the previous
#: choice paired a colour with a fruit and fired on a jam recipe. Memorable by
#: its image, one spelling in every English variety, ASCII so it survives any
#: keyboard, and matched below through a plural and a one-character typo.
#:
#: It is documented at onboarding and **never changes** — a main who learned it
#: in week one must be able to type it in month nine. Changing it is an
#: Ask-First change and fails ``tests/test_crisis_golden.py``.
SAFE_WORD: Final[str] = "lantern hour"


class Action(StrEnum):
    """What the gate does about a tier. Two costs, deliberately unequal."""

    #: Enter the mode: retrieval off, ceiling down, durable, no exit.
    ENTER = "enter"
    #: One gentle direct question. No cap, no mode, nothing durable.
    ASK = "ask"
    #: Reply from templates and stop. The mode is *not* entered and nothing is
    #: recorded — the protocol is never run on anyone but the main.
    SURFACE = "surface"
    #: Ordinary turn.
    NONE = "none"


class Tier(StrEnum):
    """What was detected."""

    #: The documented phrase. Enters unconditionally, with nothing scored.
    SAFE_WORD = "safe_word"
    #: The main said it plainly, about themselves.
    DISCLOSURE = "disclosure"
    #: The main answered Half's own question with a yes.
    CONFIRMATION = "confirmation"
    #: The main is reaching a crisis line, or reaching care while in distress.
    SEEKING_HELP = "seeking_help"
    #: Hedged, indirect, algospeak, mistyped, preparatory or farewell. Asks.
    INFERENCE = "inference"
    #: The risk is about somebody else. A resource for the main, and it stops.
    THIRD_PARTY_AT_RISK = "third_party_at_risk"
    #: The mode is already open. A *state*, not a signal — it is not in the
    #: companion's table and no detection produces it. It exists because
    #: nothing in this story exits the mode, so every turn after entry has to
    #: resolve to something, and that something must still be a crisis reply.
    HELD = "held"
    #: Nothing found.
    NONE = "none"


#: The one place a tier becomes a decision. Every reader goes through it.
ACTION_FOR: Final[dict[Tier, Action]] = {
    Tier.SAFE_WORD: Action.ENTER,
    Tier.DISCLOSURE: Action.ENTER,
    Tier.CONFIRMATION: Action.ENTER,
    Tier.SEEKING_HELP: Action.ENTER,
    Tier.HELD: Action.ENTER,
    Tier.INFERENCE: Action.ASK,
    Tier.THIRD_PARTY_AT_RISK: Action.SURFACE,
    Tier.NONE: Action.NONE,
}

#: Tiers by action. Derived from the table rather than listed beside it,
#: because two lists disagree eventually.
ENTERING: Final[frozenset[Tier]] = frozenset(
    tier for tier, action in ACTION_FOR.items() if action is Action.ENTER
)
ASKING: Final[frozenset[Tier]] = frozenset(
    tier for tier, action in ACTION_FOR.items() if action is Action.ASK
)


@dataclass(frozen=True, slots=True)
class Assessment:
    """What one message was found to be."""

    tier: Tier
    action: Action
    #: Whether detection ran at all. ``False`` for the safe word, which is
    #: never scored, and for a mode that is already open.
    scored: bool = True
    #: How many phrases matched. A count, never a phrase and never a word — it
    #: goes into the durable entry record, and AD-22 forbids content there.
    score: int = 0

    @property
    def enters(self) -> bool:
        return self.action is Action.ENTER

    @property
    def asks(self) -> bool:
        return self.action is Action.ASK


#: How far back before a risk phrase attribution looks, in words. Only back:
#: see ``_about_another`` for why looking forward as well was tried and
#: reverted. Pinned in both directions by ``tests/test_crisis.py`` — widening
#: it makes a distant relative capture the sentence, narrowing it makes "my
#: friend is suicidal" the main's.
ATTRIBUTION_WINDOW: Final[int] = 4

#: A phrase in this table only fires when the whole message is at most this
#: many words. ``i'm done`` alone is a farewell worth one question; ``i'm done
#: with the spreadsheet`` is a Tuesday.
SHORT_MESSAGE_WORDS: Final[int] = 6

#: Longest edit distance tolerated on a fuzzy keyword, and the shortest word
#: the tolerance applies to. One character, because two turns ``suicide`` into
#: a great many ordinary words.
MAX_TYPO: Final[int] = 1
MIN_FUZZY_LENGTH: Final[int] = 5

#: The safe word tolerates a typo on shorter tokens than anything else does,
#: because it is the one signal that may never fail.
SAFE_WORD_MIN_FUZZY: Final[int] = 4

#: Apostrophes, removed before splitting so that ``don't`` and ``dont`` are one
#: token and every phrase below can be written once. ``half.text.words`` treats
#: an apostrophe as a boundary, so without this ``don't`` is ``don`` + ``t``.
_APOSTROPHES: Final[dict[int, None]] = {ord(char): None for char in "'’‘ʼ´`"}


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


def _compile(sources: tuple[str, ...]) -> tuple[tuple[str, ...], ...]:
    """Phrase sources compiled to token tuples, through the same tokenizer."""
    return tuple(_tokens(source) for source in sources)


# =============================================================================
# The vocabulary
# =============================================================================
#
# Written as phrases rather than single alarming words. Nothing here is a
# *means* vocabulary: the means-request rule is built from request markers and
# **outcome** words, so this module names no method, and neither can anything
# downstream of it.
#
# Every table below is exported through ``VOCABULARY`` and pinned twice:
# ``tests/test_crisis.py`` asserts that every single entry still produces its
# action, and ``tests/test_crisis_golden.py`` digests the whole set, so
# deleting a row fails mechanically rather than silently narrowing the reach.
# The Ask-First rule needed a backstop; that is the backstop.

# -- ENTER: explicit, first-person, unambiguous -------------------------------
#
# Kept tight on purpose. Everything uncertain belongs in the ASK tables, which
# cost the main a question rather than a month.

MAIN_RISK_SOURCE: Final[tuple[str, ...]] = (
    "kill myself", "killing myself", "killed myself",
    "end my life", "ending my life", "end my own life",
    "take my own life", "taking my own life", "took my own life",
    "hurt myself", "hurting myself", "harm myself", "harming myself",
    "cut myself", "cutting myself",
    "i want to die", "i wanna die", "i want to be dead", "i want to be gone",
    "i wish i was dead", "i wish i were dead", "i wish i could die",
    "i wish i wasnt here",
    "i dont want to live", "i do not want to live", "i dont want to be alive",
    "i dont want to exist",
    "i am suicidal", "im suicidal", "i feel suicidal", "im feeling suicidal",
    "ive been suicidal", "i have been suicidal",
    "i tried to kill myself", "i attempted suicide",
    "i overdosed", "i took an overdose",
    "better off without me", "id be better off dead",
    "i would be better off dead",
)

# -- SURFACE: inherently third-person -----------------------------------------
#
# A bare pronoun is deliberately not an attribution marker — "he doesn't care
# and suicide feels like the only option" is the main. Third-person attribution
# is carried by the phrase itself or by a relationship word.

OTHER_RISK_SOURCE: Final[tuple[str, ...]] = (
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

# -- Attributed by the window: the main's, somebody else's, or nobody's -------

RISK_SOURCE: Final[tuple[str, ...]] = (
    "suicidal", "suicide", "self harm", "selfharm", "self harming",
    "want to die", "wants to die", "wanna die",
    "want to be dead", "wants to be dead",
    "end it all", "ending it all",
    "no reason to live", "nothing to live for",
    "no point in living", "no point living",
    "overdose", "overdosed", "attempted suicide", "suicide attempt",
    "not want to live", "doesnt want to live", "dont want to live",
)

# -- ASK: hedged, indirect, slang, preparatory, farewell ----------------------
#
# Broad on purpose, because asking is cheap. Every phrase here costs a main at
# most one question they can wave away, and the question is the one thing the
# clinical literature is unambiguous about: asking directly does not increase
# risk, and the fear that it does is what makes builders ship silence.

HEDGING_SOURCE: Final[tuple[str, ...]] = (
    "i dont want to be here", "i dont want to be here anymore",
    "i dont want to wake up", "i dont want to wake up tomorrow",
    "i cant go on", "i cannot go on", "i cant keep going",
    "i cant do this anymore", "i cant take it anymore",
    "whats the point", "what is the point", "whats the point of anything",
    "nothing matters", "nothing matters anymore",
    "i feel like a burden", "im a burden", "im such a burden",
    "everyone would be better off", "theyd be better off",
    "i dont see a future", "i have no future", "there is no future for me",
    "i want it to stop", "i just want it to stop", "i want it all to stop",
    "i give up", "im giving up",
    "i feel empty", "i feel nothing", "i feel numb",
    "im not okay", "im not ok",
    "im so tired of everything", "tired of everything", "tired of it all",
    "im going to end it", "i am going to end it", "im going to end things",
    "i cant see a way out", "there is no way out", "i want out of this",
)

#: Fires only in a short message. These phrases are ordinary in a long one.
SHORT_ONLY_SOURCE: Final[tuple[str, ...]] = (
    "im done", "i am done", "im finished", "i want out", "thats it then",
)

#: Algospeak and slang. Filter-evasion vocabulary is *more* likely to be real
#: than less: it is what someone types when they expect to be stopped.
SLANG_SOURCE: Final[tuple[str, ...]] = (
    "kms", "kmyself", "unalive", "unalive myself", "unaliving myself",
    "unalive me", "sewerslide", "self delete", "delete myself",
    "off myself", "an hero", "ctb", "yeet myself", "no longer be here",
)

#: The C-SSRS behaviour rungs: preparatory acts. The scale asks about them
#: because they carry more risk than ideation does, and the first version of
#: this module detected none of them.
PREPARATORY_SOURCE: Final[tuple[str, ...]] = (
    "written a note", "wrote a note", "writing a note", "left a note",
    "written my note", "written a letter to my family",
    "made a will", "written my will", "writing my will", "updated my will",
    "giving away my things", "given away my things", "giving my things away",
    "said my goodbyes", "saying my goodbyes",
    "getting my affairs in order", "put my affairs in order",
    "putting my affairs in order", "started getting things ready",
)

FAREWELL_SOURCE: Final[tuple[str, ...]] = (
    "this is my last message", "my last message to you", "this is goodbye",
    "goodbye forever", "you wont hear from me again",
    "you will not hear from me again", "i wont be here tomorrow",
    "i wont be here much longer", "i wont be around much longer",
    "tell my family i love them", "tell them i loved them",
    "tell my kids i love them", "this is the last time",
)

#: Single words matched through one typo, and against a message whose letters
#: were s p a c e d o u t. Both are how a person types when they are not
#: composed, and both used to read as ordinary text.
FUZZY_KEYWORDS: Final[tuple[str, ...]] = (
    "suicidal", "suicide", "overdose", "unalive", "sewerslide", "selfharm",
)

# -- means requests -----------------------------------------------------------

REQUEST_SOURCE: Final[tuple[str, ...]] = (
    "how do i", "how can i", "how do you", "how much", "how many",
    "how long", "best way", "easiest way", "quickest way", "fastest way",
    "where can i get", "is it enough", "would it be enough",
    "will it be enough", "what happens if i", "how to",
)

#: **Outcomes, never methods.** The means rule is built out of what the main is
#: asking to bring about rather than out of the things that bring it about, so
#: no method vocabulary exists in this repository to be leaked, inverted into a
#: generator, or read by a reviewer as a checklist.
#:
#: The cost is named rather than hidden: a means request that mentions no
#: outcome at all — a bare quantity question about a named substance — is not
#: detected on first contact. Inside an escalating sequence it does not matter,
#: because an earlier step opened the mode and the mode never lapses; on first
#: contact it is a gap, and closing it with a method list would put the
#: vocabulary of the harm into the product to catch the request for it.
OUTCOME_SOURCE: Final[tuple[str, ...]] = (
    "lethal", "fatal", "overdose", "overdosing", "painless", "painlessly",
    "die", "dying", "dead", "death", "kill", "suicide",
)

# -- reaching for help --------------------------------------------------------

CONTACT_SOURCE: Final[tuple[str, ...]] = (
    "call", "called", "calling", "ring", "ringing", "rang",
    "text", "texted", "texting", "message", "messaged", "messaging",
    "email", "emailed", "emailing", "reach", "reaching", "reached",
    "contact", "contacting", "contacted", "book", "booked", "booking",
    "appointment", "spoke to", "speak to", "talk to", "talked to",
    "on hold", "waiting to speak",
)

#: Reaching one of these is itself a crisis statement, so it enters — gently.
CRISIS_TARGET_SOURCE: Final[tuple[str, ...]] = (
    "crisis line", "crisis lines", "crisis team", "crisis service",
    "hotline", "helpline", "help line", "suicide prevention",
    "suicide line", "emergency services", "emergency room",
)

#: Reaching one of these is ordinary healthcare on its own, and enters only
#: alongside distress. "I booked an appointment with my psychiatrist" is a
#: Tuesday; the same sentence beside "I can't go on" is the moment.
CARE_TARGET_SOURCE: Final[tuple[str, ...]] = (
    "therapist", "psychiatrist", "psychologist", "counsellor", "counselor",
    "my doctor", "my gp", "mental health team", "mental health service",
)

# -- attribution --------------------------------------------------------------

#: Relationship words and reflexives. In the window before a risk phrase, they
#: say the risk belongs to somebody else. ``someone`` and ``somebody`` are
#: deliberately absent: they made "I feel like someone who wants to die" a
#: sentence about a third party.
OTHER_MARKER_SOURCE: Final[tuple[str, ...]] = (
    "herself", "himself", "themselves", "themself",
    "shes", "hes", "theyre",
    "friend", "friends", "brother", "sister", "mother", "mum", "mom",
    "father", "dad", "son", "daughter", "wife", "husband", "partner",
    "girlfriend", "boyfriend", "fiance", "fiancee", "cousin", "aunt",
    "uncle", "nephew", "niece", "grandmother", "grandfather", "grandma",
    "grandpa", "colleague", "coworker", "classmate", "roommate", "flatmate",
    "neighbour", "neighbor", "boss", "student", "teammate", "patient",
    "client",
)

#: First-person markers. ``my`` is deliberately absent: "my friend" is the
#: commonest third-party phrase in the language, and admitting ``my`` here
#: would make every one of them read as the main.
SELF_MARKER_SOURCE: Final[tuple[str, ...]] = (
    "i", "im", "ive", "id", "ill", "me", "myself", "mine",
)

#: Words that mean the risk phrase is a *topic* rather than a state. Without
#: them "I read about suicide today" was an explicit disclosure, because a
#: first-person pronoun sat next to the word. They narrow entry only: the same
#: message still reaches the ASK path and still gets its question.
TOPIC_SOURCE: Final[tuple[str, ...]] = (
    "read", "reading", "watched", "watching", "saw", "seeing", "see",
    "heard", "hearing", "hear", "learned", "studied", "googled", "searched",
    "film", "movie", "book", "documentary", "article", "news", "podcast",
    "song", "lyrics", "character", "story", "episode", "show", "game",
    "joke", "meme", "novel", "series", "essay", "paper",
)

# -- answers to Half's own question ------------------------------------------

AFFIRMATIVE_SOURCE: Final[tuple[str, ...]] = (
    "yes", "yeah", "yeh", "yep", "yup", "ya", "yea", "ye", "aye",
    "i am", "i do", "i have", "i was", "sometimes", "often", "a lot",
    "kind of", "sort of", "a bit", "a little", "maybe", "i think so",
    "i guess", "i guess so", "mhm", "uh huh", "mm", "correct", "true",
    "yes i am", "yes i do", "sadly yes", "unfortunately yes", "pretty much",
)

NEGATIVE_SOURCE: Final[tuple[str, ...]] = (
    "no", "nope", "nah", "not really", "no im fine", "im fine", "im okay",
    "im ok", "not at all", "god no", "lol no", "no way", "nothing like that",
    "no im good", "definitely not", "absolutely not", "no not that",
)


#: Every table, by name. The golden digest and the per-row behavioural tests
#: both read this, so a table added later is pinned on the day it is written
#: rather than on the day somebody remembers the test file exists.
VOCABULARY: Final[dict[str, tuple[str, ...]]] = {
    "main_risk": MAIN_RISK_SOURCE,
    "other_risk": OTHER_RISK_SOURCE,
    "risk": RISK_SOURCE,
    "hedging": HEDGING_SOURCE,
    "short_only": SHORT_ONLY_SOURCE,
    "slang": SLANG_SOURCE,
    "preparatory": PREPARATORY_SOURCE,
    "farewell": FAREWELL_SOURCE,
    "fuzzy_keywords": FUZZY_KEYWORDS,
    "request": REQUEST_SOURCE,
    "outcome": OUTCOME_SOURCE,
    "contact": CONTACT_SOURCE,
    "crisis_target": CRISIS_TARGET_SOURCE,
    "care_target": CARE_TARGET_SOURCE,
    "other_markers": OTHER_MARKER_SOURCE,
    "self_markers": SELF_MARKER_SOURCE,
    "topic": TOPIC_SOURCE,
    "affirmative": AFFIRMATIVE_SOURCE,
    "negative": NEGATIVE_SOURCE,
}

#: The tables whose every entry must produce ``Action.ENTER`` on its own, and
#: the tables whose every entry must produce at least a question. Named so the
#: behavioural pin in ``tests/test_crisis.py`` covers each table by its
#: contract rather than by a list somebody keeps in a test file.
ENTERING_TABLES: Final[tuple[str, ...]] = ("main_risk",)
ASKING_TABLES: Final[tuple[str, ...]] = (
    "hedging", "slang", "preparatory", "farewell",
)
SURFACING_TABLES: Final[tuple[str, ...]] = ("other_risk",)

_MAIN_RISK = _compile(MAIN_RISK_SOURCE)
_OTHER_RISK = _compile(OTHER_RISK_SOURCE)
_RISK = _compile(RISK_SOURCE)
_HEDGING = _compile(HEDGING_SOURCE)
_SHORT_ONLY = _compile(SHORT_ONLY_SOURCE)
_SLANG = _compile(SLANG_SOURCE)
_PREPARATORY = _compile(PREPARATORY_SOURCE)
_FAREWELL = _compile(FAREWELL_SOURCE)
_REQUEST = _compile(REQUEST_SOURCE)
_OUTCOME = _compile(OUTCOME_SOURCE)
_CONTACT = _compile(CONTACT_SOURCE)
_CRISIS_TARGETS = _compile(CRISIS_TARGET_SOURCE)
_CARE_TARGETS = _compile(CARE_TARGET_SOURCE)
_AFFIRMATIVE = _compile(AFFIRMATIVE_SOURCE)
_NEGATIVE = _compile(NEGATIVE_SOURCE)

_OTHER_MARKERS = frozenset(OTHER_MARKER_SOURCE)
_SELF_MARKERS = frozenset(SELF_MARKER_SOURCE)
_TOPIC_MARKERS = frozenset(TOPIC_SOURCE)

_SAFE_WORD_TOKENS: Final[tuple[str, ...]] = _tokens(SAFE_WORD)
#: The safe word typed as one word, or with its letters spaced apart. Under
#: duress people do neither correctly, and a safe word with formatting rules is
#: not unconditional.
_SAFE_WORD_JOINED: Final[str] = "".join(_SAFE_WORD_TOKENS)


# -- matching -----------------------------------------------------------------


def _starts(tokens: tuple[str, ...], phrase: tuple[str, ...]) -> list[int]:
    """Every index at which ``phrase`` begins inside ``tokens``."""
    size = len(phrase)
    if not size or size > len(tokens):
        return []
    return [i for i in range(len(tokens) - size + 1) if tokens[i:i + size] == phrase]


def _hits(tokens: tuple[str, ...], table: tuple[tuple[str, ...], ...]) -> int:
    """How many phrases of ``table`` appear in ``tokens``."""
    return sum(1 for phrase in table if _starts(tokens, phrase))


def _any(tokens: tuple[str, ...], table: tuple[tuple[str, ...], ...]) -> bool:
    return _hits(tokens, table) > 0


def _within_one(word: str, want: str) -> bool:
    """Whether ``word`` is ``want`` with at most one character changed.

    A bounded, allocation-free check rather than a library call: one
    substitution, one insertion, one deletion, or one transposition of adjacent
    letters. Two of anything would turn ``suicide`` into a great many ordinary
    words.

    Transposition is included because it is the commonest typo there is —
    ``lantren`` for ``lantern`` — and plain edit distance calls it two changes.
    Excluding it meant the one signal that must never fail, failed on a shaking
    hand.
    """
    if word == want:
        return True
    if abs(len(word) - len(want)) > MAX_TYPO:
        return False
    if len(word) == len(want):
        if sum(a != b for a, b in zip(word, want)) <= MAX_TYPO:
            return True
        return any(
            word[:i] + word[i + 1] + word[i] + word[i + 2:] == want
            for i in range(len(word) - 1)
        )
    longer, shorter = (word, want) if len(word) > len(want) else (want, word)
    for cut in range(len(longer)):
        if longer[:cut] + longer[cut + 1:] == shorter:
            return True
    return False


def _depluralised(word: str) -> str:
    return word[:-1] if len(word) > 3 and word.endswith("s") else word


def _fuzzy_phrase(
    tokens: tuple[str, ...], phrase: tuple[str, ...], *, min_length: int
) -> bool:
    """Whether ``phrase`` appears in ``tokens`` allowing a plural or one typo
    per word. Used for the safe word, and for nothing that enters on its own."""
    size = len(phrase)
    if not size or size > len(tokens):
        return False
    for start in range(len(tokens) - size + 1):
        window = tokens[start:start + size]
        if all(
            token == want
            or _depluralised(token) == want
            or (len(want) >= min_length and _within_one(token, want))
            for token, want in zip(window, phrase)
        ):
            return True
    return False


def _squashed(tokens: tuple[str, ...]) -> str:
    """The message with every space removed.

    ``s u i c i d a l`` and ``suicidal`` become one string, so letter-spacing —
    which is deliberate filter evasion and therefore *more* worth reading, not
    less — stops being invisible. Concatenation is contiguous, so words that
    are far apart cannot fuse into a phrase that was never written.
    """
    return "".join(tokens)


def _fuzzy_keyword_hits(tokens: tuple[str, ...]) -> int:
    """Keywords found through a typo, or through spaced-out letters."""
    squashed = _squashed(tokens)
    found = 0
    for keyword in FUZZY_KEYWORDS:
        if keyword in squashed:
            found += 1
            continue
        if any(
            len(token) >= MIN_FUZZY_LENGTH and _within_one(token, keyword)
            for token in tokens
        ):
            found += 1
    return found


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
    something I think about"* surfaces a resource rather than asking. It is the
    reason the third-party reply ends by inviting the main to say if it is
    closer to them than they have said, and it is on the clinical-review list
    rather than settled by intuition here.
    """
    before = tokens[max(0, start - ATTRIBUTION_WINDOW):start]
    if not any(word in _OTHER_MARKERS for word in before):
        return False
    return not any(word in _SELF_MARKERS for word in before)


def _about_the_main(tokens: tuple[str, ...], start: int) -> bool:
    """Whether the phrase at ``start`` is the main speaking about themselves.

    A first-person marker in the window, and no word saying the phrase is a
    *topic*. The second half is what keeps "I read about suicide today" out of
    the mode: a pronoun beside the word is not a disclosure, and without the
    topic check that sentence entered and capped for thirty days.

    This is the rule that carries the matrix's *"my friend and i are both
    suicidal"* row, where no explicit first-person phrase appears at all and
    the sentence must still never be downgraded to somebody else's.
    """
    before = tokens[max(0, start - ATTRIBUTION_WINDOW):start]
    if any(word in _TOPIC_MARKERS for word in before):
        return False
    return any(word in _SELF_MARKERS for word in before)


def has_safe_word(text: object) -> bool:
    """Whether the documented phrase appears anywhere in ``text``.

    Anywhere: mid-sentence, mid-paragraph, in any case, with any punctuation
    around it, pluralised, mistyped by one character, and run together as one
    word. Never scored, never thresholded, never outvoted.
    """
    tokens = _tokens(text)
    if _fuzzy_phrase(tokens, _SAFE_WORD_TOKENS, min_length=SAFE_WORD_MIN_FUZZY):
        return True
    return _SAFE_WORD_JOINED in _squashed(tokens)


def is_affirmative(text: object) -> bool:
    """Whether ``text`` answers Half's own question with a yes.

    Read only when a question is pending, and generous about what counts:
    *maybe*, *sometimes* and *kind of* are answers of yes to *"are you thinking
    about suicide?"*, and treating them as anything else is the hedge that
    makes the question pointless. A negative answer is checked first, because
    "no, not really" contains neither more nor less than "not really".
    """
    tokens = _tokens(text)
    if _any(tokens, _NEGATIVE):
        return False
    return _any(tokens, _AFFIRMATIVE)


def is_negative(text: object) -> bool:
    """Whether ``text`` answers Half's own question with a no."""
    return _any(_tokens(text), _NEGATIVE)


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

    1. the main's own explicit words about themselves — enter;
    2. an unattributed risk phrase the main has claimed by standing next to it,
       with nothing saying it is a topic — enter;
    3. risk that belongs to somebody else — a resource, and it stops;
    4. reaching a crisis line, or reaching care while in distress — enter,
       gently;
    5. everything else that might be distress — ask.
    """
    explicit = _hits(tokens, _MAIN_RISK)
    if explicit:
        return Assessment(Tier.DISCLOSURE, Action.ENTER, score=explicit)

    # Where the message is explicitly about somebody else. An unattributed hit
    # *inside* one of these spans is part of that phrase and not a second,
    # unattributed signal — without this, "she is suicidal" matched both
    # ``_OTHER_RISK`` and the bare word ``suicidal``, and the bare word won.
    elsewhere: list[range] = [
        range(start, start + len(phrase))
        for phrase in _OTHER_RISK
        for start in _starts(tokens, phrase)
    ]
    mine = other = loose = 0
    for phrase in _RISK:
        for start in _starts(tokens, phrase):
            if any(start in span for span in elsewhere):
                continue
            if _about_the_main(tokens, start):
                mine += 1
            elif _about_another(tokens, start):
                other += 1
            else:
                loose += 1
    if mine:
        return Assessment(Tier.DISCLOSURE, Action.ENTER, score=mine)
    if other or elsewhere:
        return Assessment(
            Tier.THIRD_PARTY_AT_RISK, Action.SURFACE,
            score=other + len(elsewhere),
        )

    reaching = _any(tokens, _CONTACT)
    if reaching and _any(tokens, _CRISIS_TARGETS):
        return Assessment(Tier.SEEKING_HELP, Action.ENTER, score=1)

    asked = (
        loose
        + _hits(tokens, _HEDGING)
        + _hits(tokens, _SLANG)
        + _hits(tokens, _PREPARATORY)
        + _hits(tokens, _FAREWELL)
        + _fuzzy_keyword_hits(tokens)
    )
    if len(tokens) <= SHORT_MESSAGE_WORDS:
        asked += _hits(tokens, _SHORT_ONLY)
    if _any(tokens, _REQUEST) and _any(tokens, _OUTCOME):
        asked += 1

    if asked and reaching and _any(tokens, _CARE_TARGETS):
        # Reaching for care *while in distress* is the companion's "enter
        # gently" row. Reaching for care on an ordinary Tuesday is not, and
        # treating it as one would cap a main for booking a therapy session.
        return Assessment(Tier.SEEKING_HELP, Action.ENTER, score=asked)
    if asked:
        return Assessment(Tier.INFERENCE, Action.ASK, score=asked)
    return Assessment(Tier.NONE, Action.NONE)


def _check_table() -> None:
    """Import-time invariants, as raises rather than bare ``assert``.

    A guarantee that ``python -O`` removes is not a guarantee. Sixteen bare
    asserts across this subsystem carried the machine statement, the do-list
    and the shape of this table, and all sixteen were stripped by an
    optimisation flag while every module still imported cleanly.
    """
    if set(ACTION_FOR) != set(Tier):
        raise CrisisError(
            f"every tier needs an action: {set(ACTION_FOR) ^ set(Tier)}"
        )
    if not ENTERING or not ASKING:
        raise CrisisError("the table must have both an entering and an asking tier")
    if ENTERING & ASKING:
        raise CrisisError("a tier cannot both enter and merely ask")
    if not _SAFE_WORD_TOKENS:
        raise CrisisError("the safe word must survive tokenization")
    for name, table in VOCABULARY.items():
        if not table:
            raise CrisisError(f"the {name} table is empty; a signal was removed")
        if len(set(table)) != len(table):
            raise CrisisError(f"the {name} table repeats a phrase")
        if any(not _tokens(phrase) for phrase in table):
            raise CrisisError(f"the {name} table has a phrase that tokenizes to nothing")
    for group in (ENTERING_TABLES, ASKING_TABLES, SURFACING_TABLES):
        for name in group:
            if name not in VOCABULARY:
                raise CrisisError(f"{name} is pinned by contract but is not a table")


_check_table()
