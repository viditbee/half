"""The offline table: what an explicit correction is, and what it means (CAP-11).

**This table is not the recall instrument, and that is the whole design.** The
argument is already written in ``half.crisis.classifier`` for distress and it
transfers here unchanged: a phrase table fires only on what somebody thought to
write down, and the ways a person says *"that's wrong"* are not enumerable. So
this is the fast, offline, high-confidence path — an explicit correction the
table recognises is acted on directly — and ``half.correction.candidate``
widens past it with a model whose answer is a candidate rather than an append.

**Tight on purpose**, on the same terms as ``MAIN_RISK_SOURCE``. Everything the
table matches is *acted on* with no confirmation, so a row that fires on an
ordinary sentence removes a belief the main never questioned. Loose phrasings —
*"I used to"*, *"that's not quite it"*, a shrug — belong to the classifier,
where they cost a question rather than a claim.

**No language is the default.** Every table below carries rows in many scripts,
and the English rows are not a base the rest extend: they are one language among
several, added first because they were the ones already in the tree. The rule is
the story's own — Half ships worldwide, and a table with one language in it is a
product that recognises corrections from one population.

The Latin-script rows are the ones chosen carefully, for the reason
``half.crisis.signals.AFFIRMATIVE_SOURCE`` gives: a non-Latin phrase cannot
collide with an English sentence, so those are added freely, while a Latin one
can. Nothing here is a single word — every row is a phrase of two tokens or
more, or a non-Latin run that cannot be an English word — because a one-word
table over ``no`` or ``wrong`` fires on half the conversations there are.

**This is a first widening and not a finished one.** Coverage was chosen by
speaker count rather than by a native speaker of each language, and extending it
is ordinary work rather than a redesign — the classifier is what stops a missing
row from being a missing capability.

**Its own tokenizer, and why there are two.** ``half.crisis.signals`` splits on
``half.text.words``, which keeps a scriptio-continua run whole — so a Chinese or
Japanese phrase matches only a message that is exactly that run. This module
splits on ``half.text.terms``, which cuts such a run into grapheme clusters, so
a phrase matches wherever those clusters are adjacent inside a longer sentence.
The two modules cannot share one function because ``half.crisis`` is depended
upon by no domain module (the spine's layer table), and this is a domain module.
``tests/test_correction.py`` pins the agreement that matters — that both cut
spaced scripts identically — so the duplication is a checked property rather
than a place to drift.

Pure and stdlib-only. No clock, no network, no model, no ambient state, and no
store: recognising a message writes nothing anywhere.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Final

from half.errors import TokenGrowthLimitError
from half.text import normalize, terms, words


class Meaning(StrEnum):
    """What an explicit correction says. Four values, and three of them remove.

    The names are the *utterance's* meaning, not the op: which op a meaning
    becomes is ``half.correction.apply``'s question, and which attribution it
    carries is ``half.correction.attribute``'s. Keeping them apart is what lets
    the third attribution state exist at all — ``WRONG`` removes the belief and
    says nothing about the cause, which no op on its own can express.
    """

    #: The main says the belief was never true. Half was wrong.
    NEVER_TRUE = "never_true"
    #: The main says it was true and is not any more. The world changed.
    CHANGED = "changed"
    #: The main says it is wrong and does not say which. Removed; cause unknown.
    WRONG = "wrong"
    #: The main asks for it to be gone entirely.
    ERASE = "erase"


#: Apostrophes, removed before splitting so that ``don't`` and ``dont`` are one
#: token and every phrase below can be written once. Same set, same reason, as
#: ``half.crisis.signals``.
_APOSTROPHES: Final[dict[int, None]] = {ord(char): None for char in "'’‘ʼ´`"}

#: Line breaks and tabs, turned into spaces before splitting. ``half.text``
#: *removes* invisible characters rather than treating them as boundaries —
#: correct for the index, wrong here, where a correction typed across two lines
#: would otherwise match nothing.
_BREAKS: Final[dict[int, str]] = {
    ord(char): " " for char in "\n\r\t\v\f  "
}


def _tokens(text: object) -> tuple[str, ...]:
    """``text`` as folded comparison tokens, in order.

    ``terms`` rather than ``words``: a run of Chinese, Japanese, Thai, Lao,
    Khmer or Korean is cut into grapheme clusters, so a phrase written in one of
    those scripts matches inside a sentence rather than only as the whole of
    one. That is the difference between a table that covers those languages and
    a table that lists them.

    Never raises. ``terms`` enforces the index's growth ceilings, and a message
    long enough to trip one must still be *recognised* — the ceilings exist to
    bound an index, not to decide that a very long message cannot be a
    correction. Past them this falls back to whole words, which is the crisis
    table's behaviour and is worse only for unspaced scripts.
    """
    if not isinstance(text, str):
        return ()
    stripped = text.translate(_BREAKS).translate(_APOSTROPHES)
    try:
        split = terms(stripped)
    except TokenGrowthLimitError:
        split = words(stripped)
    return tuple(folded for token in split if (folded := normalize(token)))


def _compile(source: tuple[str, ...]) -> tuple[tuple[str, ...], ...]:
    """Phrase sources compiled to token tuples, through the same tokenizer."""
    return tuple(_tokens(phrase) for phrase in source)


# =============================================================================
# The vocabulary
# =============================================================================
#
# Every table is exported through ``VOCABULARY`` and pinned in
# ``tests/test_correction.py``: every entry must still produce its own meaning,
# and no entry of any table may fire on an ordinary message. Deleting a row
# fails mechanically rather than silently narrowing the reach.


#: *Half was wrong.* The belief was never true — an apology is owed, and the
#: record says the system had it wrong (``expired_at``).
#:
#: Distinguished from ``WRONG_SOURCE`` by tense and by subject: these rows say
#: something about the belief's *whole history* (never, always, at no point) or
#: about Half (*you were wrong*, *you misunderstood*), where the plain-wrong
#: table says only that it is wrong now.
NEVER_TRUE_SOURCE: Final[tuple[str, ...]] = (
    # English
    "that was never true", "that was never right", "that was never correct",
    "it was never true", "this was never true", "never been true",
    "i never said that", "i never said this", "i never told you that",
    "you were wrong", "you were wrong about that", "you got that wrong",
    "you misunderstood that", "you misunderstood me", "that was always wrong",
    "where did you get that", "i never did that",
    # Romance
    "eso nunca fue cierto", "eso nunca fue verdad", "nunca dije eso",
    "te equivocaste", "isso nunca foi verdade", "eu nunca disse isso",
    "ça n'a jamais été vrai", "je n'ai jamais dit ça", "tu t'es trompé",
    # Germanic and Nordic
    "das war nie wahr", "das habe ich nie gesagt", "du hast dich geirrt",
    "det var aldrig sant", "dat was nooit waar",
    # Slavic and Baltic
    "это никогда не было правдой", "я такого не говорил",
    "я этого не говорила", "to nigdy nie było prawdą",
    # Turkish, Greek, Hebrew
    "hiç öyle demedim", "bu hiç doğru değildi",
    "αυτό δεν ήταν ποτέ αλήθεια", "מעולם לא אמרתי את זה",
    # Arabic and Persian
    "لم أقل ذلك أبدا", "هذا لم يكن صحيحا أبدا", "من هرگز این را نگفتم",
    # South Asia
    "मैंने ऐसा कभी नहीं कहा", "यह कभी सच नहीं था", "ये कभी सच नहीं था",
    "আমি কখনো এটা বলিনি", "நான் அப்படி சொல்லவே இல்லை",
    # East and South-East Asia
    "我从来没说过", "我從來沒說過", "这从来都不对",
    "そんなことは言っていない", "それは最初から違う",
    "그런 말 한 적 없어", "그건 처음부터 틀렸어",
    "saya tidak pernah bilang begitu", "tôi chưa bao giờ nói vậy",
    # Africa
    "sijawahi kusema hivyo",
)

#: *The main changed.* It was true and is not any more — no apology, and the
#: record says the claim stopped being true (``invalid_at``).
CHANGED_SOURCE: Final[tuple[str, ...]] = (
    # English
    "not any more", "not anymore", "no longer true", "not true any more",
    "that has changed", "thats changed", "that changed", "this has changed",
    "it used to be true", "that used to be true", "that was true before",
    "that was true then", "it isnt any more", "not the case any more",
    # Romance
    "eso ya no es cierto", "ya no es verdad", "eso cambio",
    "isso mudou", "isso já não é verdade",
    "ce n'est plus vrai", "ça a changé", "plus maintenant",
    # Germanic and Nordic
    "nicht mehr wahr", "das hat sich geändert", "stimmt nicht mehr",
    "det stämmer inte längre", "dat klopt niet meer",
    # Slavic and Baltic
    "это изменилось", "больше не так", "уже не так",
    "to się zmieniło", "już nie",
    # Turkish, Greek, Hebrew
    "artık değil", "bu değişti", "δεν ισχύει πια", "זה השתנה",
    # Arabic and Persian
    "لم يعد كذلك", "هذا تغير", "دیگر اینطور نیست",
    # South Asia
    "अब ऐसा नहीं है", "अब यह बदल गया", "ये अब सच नहीं है",
    "এটা এখন আর সত্যি নয়", "இது இப்போது இல்லை",
    # East and South-East Asia
    "已经不是了", "現在不是了", "这已经变了",
    "もう違います", "それはもう違う", "이제 아니야", "그건 이제 달라",
    "sudah tidak lagi", "không còn đúng nữa",
    # Africa
    "sio tena hivyo",
)

#: *Wrong, and the utterance does not say which.* The belief leaves the fold on
#: this signal alone; the cause is recorded as **not yet known** and a later
#: message can settle it.
WRONG_SOURCE: Final[tuple[str, ...]] = (
    # English
    "thats wrong", "that is wrong", "thats not right", "that is not right",
    "thats incorrect", "that is incorrect", "thats not true",
    "that is not true", "thats not correct", "that is not correct",
    "thats false", "that is false", "youre wrong", "you are wrong",
    "you have that wrong", "thats not accurate", "no thats wrong",
    "nope thats wrong", "thats not it", "wrong about that",
    # Romance
    "eso está mal", "eso no es cierto", "eso no es verdad", "no es así",
    "isso está errado", "isso não é verdade",
    "c'est faux", "ce n'est pas vrai", "ce n'est pas exact",
    # Germanic and Nordic
    "das stimmt nicht", "das ist falsch", "det stämmer inte", "det er feil",
    "dat klopt niet",
    # Slavic and Baltic
    "это неправда", "это неверно", "это не так", "to nieprawda",
    # Turkish, Greek, Hebrew
    "bu yanlış", "bu doğru değil", "αυτό είναι λάθος", "δεν είναι σωστό",
    "זה לא נכון",
    # Arabic and Persian
    "هذا خطأ", "هذا غير صحيح", "این درست نیست",
    # South Asia
    "यह गलत है", "ये गलत है", "यह सही नहीं है", "ਇਹ ਗਲਤ ਹੈ",
    "এটা ভুল", "இது தவறு", "ఇది తప్పు", "ಇದು ತಪ್ಪು", "ഇത് തെറ്റാണ്",
    # East and South-East Asia
    "这不对", "這不對", "这是错的", "不是这样",
    "それは違う", "それは間違いです", "違います",
    "그건 틀렸어", "그건 아니야", "틀렸어요",
    "itu salah", "không đúng", "ไม่ถูก", "ไม่ใช่แบบนั้น",
    # Africa and the Philippines
    "hiyo si kweli", "hindi tama iyon",
)

#: *Erase it.* Not a correction — an erasure, tombstoned, and distinct from
#: removal in what Half says (glossary; story 1's validate-then-erase).
#:
#: Deliberately the narrowest table of the four. An erasure cannot be taken
#: back, so its rows have to be unmistakable asks rather than emphatic
#: disagreement: *"that's completely wrong"* is not a request to erase.
ERASE_SOURCE: Final[tuple[str, ...]] = (
    # English
    "delete that", "delete this", "delete it", "erase that", "erase this",
    "erase it", "wipe that", "forget that completely", "forget that entirely",
    "remove that permanently", "get rid of that completely",
    # Romance
    "borra eso", "elimina eso", "apague isso", "supprime ca", "efface ca",
    # Germanic and Nordic
    "lösch das", "vergiss das ganz", "verwijder dat", "slett det",
    # Slavic and Baltic
    "удали это", "сотри это", "usuń to",
    # Turkish, Greek, Hebrew
    "bunu sil", "διάγραψε το", "תמחק את זה",
    # Arabic and Persian
    "احذف هذا", "این را حذف کن",
    # South Asia
    "इसे मिटा दो", "इसे हटा दो", "এটা মুছে দাও", "இதை நீக்கு",
    # East and South-East Asia
    "删掉这个", "刪掉這個", "把这个删掉",
    "それを削除して", "これを消して", "그거 삭제해", "그거 지워",
    "hapus itu", "xóa cái đó", "ลบอันนั้น",
    # Africa
    "futa hiyo",
)

#: The answer that lets a **candidate** act (CAP-10). Narrow on purpose, on the
#: same terms as ``half.crisis.signals.CONSENT_SOURCE`` and for the same reason:
#: the cost of reading a real yes as a hedge is one more turn, and the cost of
#: the reverse is a belief deleted on a *maybe*.
#:
#: There is deliberately **no negative table**. Anything that is not a clear
#: confirmation is a decline — silence is not consent, and neither is *maybe* —
#: so a table of ways to say no is a list nobody has to keep complete.
CONFIRM_SOURCE: Final[tuple[str, ...]] = (
    # English
    "yes", "yeah", "yep", "yup", "correct", "thats right", "that is right",
    "yes please", "yes remove it", "yes delete it", "please do", "go ahead",
    "do it", "sure", "remove it", "take it out", "exactly",
    # Romance
    "si", "claro", "por supuesto", "sim", "certo", "oui", "exactement",
    # Germanic and Nordic
    "ja", "genau", "ja bitte", "jo",
    # Slavic and Baltic
    "да", "верно", "tak",
    # Turkish, Greek, Hebrew
    "evet", "doğru", "ναι", "כן",
    # Arabic and Persian
    "نعم", "ايوه", "صحيح", "بله", "اره",
    # South Asia
    "हाँ", "हां", "जी हाँ", "haan", "सही है",
    "ਹਾਂ", "હા", "হ্যাঁ", "অবশ্যই", "అవును", "ஆம்", "ஆமா", "ಹೌದು", "होय", "അതെ",
    # East and South-East Asia
    "はい", "うん", "そうです", "네", "예", "응", "맞아",
    "是", "是的", "对", "没错",
    "iya", "benar", "vâng", "đúng rồi", "ใช่", "ครับ",
    # Africa and the Philippines
    "ndiyo", "ndio", "oo", "opo",
)


#: Every table, by name. The behavioural pin in ``tests/test_correction.py``
#: sweeps this rather than a list somebody keeps in a test file, so a new table
#: is covered by existing cases the moment it is added.
VOCABULARY: Final[dict[str, tuple[str, ...]]] = {
    "never_true": NEVER_TRUE_SOURCE,
    "changed": CHANGED_SOURCE,
    "wrong": WRONG_SOURCE,
    "erase": ERASE_SOURCE,
    "confirm": CONFIRM_SOURCE,
}

#: Which meaning each removing table produces, and **the order they are tried
#: in**. Order is a rule rather than an arrangement: a message is routinely more
#: than one of these at once — *"that was never true, delete it"* is both an
#: erasure and an attribution — and the most specific ask wins.
#:
#: Erase first, because it is the one action that cannot be taken back and the
#: one the main asked for by name. Then the two attributed meanings, because a
#: message that says *why* must never be flattened into one that does not. Plain
#: wrong last, because it is what is left when nothing more specific was said —
#: which is exactly what *not yet known* means.
MEANING_FOR_TABLE: Final[tuple[tuple[str, Meaning], ...]] = (
    ("erase", Meaning.ERASE),
    ("never_true", Meaning.NEVER_TRUE),
    ("changed", Meaning.CHANGED),
    ("wrong", Meaning.WRONG),
)

_TABLES: Final[dict[str, tuple[tuple[str, ...], ...]]] = {
    name: _compile(source) for name, source in VOCABULARY.items()
}


def _starts(tokens: tuple[str, ...], phrase: tuple[str, ...]) -> bool:
    """Whether ``phrase`` appears contiguously inside ``tokens``."""
    size = len(phrase)
    if not size or size > len(tokens):
        return False
    return any(tokens[i:i + size] == phrase for i in range(len(tokens) - size + 1))


def _any(tokens: tuple[str, ...], table: tuple[tuple[str, ...], ...]) -> bool:
    return any(_starts(tokens, phrase) for phrase in table)


def recognize(text: object) -> Meaning | None:
    """What this message explicitly corrects, or ``None``. Pure, offline.

    ``None`` is the ordinary answer and is not *"no correction"* — it is *"no
    correction this table can see"*, which is the whole reason
    ``half.correction.candidate`` exists. Nothing downstream may read a ``None``
    here as evidence that the main did not correct anything.
    """
    found = _tokens(text)
    if not found:
        return None
    for name, meaning in MEANING_FOR_TABLE:
        if _any(found, _TABLES[name]):
            return meaning
    return None


def is_confirmation(text: object) -> bool:
    """Whether this message is a clear *yes* to a standing candidate.

    Whole-message, not contained: the answer to *"shall I remove this?"* is a
    short one, and a ``yes`` buried inside a paragraph about something else is
    not an answer to Half's question. A candidate is a proposal to delete
    something, so the reading has to be the narrow one — everything that is not
    this is a decline, and a decline removes nothing.
    """
    found = _tokens(text)
    if not found:
        return False
    return any(found == phrase for phrase in _TABLES["confirm"])
