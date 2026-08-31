"""One tokenizer, shared by everything that splits a main's words.

Three modules used to split text and all three disagreed: the store's FTS query
builder was unicode-aware, while the prefix builder and the strand matcher were
``[A-Za-z0-9]`` only. Half ships wherever a messaging app does, so the
consequences were not cosmetic:

* ``build_prefix({"subject": "आशा"})`` produced ``""``, so a Devanagari subject
  was dropped from the index entirely and could never be retrieved.
* A person or loop named in any non-Latin script could never become a live
  strand, because the matcher found no tokens in the message either.
* ``café-plans`` was indexed as ``caf plans``, while FTS5's unicode61 tokenizer
  folds a query for ``café`` to ``cafe`` — so the belief was permanently
  unfindable by the word it was named after.

So: one split, unicode-aware, used everywhere.

**A word is a word in every script.** ``words`` keeps a combining mark attached
to the letter it modifies. Python's ``\\w`` does not — a Devanagari matra is
neither a letter nor a digit to ``str.isalnum``, so the earlier
``re.compile(r"[^\\W_]+")`` shattered ``यात्रा`` into ``य``, ``त``, ``र``: three
bare consonants that collide with almost any other Devanagari string. The store
OR-joined those pieces, and a query for ``रात`` ("night") retrieved a belief
about travel. Keeping marks with their letter is what makes a word a word for
every combining-mark script at once, with no language list anywhere.

**Whole words go to FTS5 as phrases.** ``words`` is deliberately *not* the split
SQLite's ``unicode61`` performs: unicode61 treats a matra as a separator, and
that is fine, because the store hands it each whole word inside quotes. FTS5
then splits the phrase with the very tokenizer it used on the indexed text, so
the two shatter alike and match. OR stays *between* words — a conversational
turn must still match a belief that shares one word.

**Scriptio continua is n-grammed, on both sides.** Japanese, Chinese, Thai, Lao,
Khmer and Korean do not put spaces where words end, so an entire sentence
arrives as one word and unicode61 indexes it as one token: ``転職`` retrieved
nothing at all from ``転職を考えている``. ``terms`` therefore expands a run of
such characters into its 1-, 2- and 3-character n-grams. Indexing and querying
call the same function, which is the whole point — an index n-grammed on one
side only is worse than the defect it replaces. (Switching FTS5 itself to the
``trigram`` tokenizer is the obvious alternative and it fails the ordinary case:
``trigram`` returns nothing for a two-character query, and two-character words
are the normal shape of a Chinese or Japanese word.)

**N-gramming is bounded, and the bound is an error rather than a truncation.**
A run of *n* characters emits up to *3n - 3* terms, so both the input length
(``MAX_INPUT_CHARS``) and the emitted term count (``MAX_TERMS``) are capped and
exceeding either raises ``TokenGrowthLimitError``. Silently dropping the tail
would leave a belief indexed by its first half and unreachable by its second,
with nothing anywhere saying so.

``words`` is what a caller splits into words. ``terms`` is what goes *into* the
FTS index and what comes *out* of a query, and ``index_text`` is that list as
the one string the index stores. ``tokens`` additionally folds case and strips
combining marks, mirroring unicode61's ``remove_diacritics``, and is what Half
uses when it compares two pieces of its own text — both sides folded the same
way, or ``Café`` and ``cafe`` are two different strands.

Pure and stdlib-only. Nothing here reads a clock, the environment or the log.
"""

from __future__ import annotations

import unicodedata
from typing import Final

from half.errors import TokenGrowthLimitError

#: Character blocks written without spaces between words, so that a whole
#: sentence arrives as a single word. Script classes, never languages: Half
#: does not detect a language and must not need a language list to work.
#:
#: Hangul is here although modern Korean *is* spaced, because Korean glues its
#: particles onto the noun — ``이직을`` is one token and a query for ``이직``
#: would miss it. That is the same failure for the same reason, so it gets the
#: same treatment.
UNSPACED_RANGES: Final[tuple[tuple[int, int], ...]] = (
    (0x0E00, 0x0E7F),    # Thai
    (0x0E80, 0x0EFF),    # Lao
    (0x1000, 0x109F),    # Myanmar
    (0x1780, 0x17FF),    # Khmer
    (0x1100, 0x11FF),    # Hangul Jamo
    (0x3040, 0x309F),    # Hiragana
    (0x30A0, 0x30FF),    # Katakana
    (0x3100, 0x312F),    # Bopomofo
    (0x3130, 0x318F),    # Hangul Compatibility Jamo
    (0x31A0, 0x31BF),    # Bopomofo Extended
    (0x31F0, 0x31FF),    # Katakana Phonetic Extensions
    (0x3400, 0x4DBF),    # CJK Unified Ideographs Extension A
    (0x4E00, 0x9FFF),    # CJK Unified Ideographs
    (0xA960, 0xA97F),    # Hangul Jamo Extended-A
    (0xAC00, 0xD7AF),    # Hangul Syllables
    (0xD7B0, 0xD7FF),    # Hangul Jamo Extended-B
    (0xF900, 0xFAFF),    # CJK Compatibility Ideographs
    (0xFF66, 0xFF9F),    # Halfwidth Katakana
    (0x20000, 0x2FA1F),  # Supplementary CJK ideographs and compatibility forms
    (0x30000, 0x323AF),  # CJK Unified Ideographs Extensions G through H
)

#: Unigrams make a one-character query reachable, bigrams carry the ordinary
#: two-character word, trigrams add specificity. Fixed at three sizes so growth
#: is bounded at ``3n - 3`` terms for a run of ``n`` characters.
NGRAM_SIZES: Final[tuple[int, ...]] = (1, 2, 3)

#: Longest text this tokenizer will look at. A claim is a sentence and a turn is
#: a message; anything past this is not either of those.
MAX_INPUT_CHARS: Final[int] = 8_000

#: Ceiling on terms emitted for one text. Bounds the n-gram expansion before an
#: oversized term list is materialized, rather than after.
MAX_TERMS: Final[int] = 20_000


def words(text: object) -> list[str]:
    """Word tokens of ``text``, in order, case and accents preserved.

    A word is a run of letters and digits together with the marks that belong
    to them — matras, viramas, nuktas, combining accents — so a word stays one
    word in every script rather than shattering into consonants. Underscore is
    a separator, as it was before.

    Preserved on purpose: these are handed to FTS5 as phrases, and FTS5 does
    its own folding. Folding twice is how ``café`` became ``caf``. Anything
    that is not a string yields no words rather than raising — the log
    preserves fields this build does not recognise, and one odd value must not
    take an index rebuild down.
    """
    if not isinstance(text, str):
        return []
    found: list[str] = []
    current: list[str] = []
    for char in text:
        if char.isalnum() or unicodedata.category(char).startswith("M"):
            current.append(char)
        elif current:
            found.append("".join(current))
            current = []
    if current:
        found.append("".join(current))
    return found


def terms(text: object) -> list[str]:
    """The index terms of ``text``: its words, with unspaced runs n-grammed.

    The same function on both sides of the index. A word written in a spaced
    script passes through whole; a run of scriptio-continua characters becomes
    its bounded n-grams, so a two-character word is findable inside a sentence
    that never spaced it.

    A term carrying no letter or digit at all is dropped: a lone combining mark
    is a separator to FTS5 and contributes nothing to either side, so keeping it
    would only spend the term budget.

    Raises ``TokenGrowthLimitError`` when the input or the emitted term count
    exceeds its ceiling. Never truncates — a half-indexed belief is unreachable
    by its own words with nothing recording that it happened.
    """
    if not isinstance(text, str):
        return []
    if len(text) > MAX_INPUT_CHARS:
        raise TokenGrowthLimitError(
            f"text of {len(text)} characters exceeds the "
            f"{MAX_INPUT_CHARS}-character tokenizer limit"
        )
    emitted: list[str] = []
    for word in words(text):
        for run, unspaced in _script_runs(word):
            if unspaced:
                _require_capacity(len(emitted), _ngram_count(len(run)))
                emitted.extend(_ngrams(run))
            else:
                _require_capacity(len(emitted), 1)
                emitted.append(run)
    return [term for term in emitted if any(ch.isalnum() for ch in term)]


def index_text(text: object) -> str:
    """``terms`` as the single string the FTS index stores.

    Space-separated, which is a boundary in every script FTS5's ``unicode61``
    recognises, so each term is its own token however it was written.
    """
    return " ".join(terms(text))


def normalize(word: str) -> str:
    """Casefold ``word`` and strip combining marks.

    ``unicode61``'s ``remove_diacritics`` behaviour, reproduced so that Half's
    own comparisons agree with the index's.
    """
    decomposed = unicodedata.normalize("NFKD", word.casefold())
    return "".join(ch for ch in decomposed if not unicodedata.combining(ch))


def tokens(text: object) -> frozenset[str]:
    """Normalized index terms of ``text``, for comparing Half's text to itself.

    Built on ``terms`` rather than ``words`` so that a strand named in an
    unspaced script is found inside a sentence that never spaced it — a person
    called ``転職`` is otherwise never live in ``転職を考えている``.
    """
    return frozenset(normalize(term) for term in terms(text) if term)


def _is_unspaced(char: str) -> bool:
    """Whether ``char`` belongs to a script written without word spaces."""
    codepoint = ord(char)
    return any(start <= codepoint <= end for start, end in UNSPACED_RANGES)


def _script_runs(word: str) -> list[tuple[str, bool]]:
    """``word`` split wherever it enters or leaves a scriptio-continua script.

    ``転職plan`` is two runs, so the CJK half is n-grammed and the Latin half is
    left alone. One claim may mix scripts and both halves must stay findable.
    """
    if not word:
        return []
    runs: list[tuple[str, bool]] = []
    start = 0
    unspaced = _is_unspaced(word[0])
    for position, char in enumerate(word[1:], start=1):
        current = _is_unspaced(char)
        if current != unspaced:
            runs.append((word[start:position], unspaced))
            start = position
            unspaced = current
    runs.append((word[start:], unspaced))
    return runs


def _ngrams(run: str) -> list[str]:
    """Bounded character n-grams of one uninterrupted unspaced run."""
    return [
        run[offset:offset + size]
        for size in NGRAM_SIZES
        if len(run) >= size
        for offset in range(len(run) - size + 1)
    ]


def _ngram_count(length: int) -> int:
    """The exact n-gram count for a run, without materializing the terms."""
    return sum(length - size + 1 for size in NGRAM_SIZES if length >= size)


def _require_capacity(emitted: int, adding: int) -> None:
    if emitted + adding > MAX_TERMS:
        raise TokenGrowthLimitError(
            f"tokenization would emit more than the {MAX_TERMS}-term limit"
        )
