"""The reranker port and the types retrieval returns (AD-5).

**One method.** gbrain's own docs record what happens otherwise: their storage
engine interface absorbed embedding and chunking, grew past a hundred methods,
and stopped being something anyone could reason about. Everything a reranker
could want to know — the query, the candidates, their scores, their beliefs —
travels in the two arguments of ``rerank``. A second method needs human
sign-off, not a commit.

**Reordering only.** A reranker may not drop a candidate. That is AD-24 one
level down: pruning here would be a filter wearing a ranker's clothes, and the
retriever rejects a short return rather than silently shrinking the set.

No implementation ships in v1 (AD-5, AD-19). The port exists so that absence is
*annotated* rather than invisible — a caller can always tell whether it is
looking at reranked results or at the fallback.
"""

from __future__ import annotations

from collections.abc import Iterator, Mapping, Sequence
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any, Protocol, runtime_checkable


class RerankSource(StrEnum):
    """How the returned order was produced.

    Lifted from claude-obsidian's ``rerank.py``, which annotates a fallback
    (``noop-no-ollama``, ``noop-no-model``) instead of hiding it. Degradation
    that is not recorded in the result is degradation nobody notices.
    """

    #: A reranker ran and its order was accepted.
    RERANKED = "reranked"
    #: No reranker was configured. Correct BM25-fused order, unchanged.
    ABSENT = "noop-no-reranker"
    #: A reranker was configured and misbehaved. Same order as ``ABSENT``.
    FAILED = "noop-reranker-failed"

    @property
    def is_noop(self) -> bool:
        return self is not RerankSource.RERANKED


@dataclass(frozen=True, slots=True)
class Candidate:
    """One belief that matched, with everything ranking needs about it.

    ``score`` and ``weights`` are **volatile**: they are recomputed per query
    from folded state and never written anywhere (AD-26). ``weights`` carries
    the component breakdown so a caller can see *why* an order came out the way
    it did, which is the difference between a ranker you can debug and a
    number you have to trust.
    """

    id: str
    claim: str
    prefix: str
    #: Raw ``bm25()`` from FTS5 — negative, more negative is a better match.
    #: ``None`` for a candidate the backstop supplied rather than a term match.
    bm25: float | None
    #: The folded belief record, as the log wrote it.
    belief: Mapping[str, Any] = field(default_factory=dict)
    #: Fused relevance in (0, 1]. Higher is better — the opposite sense to
    #: ``bm25``, deliberately, so nothing downstream has to remember which.
    score: float = 0.0
    #: Component multipliers: bm25, strand, recency, salience.
    weights: Mapping[str, float] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class Ranked:
    """A ranked candidate set plus how it was ordered.

    Both annotations are on the envelope rather than on each candidate so they
    survive an empty result: "no beliefs, and no reranker ran" is a different
    statement from "no beliefs", and an empty store must never be reported as
    missing access.
    """

    beliefs: tuple[Candidate, ...] = ()
    rerank: RerankSource = RerankSource.ABSENT
    #: True when beliefs were dropped before scoring, or when the caller asked
    #: for none. Never silent: a cap the result does not mention is
    #: indistinguishable from a main who simply has nothing, and that is the
    #: shape "I don't have access to that" arrives in.
    truncated: bool = False

    @property
    def ids(self) -> tuple[str, ...]:
        return tuple(c.id for c in self.beliefs)

    @property
    def degraded(self) -> bool:
        """True when no reranker contributed to this order."""
        return self.rerank.is_noop

    def __len__(self) -> int:
        return len(self.beliefs)

    def __iter__(self) -> Iterator[Candidate]:
        return iter(self.beliefs)

    def __getitem__(self, index: int) -> Candidate:
        return self.beliefs[index]

    def __bool__(self) -> bool:
        return bool(self.beliefs)


@runtime_checkable
class Reranker(Protocol):
    """The whole optional-reranker surface. One method, by decision."""

    def rerank(
        self, query: str, candidates: Sequence[Candidate]
    ) -> Sequence[Candidate]:
        """Return ``candidates`` reordered — the same set, nothing added or
        dropped.

        May raise: the retriever treats any failure as a no-op and falls back
        to the order it already had (AD-5). An implementation is never
        responsible for its own fallback.
        """
        ...
