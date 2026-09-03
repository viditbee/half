"""The cheap gate in front of the judge, and what a full budget takes first.

**Everything here runs before any model comparison and none of it is one**
(CAP-7). A couple this module turns away never reaches
``half.consolidate.port``, so the judge's cost is a function of what survived
rather than of the ledger's size — which is the half of CAP-7's budget sentence
that ``half.consolidate.candidates`` does not already cover. The bound decides
*which pairs exist*; this decides *which are worth paying for*.

**Extracted from HippoRAG, with the part that is a model call left behind.**
The manifest row is `src/hipporag/rerank.py` (`DSPyFilter`), open since story 4
for exactly this moment, and reading it is what settled the design — mostly by
showing where the cheap step actually is. `DSPyFilter` is *not* the cheap
filter: it is one LLM call per query, unconditionally. The pruning that makes it
affordable happens upstream in `HippoRAG.rerank_facts`, which `argsort`s dense
scores and hands the model a top-`linking_top_k` of **five**, with the filter
unable to expand past what it was given. That placement is what was taken —
a cheap non-model narrowing to a small set, then one expensive step that cannot
widen it — and it is why ``mint.slate`` computes the whole survivor list before
a single call is made. Rejected: the filter itself, which is a model call this
story forbids outright; and its `difflib.get_close_matches(..., cutoff=0.0)`
realignment, already rejected once in story 4 for the reason it is rejected
again here — a cutoff of zero always returns a nearest string, so a filter built
on it can never say *nothing survived*.

**Three cheap rules, and each of them rejects something the bound admits.** A
filter whose rejections were already made upstream is a filter that reads as
enforcement and asserts nothing — the *"identical either way"* failure this
project has shipped once. So each rule below is exercised by a case whose pair
the candidate sets produce and this module turns away:

* **Both halves must carry a claim this build can read.** A judge handed an id
  and no text can only guess, and a pass that paid for that guess would have
  spent its budget on the one comparison nothing could answer. *Readable* and
  not merely *present*: a claim that is all punctuation, or one past ``tokens``'
  growth ceiling, used to reach the ranking scoring ``0.0`` — which is the score
  of a term every entry carries, so the thing nothing could compare sat at the
  bottom of the queue instead of outside it.
* **The two must not be on the same named ledger.** The mirror *is* the gap
  between what the main says and what they do (glossary, CAP-7), so two stated
  entries disagreeing is a question about Half's own record-keeping and two
  revealed ones is a question about the sources. A pair with a ledger missing
  on either side is admitted, because unknown is not the same as same.
* **The two must not be restating each other.** The same folded tokens *in the
  same order* is one claim written twice, which is a duplicate rather than a
  disagreement. Ordered, because comparing token **sets** made ``"prefers Delhi
  over Goa"`` and ``"prefers Goa over Delhi"`` a restatement of each other —
  the disagreement CAP-7 exists to catch, discarded by the cheap filter in
  front of it, and the mirror image of the lexical-overlap trap loop 1
  rejected.

**Ranking, from honcho's surprisal, with the embeddings left behind.** The
manifest row is `src/dreamer/surprisal.py`, and the load-bearing detail is which
of its seven tree implementations to read. The default `kdtree` computes
`dim * log(mean kNN distance)` over embeddings that a model produced — rejected
outright, because it would put a model in front of the filter, which is the one
thing CAP-7's ordering forbids. `rptree` computes the same quantity from
**counts**: `S(x) = Σ -log(n_child / n_parent)` along a root-to-leaf path, no
model anywhere. That is the shape taken. ``surprisal`` below estimates
`-log2 p(term)` from the main's own ledger — a term almost every belief carries
tells you nothing, a term one belief carries is the anomaly — and takes the
rarest term rather than the sum, so a long claim does not outrank a sharp one
merely by being long. Also taken: honcho's *fail soft to empty* discipline, and
its `max(1, ...)` floor, which is why a budget of one still consults somebody.
Rejected besides the embeddings: its min-max normalisation, which is
rank-preserving and therefore decides nothing, and its
`TOP_PERCENT_SURPRISAL` — a percentile of a candidate set is not a cost bound,
and the cost bound is the thing CAP-7 asks for.

Pure, offline and clockless. Nothing here reads a store, a clock or a model.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from math import log2
from typing import Final

from half.consolidate.candidates import BOTH, Couple, Entry
from half.text import sequence, tokens

#: What an entry scores when there is nothing in it to score. **Not the
#: surprisal of an unseen term**, which is what this used to claim to be and
#: is the opposite of what it is: ``-log2`` of the *smallest* estimate is the
#: *largest* value the formula produces, and zero is what a term every single
#: entry carries comes to. A claim this build cannot tokenise therefore ranked
#: as the least surprising thing in the ledger rather than being kept out of
#: the ranking at all.
#:
#: It stays zero, and ``readable`` is what makes that harmless: an entry with
#: no readable claim never reaches the judge, so the floor is a floor for a
#: value nothing is spent on rather than a rank an unreadable belief competes
#: from.
UNRANKED: Final[float] = 0.0


def carries_claim(item: Entry) -> bool:
    """Whether ``item`` says anything a judgement could be about."""
    return isinstance(item, Entry) and bool(item.claim.strip())


def readable(item: Entry) -> bool:
    """Whether this build can actually read ``item``'s claim.

    ``carries_claim`` asks whether there is text; this asks whether the text
    comes to anything — a claim that is all punctuation, or one so long that
    ``tokens`` refuses to expand it, has characters in it and no words.

    Kept apart from the ranking deliberately. Such an entry used to reach the
    priority queue scoring ``0.0``, which is the score of a term *every* entry
    carries — so an unreadable claim sat at the bottom of the ranking, still
    inside the budget, still able to be bought if the queue were short. An
    entry nothing can compare is one to leave alone, not one to rank last.
    """
    return carries_claim(item) and bool(_marks(item.claim))


def crossing(couple: Couple) -> bool:
    """Whether the two halves sit on **different** named ledgers.

    True when either side names no ledger: unknown is not the same as same, and
    refusing a pair because Half failed to record where half of it came from
    would make a gap in the log into a gap in the mirror.
    """
    named = [
        item.ledger for item in couple.both
        if isinstance(item.ledger, str) and item.ledger.strip()
    ]
    return len(named) < BOTH or len(set(named)) == BOTH


def restating(couple: Couple) -> bool:
    """Whether the two halves say the same thing in the same words, **in the
    same order**.

    Compared with ``half.text.sequence``, which folds case and diacritics and
    cuts unspaced scripts into clusters — so this means the same thing in
    Devanagari, Khmer and Japanese as it does in English, which a naive string
    equality would not.

    **Ordered, and that is the correction.** This compared token *sets*, so
    ``"prefers Delhi over Goa"`` and ``"prefers Goa over Delhi"`` were one claim
    written twice and never reached the judge — the exact disagreement CAP-7
    exists to catch, thrown away by the cheap filter standing in front of it,
    and the mirror image of the lexical-overlap trap this story rejected in its
    first loop. Two claims made of the same words are not the same claim; a
    restatement is the same words *in the same order*.
    """
    shapes = {_ordered(item.claim) for item in couple.both}
    return len(shapes) < BOTH


def admits(couple: Couple) -> bool:
    """Whether ``couple`` may reach the judge at all. Cheap, offline, total.

    Never raises: this runs once per couple on a path where an exception costs
    a main their whole night's minting, and a couple this build cannot read is
    one to leave alone rather than one to spend a judgement on.
    """
    if not isinstance(couple, Couple) or len(couple.both) != BOTH:
        return False
    if len(set(couple.names)) != BOTH:
        return False
    if not all(readable(item) for item in couple.both):
        return False
    if not crossing(couple):
        return False
    return not restating(couple)


def corpus(known: Mapping[str, Entry]) -> tuple[dict[str, int], int]:
    """How many entries carry each term, and how many entries there are.

    The counts a surprisal is estimated from, computed once per pass over the
    main's own ledger rather than per couple. Document frequency, not term
    frequency: a word repeated ten times in one claim is one belief that
    mentions it, exactly as ten mentions in one email thread are one support
    (glossary, *independence*).
    """
    counts: dict[str, int] = {}
    total = 0
    for item in known.values():
        total += 1
        for mark in _marks(item.claim):
            counts[mark] = counts.get(mark, 0) + 1
    return counts, total


def surprisal(item: Entry, *, counts: Mapping[str, int], total: int) -> float:
    """How anomalous ``item`` is against the main's own ledger. Counts only.

    ``-log2 p`` of its rarest term, with ``p`` estimated as the fraction of
    entries carrying that term, add-one smoothed so a term the corpus has never
    seen is finite rather than infinite — honcho's `+1e-10` guard, spelled as
    the smoothing it actually is.

    The **rarest** term rather than the sum, which is the one deliberate
    departure from the reference: `rptree` sums along a path of fixed length, so
    length is not a free variable there. Here it would be — summing would let a
    long claim outrank a sharp one for saying more words, and *what is worth
    surfacing* is not *what was said at length*.
    """
    marks = _marks(item.claim)
    if not marks or total <= 0:
        return UNRANKED
    return max(
        -log2((counts.get(mark, 0) + 1) / (total + 1)) for mark in marks
    )


def weight(
    couple: Couple, *, counts: Mapping[str, int], total: int
) -> float:
    """A couple's surprisal: the sum of its two halves'.

    A **sum**, which is what makes it symmetric — the same number whichever way
    round the couple was built — where any *comparison* of the two would be a
    ranking of one side over the other in the one function every mint runs
    through.
    """
    return sum(
        surprisal(item, counts=counts, total=total) for item in couple.both
    )


def priority(
    offered: Iterable[Couple], *, counts: Mapping[str, int], total: int
) -> tuple[Couple, ...]:
    """``offered`` most surprising first, ties broken by the couple's own id.

    Deterministic to the last element, which is what makes *"the same log twice
    mints the same set"* true when the budget cuts the list: a tie broken by
    iteration order would mint one tension tonight and its neighbour tomorrow
    from a log that had not changed.
    """
    return tuple(
        sorted(
            offered,
            key=lambda item: (
                -weight(item, counts=counts, total=total), item.id
            ),
        )
    )


def _marks(text: object) -> frozenset[str]:
    """``half.text.tokens``, and never an exception.

    ``tokens`` refuses to expand text past its growth ceilings rather than
    truncating it (``TokenGrowthLimitError``), which is right for an index and
    wrong for a filter: one enormous claim must cost that belief its comparison,
    not the main their night. An empty set means *nothing to compare*, which
    ``readable`` turns into a rejection rather than into a ranking.
    """
    try:
        return tokens(text)
    except Exception:  # noqa: BLE001 - one claim, never the pass
        return frozenset()


def _ordered(text: object) -> tuple[str, ...]:
    """``half.text.sequence``, and never an exception. See ``_marks``."""
    try:
        return sequence(text)
    except Exception:  # noqa: BLE001 - one claim, never the pass
        return ()


__all__ = [
    "UNRANKED",
    "admits",
    "carries_claim",
    "corpus",
    "crossing",
    "priority",
    "readable",
    "restating",
    "surprisal",
    "weight",
]
