"""The contextual prefix: structural, deterministic, no model (AD-19).

Anthropic's contextual retrieval has a model write a short prefix per chunk,
because a chunk is a fragment torn out of a document and its context lives in
the surrounding pages. claude-obsidian's ``contextual-prefix.py`` keeps that as
tier 1 and 2, and falls back to a **tier 3 synthetic prefix** assembled from the
page's own front matter when no model may be called.

For Half, tier 3 is not a fallback — it is the whole design. A belief is
already a self-contained claim carrying its subject, its ledger and the loop it
sits on, so nothing about its context has to be inferred. Tier 3 loses most of
the benefit for chunks and almost none of it for claims, and it costs no model
call, no network, and no nondeterminism.

The prefix is indexed as a second FTS column, which is what makes a query
matching a subject or a loop slug retrieve a belief whose claim text never
mentions either.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from half.text import words


def build_prefix(belief: Mapping[str, Any]) -> str:
    """A short, deterministic sentence situating ``belief`` among the others.

    Pure: same record in, same string out, forever. Called at index time by
    the store's rebuild, so it must not read a clock, a model, or the network —
    a prefix that varied across rebuilds would make the FTS index disagree with
    itself between two replays of one log (AD-4, AD-30).

    Returns ``""`` when a belief carries none of the three fields, which the
    store stores as NULL rather than as an empty indexed row.
    """
    parts = [
        _field(belief.get("subject")),
        _field(belief.get("ledger")),
        _field(belief.get("loop")),
    ]
    return ". ".join(part for part in parts if part)


def _field(value: object) -> str:
    """One field's own words, or ``""``.

    Values only — never the connective words that would join them into a
    sentence. An earlier version emitted "about {subject}. {ledger} ledger.
    open loop {loop}", which put the literal tokens *about*, *ledger* and
    *open loop* into every belief's indexed text. Since a query is OR-joined
    over its words, any message containing "about" then term-matched the entire
    belief set: the bm25 signal was noise and the never-empty backstop became
    nearly unreachable. Template vocabulary is shared by every document, so it
    can only ever add matches that mean nothing.

    Slugs arrive kebab-case (``buy-farmland``) and FTS5 would keep that as one
    token, so the words are separated here. Case and accents are preserved —
    FTS5 folds them itself, and folding twice is how ``café`` becomes ``caf``.

    Non-strings yield empty rather than raising: the log preserves fields this
    build does not recognise, and one odd shape must not take the index down.
    """
    return " ".join(words(value))
