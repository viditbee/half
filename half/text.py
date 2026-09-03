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

**One mechanism, not two: every word is matched as a phrase.** ``words`` cuts
text into words; ``phrases`` turns each word into the token sequence FTS5 should
match it by; the store quotes each of those and ORs them *between* words. A
phrase matches only where its tokens are adjacent, and adjacency is what carries
word identity in a script that has no spaces to carry it.

**A word is a word in every script.** ``words`` keeps a combining mark attached
to the letter it modifies. Python's ``\\w`` does not — a Devanagari matra is
neither a letter nor a digit to ``str.isalnum``, so the earlier
``re.compile(r"[^\\W_]+")`` shattered ``यात्रा`` into ``य``, ``त``, ``र``: three
bare consonants that collide with almost any other Devanagari string, and a
query for ``रात`` ("night") retrieved a belief about travel. That whole word then
goes to FTS5 inside quotes, and FTS5 re-splits it with the very tokenizer it used
on the indexed text — so however ``unicode61`` shatters a word, both sides
shatter it alike and the phrase matches only the word it came from.

**Scriptio continua is cut into grapheme clusters, on both sides.** Japanese,
Chinese, Thai, Lao, Khmer and Korean do not put spaces where words end, so an
entire sentence arrives as one word and ``unicode61`` indexes it as a single
token: ``転職`` retrieved nothing at all from ``転職を考えている``. Such a run is
therefore cut into clusters, indexed as a token each, and queried as the phrase
of the same clusters. ``転職`` is then the two-token phrase 転-then-職, which
matches ``転職を考えている`` and does *not* match ``退職金の話をした``.

  An earlier version of this module emitted 1-, 2- and 3-character n-grams and
  OR'd them, copying ``claude-obsidian``'s BM25 tokenizer. That is wrong here
  and it was verified wrong: OR-ing unigrams means one shared character
  retrieves anything, so ``転職`` returned the belief about severance pay and
  ``เปลี่ยนงาน`` returned one about sticky rice. It was the ``रात``-matches-travel
  defect reborn one script over. The n-grams survive only in ``tokens``, which
  compares *sets* and has no adjacency to work with.

  Slicing at raw codepoint offsets was wrong for the same shape of reason: it
  undid the mark-preserving fix one layer below it. ``terms("ភាសាខ្មែរ")`` began
  ``['ភ','ស','ខ','ម','រ','ភា','ាស',...]`` — dependent vowels stripped off and
  bigrams beginning on a bare mark. A cluster is a base plus the marks that
  belong to it, and a virama or coeng pulls in the letter it subjoins, so
  ``ភាសាខ្មែរ`` cuts into ``ភា សា ខ្មែ រ``.

**Script class comes from the Unicode character database.** ``unicodedata.name``
carries the script in the character's own name, so every CJK extension block,
Kana Supplement and halfwidth form classifies correctly without being listed,
and a new block in an existing script needs no change here. A table of codepoint
ranges was the alternative and it is the per-language list this module must not
have: the one this replaced was already missing Javanese, Balinese, Sundanese,
Tibetan, Tai Tham and Kana Supplement, and eleven of its twenty rows could be
deleted with the whole suite still green.

**N-gramming is bounded, and the bound is an error rather than a truncation.**
Both the input length (``MAX_INPUT_CHARS``) and the emitted term count
(``MAX_TERMS``) are capped and exceeding either raises
``TokenGrowthLimitError``. The two bind in different places and both are
reachable: a spaced text meets the character ceiling first, an unspaced run
meets the term ceiling first, because a run emits one term per cluster.
Silently dropping the tail would leave a belief indexed by its first half and
unreachable by its second, with nothing anywhere saying so. A caller on the
turn path, or rebuilding a log written before these ceilings existed, catches it
— refusing to index is never allowed to cost a main their reply or their store.

``words`` is what a caller splits into words. ``phrases`` is what the query
builder quotes and ``index_text`` is what the index stores, and they are the
same expansion so the two sides cannot drift. ``tokens`` folds case and
diacritics and is what Half uses when it compares two pieces of its own text —
both sides folded the same way, or ``Café`` and ``cafe`` are two different
strands.

Pure and stdlib-only. Nothing here reads a clock, the environment or the log.
"""

from __future__ import annotations

import unicodedata
from typing import Final

from half.errors import TokenGrowthLimitError

#: Scripts written without spaces between words, named as the Unicode character
#: database names them. Matched against the start of ``unicodedata.name``, so
#: one entry covers every block a script is spread across — ``CJK`` takes the
#: unified ideographs, every extension and the compatibility forms at once.
#: These are script classes, never languages: Half does not detect a
#: language and must not need a language list to work.
#:
#: Hangul is here although modern Korean *is* spaced, because Korean glues its
#: particles onto the noun — ``이직을`` is one token and a query for ``이직``
#: would miss it. Same failure, same reason, same treatment.
#:
#: Every entry is pinned by a retrieval case in ``tests/test_scripts.py`` whose
#: query word is drawn only from that script. A class no test can remove is a
#: class that will be removed. ``KANGXI`` was listed here and is deliberately
#: gone: Kangxi radicals and CJK radicals are Unicode symbols rather than
#: letters, so ``words`` drops them before this is ever consulted and no
#: retrieval case can pin the entry. An entry that cannot be pinned is an entry
#: that is not doing anything.
UNSPACED_SCRIPTS: Final[tuple[str, ...]] = (
    "CJK",           # unified ideographs, every extension, compatibility forms
    "IDEOGRAPHIC",   # iteration marks, ideographic number zero
    "HIRAGANA",      # including Kana Supplement
    "KATAKANA",      # including the katakana-hiragana prolonged sound mark
    "HANGUL",        # syllables, jamo, compatibility jamo
    "BOPOMOFO",
    "THAI",
    "LAO",
    "KHMER",
    "MYANMAR",
    "TIBETAN",
    "JAVANESE",
    "BALINESE",
    "SUNDANESE",
    "TAI THAM",
    "TAI LE",
    "TAI VIET",
    "NEW TAI LUE",
)

#: Width prefixes that sit in front of the script name and say nothing about the
#: script: ``HALFWIDTH KATAKANA LETTER WO`` is katakana.
_WIDTH_PREFIXES: Final[tuple[str, ...]] = ("HALFWIDTH ", "FULLWIDTH ")

#: Unicode categories that are neither a word character nor a word boundary:
#: format and control characters, surrogates, private use. Removed outright, so
#: that a zero-width joiner inside an Indic word — or a soft hyphen pasted into
#: a Latin one — can neither split a word nor join two. This mirrors what the
#: AD-18 drop rule already does in ``half.context.build``.
_INVISIBLE: Final[frozenset[str]] = frozenset({"Cc", "Cf", "Co", "Cs"})

#: Canonical combining class of a virama, coeng or other subjoining sign. Such a
#: mark binds the letter that follows it into the same grapheme, which is why
#: ``ខ្មែ`` is one cluster and not ``ខ្`` plus ``មែ``.
_VIRAMA: Final[int] = 9

#: Cluster n-gram sizes used by ``tokens`` only. A set comparison has no
#: adjacency to carry word identity, so the n-grams supply it there. They are
#: deliberately absent from the index, where the phrase does that job and
#: n-grams would only inflate document length and blur bm25.
COMPARISON_NGRAM_SIZES: Final[tuple[int, ...]] = (1, 2, 3)

#: Longest text this tokenizer will look at. A claim is a sentence and a turn is
#: a message; anything past this is neither. Binds first for spaced text.
MAX_INPUT_CHARS: Final[int] = 8_000

#: Ceiling on terms emitted for one text. Binds first for an unspaced run, which
#: emits one term per grapheme cluster where a spaced text emits one per word.
MAX_TERMS: Final[int] = 6_000


def words(text: object) -> list[str]:
    """Word tokens of ``text``, in order, case and accents preserved.

    A word is a run of letters and digits together with the marks that belong
    to them — matras, viramas, nuktas, combining accents — so a word stays one
    word in every script rather than shattering into consonants. Underscore is
    a separator, as it was before. Invisible characters are removed rather than
    treated as boundaries.

    Composed to NFC first, because a query typed on a platform that produces NFD
    must find a belief stored as NFC. Both sides normalize, so both agree.

    Preserved otherwise on purpose: these are handed to FTS5 as phrases, and
    FTS5 does its own folding. Folding twice is how ``café`` became ``caf``.

    Never raises. Anything that is not a string yields no words — the log
    preserves fields this build does not recognise, and one odd value must not
    take an index rebuild down. The growth ceilings live in ``phrases`` and
    ``terms``, which is where growth happens.
    """
    if not isinstance(text, str):
        return []
    found: list[str] = []
    current: list[str] = []
    for char in unicodedata.normalize("NFC", text):
        category = unicodedata.category(char)
        if category in _INVISIBLE:
            continue
        if char.isalnum() or category.startswith("M"):
            current.append(char)
        elif current:
            found.append("".join(current))
            current = []
    if current:
        found.append("".join(current))
    return found


def phrases(text: object) -> list[str]:
    """Each word of ``text`` as the phrase FTS5 should match it by.

    A word in a spaced script is its own phrase, so nothing about Latin changes.
    A word containing a scriptio-continua run has that run cut into grapheme
    clusters, space-separated, so FTS5 sees a token sequence and the phrase
    matches only where those clusters are adjacent.

    Raises ``TokenGrowthLimitError`` past either ceiling.
    """
    return [" ".join(parts) for parts in _expand(text)]


def terms(text: object) -> list[str]:
    """Every index term of ``text``, flat and in order.

    ``phrases`` without the word boundaries. This is what the growth ceiling
    counts and what ``index_text`` joins.
    """
    return [part for parts in _expand(text) for part in parts]


def index_text(text: object) -> str:
    """``terms`` as the single string the FTS index stores.

    Space-separated, which is a boundary in every script ``unicode61``
    recognises, so each term is its own token however it was written. Joining
    the phrases with the same separator is what makes the index and the query
    agree: the store writes ``index_text`` and queries with ``phrases``, and one
    is the join of the other.
    """
    return " ".join(terms(text))


def normalize(word: str) -> str:
    """Casefold ``word`` and strip combining marks.

    ``unicode61``'s ``remove_diacritics`` behaviour, reproduced so that Half's
    own comparisons agree with the index's. The AD-18 drop rule in
    ``half.context.build`` folds with this and depends on it over-folding —
    leave it alone.
    """
    decomposed = unicodedata.normalize("NFKD", word.casefold())
    return "".join(ch for ch in decomposed if not unicodedata.combining(ch))


def tokens(text: object) -> frozenset[str]:
    """Folded comparison tokens of ``text``, for comparing Half's text to itself.

    Each word, plus — for a word cut into clusters — the bounded cluster
    n-grams, because a strand named ``転職`` sits unspaced inside
    ``転職を考えている`` and a set comparison has no adjacency to find it with.
    A spaced word yields itself and nothing else, so Latin is untouched.

    Folded by ``_fold`` rather than ``normalize``: a virama is not a diacritic,
    and stripping it collapses ``यात्रा`` into ``यातरा`` — the false-positive
    class the index just shed, reappearing in the strand matcher.
    """
    found: set[str] = set()
    for parts in _expand(text):
        found.add("".join(parts))
        if len(parts) > 1:
            for size in COMPARISON_NGRAM_SIZES:
                for offset in range(len(parts) - size + 1):
                    found.add("".join(parts[offset:offset + size]))
    return frozenset(folded for part in found if (folded := _fold(part)))


def sequence(text: object) -> tuple[str, ...]:
    """``tokens``' vocabulary **in the order it was written**, one per word.

    The same folding as ``tokens`` and the same treatment of unspaced runs, but
    a sequence rather than a set — because *what was said* and *in what order*
    are two different questions and a set can only answer the first.

    ``half.consolidate.filter.restating`` is why this exists. It compared token
    *sets*, so ``"prefers Delhi over Goa"`` and ``"prefers Goa over Delhi"``
    were judged one claim written twice and never reached the judge — which is
    precisely the disagreement CAP-7 exists to catch, discarded by the cheap
    filter in front of it. It is also the mirror image of the lexical-overlap
    trap this project rejected once: two claims made of the same words are not
    the same claim.

    The cluster n-grams ``tokens`` adds are deliberately absent. They exist so
    that an unspaced strand can be *found inside* a longer run, which is a
    containment question; equality of two whole claims is not.

    Raises ``TokenGrowthLimitError`` past either ceiling, like everything else
    built on ``_expand``.
    """
    return tuple(
        folded for parts in _expand(text)
        if (folded := _fold("".join(parts)))
    )


def is_unspaced(char: str) -> bool:
    """Whether ``char`` belongs to a script written without word spaces.

    Read off the character's own Unicode name, so this needs no codepoint table
    and stays right as Unicode grows.
    """
    try:
        return _UNSPACED_CACHE[char]
    except KeyError:
        pass
    name = unicodedata.name(char, "")
    for prefix in _WIDTH_PREFIXES:
        if name.startswith(prefix):
            name = name[len(prefix):]
            break
    verdict = any(name.startswith(script) for script in UNSPACED_SCRIPTS)
    _UNSPACED_CACHE[char] = verdict
    return verdict


#: ``unicodedata.name`` is a lookup per call and this runs per character of
#: every claim on every rebuild. Pure memoisation of a pure function — the
#: verdict for a codepoint cannot change while the process lives.
_UNSPACED_CACHE: dict[str, bool] = {}


def _fold(term: str) -> str:
    """Casefold and strip diacritics, keeping the marks that carry a word apart.

    ``normalize`` strips every non-zero combining class, which takes the virama
    with the accents: ``यात्रा`` and ``यातरा`` fold together and the strand
    matcher cannot tell two different words apart. A virama joins letters rather
    than decorating one, so it is kept. Nukta and the Latin accents still go —
    ``ज़मीन`` and ``जमीन`` are one word, and so are ``Café`` and ``cafe``.
    """
    decomposed = unicodedata.normalize("NFKD", term.casefold())
    return "".join(
        ch for ch in decomposed
        if not unicodedata.combining(ch) or unicodedata.combining(ch) == _VIRAMA
    )


def _expand(text: object) -> list[list[str]]:
    """Each word's ordered index terms, with the growth ceilings enforced.

    One walk, one budget: the term count is counted across the whole text rather
    than per word, because it is the whole text that becomes one indexed column.
    """
    if not isinstance(text, str):
        return []
    _require_length(len(text))
    expanded: list[list[str]] = []
    emitted = 0
    for word in words(text):
        parts: list[str] = []
        for run, unspaced in _script_runs(word):
            pieces = clusters(run) if unspaced else [run]
            _require_capacity(emitted, len(pieces))
            emitted += len(pieces)
            parts.extend(pieces)
        # A term carrying no letter or digit is a separator to FTS5 and matches
        # nothing on either side, so it would only spend the budget.
        parts = [part for part in parts if any(ch.isalnum() for ch in part)]
        if parts:
            expanded.append(parts)
    return expanded


def _script_runs(word: str) -> list[tuple[str, bool]]:
    """``word`` split wherever it enters or leaves a scriptio-continua script.

    ``転職plan`` is two runs, so the CJK half is cut into clusters and the Latin
    half is left whole. One claim may mix scripts and both halves must stay
    findable.

    A combining mark inherits the run it is attached to rather than being
    classified on its own, so a mark can never open a run or close one.
    """
    if not word:
        return []
    runs: list[tuple[str, bool]] = []
    start = 0
    unspaced = is_unspaced(word[0])
    for position, char in enumerate(word[1:], start=1):
        if unicodedata.category(char).startswith("M"):
            continue
        current = is_unspaced(char)
        if current != unspaced:
            runs.append((word[start:position], unspaced))
            start = position
            unspaced = current
    runs.append((word[start:], unspaced))
    return runs


def clusters(run: str) -> list[str]:
    """One run of text, cut into grapheme clusters.

    A cluster is a base character plus the marks that belong to it, and a virama
    or coeng binds the letter after it into the same cluster. Cutting at raw
    codepoint offsets instead is what stripped Khmer dependent vowels and
    produced fragments beginning on a bare mark.

    **Public because a second consumer arrived**, and a second implementation
    would have been a codepoint slice: ``half.voice.compose.Sample`` bounds the
    main's own words to a length, and a bound that cuts at an offset splits the
    cluster it lands in — which is the exact failure this function exists to
    have already solved, and the reason the withheld rule was imported rather
    than reimplemented one package over.
    """
    clusters: list[str] = []
    current = ""
    joining = False
    for char in run:
        if not current:
            current = char
        elif joining or unicodedata.category(char).startswith("M"):
            current += char
        else:
            clusters.append(current)
            current = char
        joining = unicodedata.combining(char) == _VIRAMA
    if current:
        clusters.append(current)
    return clusters


def _require_length(length: int) -> None:
    if length > MAX_INPUT_CHARS:
        raise TokenGrowthLimitError(
            f"text of {length} characters exceeds the "
            f"{MAX_INPUT_CHARS}-character tokenizer limit"
        )


def _require_capacity(emitted: int, adding: int) -> None:
    if emitted + adding > MAX_TERMS:
        raise TokenGrowthLimitError(
            f"tokenization would emit more than the {MAX_TERMS}-term limit"
        )
