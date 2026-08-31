"""Independence-gated corroboration (CAP-3).

Ten mentions of one fact in a single email thread is **one** piece of evidence,
not ten. Without this the belief set inflates with echoes of a single moment,
and "ingestion is unbounded, belief is bounded" fails in the first noisy month
— Half then states things with the full weight of the mirror behind them, on
the strength of one email quoted nine times.

The mechanism is union-find, adapted from claude-obsidian's ledger
(`_independent_group_count`): each source contributes an identity *set*, any
two sources sharing any identity value are unioned, and the answer is the
number of distinct groups.

For mail the identity members are the thread, the sender, and the content
digest — so a long reply chain collapses by thread, and a forward from someone
else collapses by content.
"""

from __future__ import annotations

import unicodedata
from collections.abc import Iterable, Mapping
from typing import Any


def _normalize(value: str) -> str:
    """Casefold under NFC so two spellings of one identity match."""
    return unicodedata.normalize("NFC", value.strip()).casefold()


def identity_set(source_id: str, source: Mapping[str, Any]) -> set[str]:
    """Every handle by which this source might be the same as another.

    Namespaced by kind so a thread id can never collide with a digest.
    """
    values = {f"source:{_normalize(source_id)}"}
    for key, kind in (("thread_id", "thread"), ("sender", "sender"),
                      ("digest", "content"), ("independence_key", "declared")):
        raw = source.get(key)
        if isinstance(raw, str) and raw.strip():
            values.add(f"{kind}:{_normalize(raw)}")
    return values


def independent_groups(
    supporting: Iterable[tuple[str, Mapping[str, Any]]]
) -> int:
    """How many genuinely independent supports these sources represent."""
    items = list(supporting)
    if not items:
        return 0

    parents = list(range(len(items)))

    def find(index: int) -> int:
        while parents[index] != index:
            parents[index] = parents[parents[index]]  # path compression
            index = parents[index]
        return index

    def union(left: int, right: int) -> None:
        left_root, right_root = find(left), find(right)
        if left_root != right_root:
            parents[right_root] = left_root

    identities = [identity_set(sid, src) for sid, src in items]

    # An index from identity value to the sources carrying it, so this is
    # linear in the number of shared handles rather than quadratic in sources.
    seen: dict[str, int] = {}
    for index, values in enumerate(identities):
        for value in values:
            first = seen.setdefault(value, index)
            if first != index:
                union(first, index)

    return len({find(index) for index in range(len(items))})
