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


#: What makes two sources the same evidence.
#:
#: Sender is deliberately **absent**. Unioning on sender is transitive, so any
#: person appearing in two threads links those threads, and a handful of such
#: people link nearly everything — corroboration then trends to one group and
#: the gate never opens. Tested at scale rather than on three hand-built
#: sources, which is how that stayed invisible.
IDENTITY_FIELDS: tuple[tuple[str, str], ...] = (
    ("thread_id", "thread"),
    ("digest", "content"),
    ("independence_key", "declared"),
)


def _normalize(value: str) -> str:
    """Casefold under NFC so two spellings of one identity match."""
    return unicodedata.normalize("NFC", value.strip()).casefold()


def identity_set(source_id: str, source: Mapping[str, Any]) -> set[str]:
    """Every handle by which this source might be the same as another.

    Namespaced by kind so a thread id can never collide with a digest.
    """
    if not str(source_id).strip():
        raise ValueError("source_id is required; an empty id unions everything")
    values = {f"source:{_normalize(str(source_id))}"}
    for key, kind in IDENTITY_FIELDS:
        raw = source.get(key)
        # Coerced rather than type-checked: a provider handing back an integer
        # thread id would otherwise drop the identity silently, and ten
        # messages in one thread would count as ten independent supports.
        if raw is not None and str(raw).strip():
            values.add(f"{kind}:{_normalize(str(raw))}")
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
