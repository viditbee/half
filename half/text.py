"""One tokenizer, shared by everything that splits a main's words.

Three modules used to split text and all three disagreed: the store's FTS query
builder was unicode-aware, while the prefix builder and the strand matcher were
``[A-Za-z0-9]`` only. The consequences were not cosmetic for a product aimed at
India:

* ``build_prefix({"subject": "आशा"})`` produced ``""``, so a Devanagari subject
  was dropped from the index entirely and could never be retrieved.
* A person or loop named in any non-Latin script could never become a live
  strand, because the matcher found no tokens in the message either.
* ``café-plans`` was indexed as ``caf plans``, while FTS5's unicode61 tokenizer
  folds a query for ``café`` to ``cafe`` — so the belief was permanently
  unfindable by the word it was named after.

So: one split, unicode-aware, used everywhere. ``words`` is the split FTS5
performs, and is what goes *into* the index. ``tokens`` additionally folds case
and strips combining marks, mirroring unicode61's ``remove_diacritics``, and is
what Half uses when it compares two pieces of its own text — both sides folded
the same way, or ``Café`` and ``cafe`` are two different strands.

Pure and stdlib-only. Nothing here reads a clock, the environment or the log.
"""

from __future__ import annotations

import re
import unicodedata
from typing import Final

#: Runs of word characters, underscore excluded — the same boundaries SQLite's
#: unicode61 tokenizer uses, so what Half indexes and what FTS5 indexes agree.
_WORD: Final = re.compile(r"[^\W_]+", re.UNICODE)


def words(text: object) -> list[str]:
    """Word tokens of ``text``, in order, case and accents preserved.

    Preserved on purpose: this is the form that goes into the FTS index, and
    FTS5 does its own folding. Folding twice is how ``café`` became ``caf``.
    Anything that is not a string yields no words rather than raising — the log
    preserves fields this build does not recognise, and one odd value must not
    take an index rebuild down.
    """
    if not isinstance(text, str):
        return []
    return _WORD.findall(text)


def normalize(word: str) -> str:
    """Casefold ``word`` and strip combining marks.

    ``unicode61``'s ``remove_diacritics`` behaviour, reproduced so that Half's
    own comparisons agree with the index's.
    """
    decomposed = unicodedata.normalize("NFKD", word.casefold())
    return "".join(ch for ch in decomposed if not unicodedata.combining(ch))


def tokens(text: object) -> frozenset[str]:
    """Normalized word tokens of ``text``, for comparing Half's text to itself."""
    return frozenset(normalize(word) for word in words(text) if word)
