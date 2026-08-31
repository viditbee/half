"""The fusion: bm25 x strand x recency x salience (CAP-1, CAP-9, AD-5).

`half.store` answers *which beliefs contain these words, and how strongly*.
This module answers *which of them matter to this main, in this conversation,
right now* — and the two are deliberately different jobs in different layers.
gbrain's docs are the cautionary tale: embedding and chunking migrated into
their storage engine, which then grew past a hundred methods and stopped being
reasonable about either job. Ranking policy lives here and nowhere in
``half/store/``.

**Every factor has a positive floor.** The product of four multipliers, each in
``(0, 1]``, is itself in ``(0, 1]``. There is no combination of inputs that
scores a belief out of the result set, which is AD-24 made arithmetic rather
than promised.

**The candidate set is never empty while the store is not.** When a query
matches no term at all, the backstop ranks the belief set on the remaining
three factors instead of returning nothing. "No results" and "no beliefs" would
otherwise be the same answer, and the first is one paraphrase away from *"I
don't have access to that."*

**A bound on scoring is salience-ordered and announced.** Reachable means
findable by a matching query, not present in every candidate set, so bounding
how many beliefs a turn scores is legitimate. What is not legitimate is the
shape the first version had: ``ORDER BY id LIMIT 500`` in SQL, under a
docstring reading "Nothing here is a filter". That silently made a main's
oldest five hundred identifiers the only ones a backstop could ever reach. So
the bound moved here, where salience can be computed: above ``max_scored``
candidates the set is pre-ranked by salience alone — no bm25, no strand, the
cheap half of the fusion — and the survivors go on to be scored fully. When
that fires, ``Ranked.truncated`` says so.

**The reranker runs last, on a pruned set.** HippoRAG prunes candidates before
its expensive stage rather than after; the same shape here means an optional
reranker sees ``limit`` candidates, not the whole belief set. What is *not*
copied is how HippoRAG maps a reranked item back to its candidate:
``difflib.get_close_matches`` with ``cutoff=0.0`` always returns a nearest
string, so a hallucinated item silently becomes whichever real one looked
closest. Mapping here is by exact id, and an id that was not offered is a
failure, not a near miss.
"""

from __future__ import annotations

import logging
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Final

from half.errors import RetrievalDisabled, RetrievalError
from half.retrieval.port import Candidate, Ranked, Reranker, RerankSource
from half.retrieval.salience import days_between, parse_time, salience
from half.retrieval.strands import Strands, strand_weight, strands_of
from half.store.store import Store

logger = logging.getLogger(__name__)

#: Results returned to a caller unless it asks for more.
DEFAULT_LIMIT: Final[int] = 10

#: Ceiling on how many beliefs are scored for one query. The belief set is
#: bounded by design — the free tier's cost model depends on it — so this is a
#: guard against a pathological store, not a routine truncation. When it does
#: fire it drops the *least salient*, and the result says it happened.
MAX_SCORED: Final[int] = 5_000

#: Floor of the bm25 multiplier. A belief the backstop supplied, with no term
#: match at all, still ranks; it just starts a long way behind.
BM25_FLOOR: Final[float] = 0.1

#: bm25 strength at which the multiplier sits halfway to 1.0.
BM25_MIDPOINT: Final[float] = 1.0

#: Floor of the recency multiplier. Old beliefs are the point of the product.
RECENCY_FLOOR: Final[float] = 0.25

#: Days after which a belief's own age halves its recency contribution.
RECENCY_HALF_LIFE_DAYS: Final[float] = 180.0


@dataclass(slots=True)
class RetrievalSwitch:
    """Whether ledger retrieval is permitted at all (CAP-12).

    One flag, held by the actor and read by the retriever, so that disabling
    retrieval is a single act rather than a condition each call site has to
    remember. Crisis mode turns it off before anything else runs; nothing here
    turns it back on, because restoring it is aftercare's decision and aftercare
    is story 6.

    Volatile, like every other piece of state on this path (AD-26): it never
    enters the log and a restart begins enabled.
    """

    enabled: bool = True

    def disable(self) -> None:
        self.enabled = False

    def enable(self) -> None:
        self.enabled = True


@dataclass(slots=True)
class Retriever:
    """Ranks a main's beliefs against a query. Reads only; writes nothing."""

    store: Store
    #: Optional by AD-5 and unimplemented in v1 by AD-19. Absence is annotated.
    reranker: Reranker | None = None
    #: This main's switch. Owned by the actor, so one main's crisis cannot
    #: silence another's retrieval — the failure a single shared switch caused.
    switch: RetrievalSwitch = field(default_factory=RetrievalSwitch)
    #: How many beliefs one turn will score. Injectable so the truncation path
    #: is reachable from a test without building a pathological store.
    max_scored: int = MAX_SCORED

    def retrieve(
        self,
        query: str,
        *,
        now: str,
        strands: Strands | None = None,
        limit: int = DEFAULT_LIMIT,
    ) -> Ranked:
        """Rank the belief set against ``query`` as of ``now``.

        ``now`` is injected as an ISO-8601 stamp and is the only notion of time
        in the whole path — nothing under ``half/retrieval/`` reads a clock, so
        two runs over one store with one ``now`` are identical results.

        ``limit`` bounds what is *returned*; ``max_scored`` bounds what is
        *considered*. A ``limit`` of zero or less returns nothing and sets
        ``Ranked.truncated``, so that "you asked for none" cannot be mistaken
        for "this main has none".

        Raises ``RetrievalDisabled`` when switched off, and ``RetrievalError``
        for a ``now`` that cannot be read: a caller that mangles the timestamp
        gets an error rather than a silently mis-ranked set.
        """
        if not self.switch.enabled:
            raise RetrievalDisabled(
                "ledger retrieval is disabled for this main; a caller must "
                "branch on the mode rather than treat this as an empty store"
            )

        moment = parse_time(now)
        if moment is None:
            raise RetrievalError(f"'now' must be an ISO-8601 timestamp, got {now!r}")

        limit = int(limit)
        rows = self.store.candidates(query)
        if not rows:
            # No term matched. Rank everything on the other three factors
            # rather than answering "nothing" — this is the branch that keeps
            # a topic switch from emptying the set (AD-24).
            rows = self.store.all_candidates()
        # An empty store falls through the same path rather than short-circuiting:
        # the result is an empty set with an honest annotation, not an error, and
        # never phrased upstream as missing access.
        loops = self.store.loops()
        rows, truncated = self._bound(rows, moment, loops)

        scored = [self._score(row, moment, loops, strands) for row in rows]
        # Ties break on id so that equal scores are still a total order — the
        # determinism requirement is on the returned sequence, not on the set.
        scored.sort(key=lambda c: (-c.score, c.id))
        ordered = tuple(scored[:limit]) if limit > 0 else ()

        beliefs, source = self._rerank(query, ordered)
        # A caller asking for nothing gets nothing, and is told it was a cut
        # rather than an empty ledger — the two must never look alike.
        return Ranked(
            beliefs=beliefs, rerank=source, truncated=truncated or limit <= 0
        )

    def _bound(
        self,
        rows: list[Mapping[str, Any]],
        now: datetime,
        loops: Mapping[str, Mapping[str, Any]],
    ) -> tuple[list[Mapping[str, Any]], bool]:
        """Cap how many beliefs this turn scores, keeping the most salient.

        Salience is the ordering because it is the only one of the four factors
        that is a property of the belief alone: bm25 needs the query, strand
        needs the conversation, and both are the expensive half. Ordering a cap
        by id instead — the shape this replaced — makes reachability a function
        of when a belief happened to be created, which is not a ranking at all.
        """
        if len(rows) <= self.max_scored:
            return rows, False
        ranked = sorted(
            rows,
            key=lambda row: (
                -salience(row.get("belief") or {}, now=now, loops=loops),
                str(row.get("id", "")),
            ),
        )
        return ranked[: self.max_scored], True

    # -- scoring -------------------------------------------------------------

    def _score(
        self,
        row: Mapping[str, Any],
        now: datetime,
        loops: Mapping[str, Mapping[str, Any]],
        strands: Strands | None,
    ) -> Candidate:
        belief = row.get("belief") or {}
        weights = {
            "bm25": _bm25_weight(row.get("score")),
            "strand": strand_weight(strands_of(belief), strands),
            "recency": _recency_weight(belief.get("t"), now),
            "salience": salience(belief, now=now, loops=loops),
        }
        score = 1.0
        for value in weights.values():
            score *= value
        return Candidate(
            id=str(row.get("id", "")),
            claim=row.get("claim") or "",
            prefix=row.get("prefix") or "",
            bm25=row.get("score"),
            belief=belief,
            score=score,
            weights=weights,
        )

    # -- reranking -----------------------------------------------------------

    def _rerank(
        self, query: str, ordered: tuple[Candidate, ...]
    ) -> tuple[tuple[Candidate, ...], RerankSource]:
        """Apply the reranker if there is one, and survive it if there is.

        Every failure mode collapses to the same outcome: the order this module
        already computed, annotated so the degradation is visible. Nothing a
        reranker does can raise out of here (AD-5).
        """
        if self.reranker is None:
            return ordered, RerankSource.ABSENT
        try:
            returned = self.reranker.rerank(query, ordered)
            return _accept(ordered, returned), RerankSource.RERANKED
        except Exception as exc:  # noqa: BLE001 - an optional stage is never fatal
            # The exception *type* only. A traceback or a message would carry
            # whatever a third-party reranker chose to put in it, and that is
            # belief text often enough to be a leak (AD-22).
            logger.warning(
                "reranker raised %s; falling back to bm25 order", type(exc).__name__
            )
            return ordered, RerankSource.FAILED


def _accept(
    offered: tuple[Candidate, ...], returned: Sequence[Candidate]
) -> tuple[Candidate, ...]:
    """Map a reranker's output back onto the candidates it was given.

    By exact id, never by similarity. A reranker that invents, repeats or drops
    a candidate is rejected outright: reordering is the contract, and a short
    return would be a filter — the thing AD-24 forbids — arriving through the
    one door that was supposed to be optional.
    """
    by_id = {candidate.id: candidate for candidate in offered}
    accepted: list[Candidate] = []
    seen: set[str] = set()
    for item in returned:
        ident = getattr(item, "id", None)
        if not isinstance(ident, str) or ident not in by_id or ident in seen:
            raise RetrievalError("reranker returned a candidate it was not offered")
        seen.add(ident)
        accepted.append(by_id[ident])
    if len(accepted) != len(offered):
        raise RetrievalError("reranker dropped candidates; it may only reorder")
    return tuple(accepted)


def _bm25_weight(raw: object) -> float:
    """FTS5's ``bm25()`` as a multiplier in ``[BM25_FLOOR, 1.0)``.

    ``bm25()`` is negative and more negative is a better match, so the sign is
    flipped here once and never thought about again. Saturating rather than
    normalised across the candidate set, because a set-relative score would
    make one belief's weight depend on which others happened to match.
    """
    if not isinstance(raw, (int, float)) or isinstance(raw, bool):
        return BM25_FLOOR
    strength = max(0.0, -float(raw))
    return BM25_FLOOR + (1.0 - BM25_FLOOR) * strength / (BM25_MIDPOINT + strength)


def _recency_weight(stamp: object, now: datetime) -> float:
    """How recently the belief itself was recorded, in ``[RECENCY_FLOOR, 1.0]``.

    Distinct from salience's corroboration term on purpose: this is the age of
    the record, that is the age of the last confirmation. A claim asserted years
    ago and confirmed last week should not be ranked as stale.
    """
    moment = parse_time(stamp)
    if moment is None:
        return RECENCY_FLOOR
    age = days_between(now, moment)
    decayed = 0.5 ** (age / RECENCY_HALF_LIFE_DAYS)
    return RECENCY_FLOOR + (1.0 - RECENCY_FLOOR) * decayed
