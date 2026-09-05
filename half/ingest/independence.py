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

For mail the identity members are the thread, the **origin** — who sent it —
and the content digest, so a long reply chain collapses by thread, a shop
mailing you eight times collapses by origin, and a byte-identical repeat
collapses by content.

**The origin axis is why this is corroboration rather than counting.** Without
it two messages from one sender in two threads are two independent supports,
CAP-3's bar is two, and a shop's newsletter corroborates itself. It was in
claude-obsidian's ledger, in the extraction manifest, and in story 3's own
frozen block — *"union-find over origin, content hash, and declared key"* — and
the first implementation substituted the thread for it. Story 17 restored it;
the thread stayed, because ten strangers in one conversation are still one
support and only the thread says so.

**A missing origin is not an identity.** ``identity_set`` skips an absent or
blank value on every axis, and on this axis that skip is load-bearing: were an
empty sender an identity, every source without one would union into a single
group, Half would find one support everywhere, admit nothing, and go quiet —
which reads as restraint and is an outage.
"""

from __future__ import annotations

import unicodedata
from collections.abc import Iterable, Mapping
from typing import Any


#: What makes two sources the same evidence.
#:
#: The three axes the manifest and story 3 both name — origin, content, declared
#: — plus the thread, which is mail's own and is what makes a reply chain one
#: support. Collapsing on origin *is* transitive, and that is the rule rather
#: than a side effect: one sender's mail is one source however many threads it
#: arrives in, exactly as one thread is one source however many people speak in
#: it. Nothing is derived from an address here — no domain, no plus-address, no
#: display name. The value is the sender as the receipt carries it, under
#: ``_normalize`` and nothing else.
IDENTITY_FIELDS: tuple[tuple[str, str], ...] = (
    ("thread_id", "thread"),
    ("sender", "origin"),
    ("digest", "content"),
    ("independence_key", "declared"),
)


#: The axis this story restored, as the pair it must appear as. Kept apart from
#: ``names_the_origin`` so the guard and the case cannot drift into two
#: different ideas of what "the origin axis" is.
ORIGIN_AXIS: tuple[str, str] = ("sender", "origin")


def names_the_origin(fields: Iterable[tuple[str, str]]) -> bool:
    """Whether these axes include the origin, under the name it is read by.

    A predicate rather than a comment, read by ``_check_axes`` below and by the
    case that asserts it, because *"origin is an identity axis"* was true of
    the specification, the manifest and story 3's frozen block for eleven
    stories while being false of the code.

    Both halves matter. The **key** is what ``identity_set`` looks up in a
    source, so a wrong one reads nothing and the axis is silently absent; the
    **kind** is the namespace an address is compared in, so a wrong one puts
    senders and thread ids in the same space and a thread called ``a@x``
    collapses a stranger's mail into it.
    """
    return ORIGIN_AXIS in tuple(fields)


def an_identity(raw: object) -> bool:
    """Whether this value can make two sources the same evidence.

    **The empty-origin rule, as a predicate the runtime and the cases share.**
    ``None``, ``""`` and whitespace are not identities. This is the single most
    dangerous line in the module: were a blank sender an identity, every source
    without one would carry the handle ``origin:`` and union into one group —
    Half would find one support everywhere, admit nothing, and go quiet, which
    reads as restraint and is an outage.

    Coerced rather than type-checked, so a provider handing back an integer
    thread id is still an identity; ``0`` is a real thread id and ``str(0)``
    does not strip to empty.
    """
    return raw is not None and bool(str(raw).strip())


def _check_axes() -> None:
    """Import-time invariants, as raises rather than bare ``assert``.

    A guarantee ``python -O`` removes is not a guarantee. Deleting the origin
    axis is a one-line edit that leaves every other case in the suite green and
    every count in the product quietly too high, so the module refuses to
    import without it rather than waiting to be caught by a count.
    """
    if not names_the_origin(IDENTITY_FIELDS):
        raise ValueError(
            "the identity axes do not name the origin. Two messages from one "
            "sender in two threads are then two independent supports, CAP-3 "
            "admits at two, and a shop's newsletter corroborates itself — "
            f"which is the defect story 17 closed. Expected {ORIGIN_AXIS!r} "
            f"among {IDENTITY_FIELDS!r}"
        )
    kinds = [kind for _, kind in IDENTITY_FIELDS]
    if len(set(kinds)) != len(kinds):
        raise ValueError(
            f"two identity axes share a namespace in {IDENTITY_FIELDS!r}. The "
            "namespace is the whole reason a thread id cannot collide with an "
            "address, and two axes sharing one deletes that"
        )
    keys = [key for key, _ in IDENTITY_FIELDS]
    if len(set(keys)) != len(keys):
        raise ValueError(
            f"two identity axes read the same field in {IDENTITY_FIELDS!r}; "
            "one of them is an axis that can never disagree with the other"
        )


def _normalize(value: str) -> str:
    """Casefold under NFC so two spellings of one identity match."""
    return unicodedata.normalize("NFC", value.strip()).casefold()


def identity_set(source_id: str, source: Mapping[str, Any]) -> set[str]:
    """Every handle by which this source might be the same as another.

    Namespaced by kind so a thread id can never collide with a digest, and so
    an address can never collide with either.

    **An absent or blank value is skipped on every axis**, which on the origin
    axis is the difference between a fix and an outage: a mailbox where nothing
    carries a sender would otherwise be one group, one support and no claim at
    all. The skip is the same one line for all four axes on purpose — a second
    rule for the origin is a second thing that can be got wrong.
    """
    if not str(source_id).strip():
        raise ValueError("source_id is required; an empty id unions everything")
    values = {f"source:{_normalize(str(source_id))}"}
    for key, kind in IDENTITY_FIELDS:
        raw = source.get(key)
        if an_identity(raw):
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


_check_axes()
