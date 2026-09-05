"""Independence-gated corroboration (CAP-3).

Ten mentions of one fact in a single email thread is **one** piece of evidence,
not ten. Without this the belief set inflates with echoes of a single moment,
and "ingestion is unbounded, belief is bounded" fails in the first noisy month
— Half then states things with the full weight of the mirror behind them, on
the strength of one email quoted nine times.

**Two levels, and the reason they are two is measured.**

1. **The same moment.** Union-find over the thread, the content digest and a
   declared key, adapted from claude-obsidian's ledger
   (``_independent_group_count``): each source contributes a *same-moment* set,
   any two sources sharing any of those values are unioned, and each group is
   one **voice**. A long reply chain is one voice by thread; a byte-identical
   repeat is one voice by content; a source that declares what it is the same
   as is one voice by declaration.
2. **Who is speaking.** Each voice then answers to a single origin — the sender
   — if it has exactly one. A shop mailing you eight times is eight voices with
   one origin between them, so it is **one** support. A voice with several
   speakers is a conversation: it stands for itself, *unless* everyone in it has
   already written to you separately, in which case it is those people talking
   and adds nothing. A voice with no readable sender always stands for itself.
   The answer is the number of distinct answers.

**Why the origin is not simply a fourth axis of the union-find, which is what
it was for one commit.** Union-find is transitive *across* axes: A shares a
thread with B, B shares a sender with C, so A, B and C are one group. On a
realistic mailbox that percolates — measured in ``tools/percolation_sim.py``,
which is where this rule was chosen rather than argued — and above a low
density every mailbox becomes a single giant component. The gate then never
opens, Half finds one support everywhere, admits nothing, and goes quiet. That
is not restraint, it is an outage, and it looks exactly like a well-behaved
product with nothing to say. Story 3's implementation left a comment saying so;
story 17 first deleted the comment and reproduced the failure, then measured
it.

Applying the axes at *different levels* cannot percolate, because a voice's
origin never links two voices to a third: the second level is a map from voice
to one handle, and a map has no transitive closure.

**The declared key is a same-moment axis and deliberately not an origin.** It
says *this source is the same evidence as that one*, which is a statement about
the moment rather than about who is speaking — and a source declares it, so at
the second level a single crafted key would merge unrelated voices for free,
which is the percolation again through a field the sender controls.

**A missing origin is not an identity.** ``an_identity`` refuses an absent or
blank value everywhere, and on the origin that refusal is load-bearing: were a
blank sender an origin, every source without one would answer to the same
handle and a mailbox nothing could be parsed out of would count as one support.
"""

from __future__ import annotations

import unicodedata
from collections.abc import Iterable, Mapping
from typing import Any


#: What makes two sources **the same moment**, unioned transitively.
#:
#: The origin is deliberately **not** here, and putting it back is the one edit
#: that turns this module into an outage — see the module docstring and
#: ``_check_axes``. Nothing is derived from any of these values: no domain, no
#: plus-address, no display name, no parsing of any kind. The value is what the
#: receipt carries, under ``_normalize`` and nothing else.
SAME_MOMENT_FIELDS: tuple[tuple[str, str], ...] = (
    ("thread_id", "thread"),
    ("digest", "content"),
    ("independence_key", "declared"),
)

#: The second level, as the pair it must appear as: the field a source carries
#: it in, and the namespace a voice answers under. One tuple rather than two
#: constants so a guard and a case cannot drift into two different ideas of
#: what "the origin" is.
ORIGIN_AXIS: tuple[str, str] = ("sender", "origin")
ORIGIN_FIELD, ORIGIN_KIND = ORIGIN_AXIS


def unions_the_origin(fields: Iterable[tuple[str, str]]) -> bool:
    """Whether this same-moment table would union on the origin.

    **The percolation predicate**, read by ``_check_axes`` and by the cases
    that assert it. True is the outage: the origin unioned alongside the thread
    means A's thread reaches C's mail through B, a realistic mailbox becomes one
    group, and CAP-3's gate never opens again.

    Both halves are checked because either alone reintroduces it. The **key** is
    what ``same_moment_set`` looks up in a source, so ``("sender", "whatever")``
    unions senders under a different name; the **kind** is the namespace, so
    ``("anything", "origin")`` puts a voice's handle into the union-find's own
    value space, where it meets the handles this function exists to keep it away
    from.
    """
    pairs = tuple(fields)
    return any(key == ORIGIN_FIELD or kind == ORIGIN_KIND for key, kind in pairs)


def an_identity(raw: object) -> bool:
    """Whether this value can make two sources the same evidence.

    **The blank rule, as a predicate the runtime and the cases share.** ``None``,
    ``""`` and whitespace are not identities, on either level. On the origin
    that refusal is what stops a mailbox whose ``from`` headers could not be
    read from answering to one handle and counting as one support.

    Coerced rather than type-checked, so a provider handing back an integer
    thread id is still an identity; ``0`` is a real thread id and ``str(0)``
    does not strip to empty.
    """
    return raw is not None and bool(str(raw).strip())


def _normalize(value: str) -> str:
    """Casefold under NFC so two spellings of one identity match."""
    return unicodedata.normalize("NFC", value.strip()).casefold()


def origin_of(source: Mapping[str, Any]) -> str | None:
    """This source's origin, normalised — or ``None`` where it has none.

    The whole of the second level's reading of a source. Nothing is parsed: two
    spellings of one address match because ``_normalize`` casefolds under NFC,
    and for no other reason.
    """
    raw = source.get(ORIGIN_FIELD)
    return _normalize(str(raw)) if an_identity(raw) else None


def one_voice(origins: Iterable[str | None]) -> str | None:
    """The single origin a voice speaks with, or ``None`` if it speaks for itself.

    **The second level, as a predicate.** A voice with exactly one origin is
    that origin wherever else it appears — which is what makes a newsletter one
    support across eight threads. A voice with none (nothing carried a sender)
    or with several (a conversation between people) is its own support, because
    there is no one speaker to attribute it to and inventing one would collapse
    every senderless mailbox into a single group.

    Blanks are dropped rather than counted, so a thread carrying one real sender
    and one unreadable header is still that sender's voice.
    """
    distinct = {origin for origin in origins if an_identity(origin)}
    return next(iter(distinct)) if len(distinct) == 1 else None


def adds_a_voice(origins: Iterable[str | None], spoken: Iterable[str]) -> bool:
    """Whether a conversation is a support of its own, or is already counted.

    **The third clause, and it is here because of a measurement.** Without it,
    five hundred messages from ten people across four hundred threads count as
    *one hundred and forty-two* independent supports: every thread two of those
    ten happened to share becomes its own voice, on top of the ten origins. That
    is over-counting by fourteen times, in the exact direction CAP-3 exists to
    prevent — thin evidence admitted — and it is the mirror of the percolation,
    not a smaller version of it. See ``tools/percolation_sim.py``.

    The rule in one sentence: **a conversation adds nothing when everyone in it
    has already written to you separately.** A thread carrying somebody new is a
    support; a thread of people already counted is the same people talking.

    A voice with no readable origin always counts, because *nothing is known
    about who spoke* is not the same as *everyone here is already counted*, and
    treating it as the latter is how a mailbox with no parseable senders would
    collapse to nothing.

    It cannot chain: ``spoken`` is fixed before any of this is asked, so no
    answer here can change another. That is the whole reason the second level is
    a map and not a union.
    """
    named = {origin for origin in origins if an_identity(origin)}
    return not named or not named <= set(spoken)


def _check_axes() -> None:
    """Import-time invariants, as raises rather than bare ``assert``.

    A guarantee ``python -O`` removes is not a guarantee, and the one this
    module exists to keep — *the origin is read at a second level and never
    unioned into the first* — is a one-line edit away from a product that
    quietly stops saying anything.
    """
    if unions_the_origin(SAME_MOMENT_FIELDS):
        raise ValueError(
            f"the same-moment axes {SAME_MOMENT_FIELDS!r} union on the origin. "
            "Union-find is transitive across axes, so one sender in two threads "
            "links those threads, a handful of such senders link a mailbox, and "
            "above a low density every mailbox is one group — the gate never "
            "opens and Half goes quiet, which looks like restraint and is an "
            "outage. Measured in tools/percolation_sim.py. The origin belongs "
            "to the second level, where a voice answers to one handle and "
            "nothing chains"
        )
    kinds = [kind for _, kind in SAME_MOMENT_FIELDS]
    if len(set(kinds)) != len(kinds):
        raise ValueError(
            f"two same-moment axes share a namespace in {SAME_MOMENT_FIELDS!r}. "
            "The namespace is the whole reason a thread id cannot collide with "
            "a digest, and two axes sharing one deletes that"
        )
    keys = [key for key, _ in SAME_MOMENT_FIELDS]
    if len(set(keys)) != len(keys):
        raise ValueError(
            f"two same-moment axes read the same field in "
            f"{SAME_MOMENT_FIELDS!r}; one of them is an axis that can never "
            "disagree with the other"
        )
    if not all(isinstance(part, str) and part for part in ORIGIN_AXIS):
        raise ValueError(
            f"the origin axis {ORIGIN_AXIS!r} is not a (field, namespace) pair; "
            "a voice would answer to nothing and every newsletter would "
            "corroborate itself again"
        )


def same_moment_set(source_id: str, source: Mapping[str, Any]) -> set[str]:
    """Every handle by which this source might be **the same moment** as another.

    Namespaced by kind so a thread id can never collide with a digest. The
    origin is not among them: it is read by ``origin_of`` at the second level,
    and a handle for it here is the percolation ``_check_axes`` refuses.

    An absent or blank value is skipped, so a source that carries nothing but
    its own id unions with nothing.
    """
    if not str(source_id).strip():
        raise ValueError("source_id is required; an empty id unions everything")
    values = {f"source:{_normalize(str(source_id))}"}
    for key, kind in SAME_MOMENT_FIELDS:
        raw = source.get(key)
        if an_identity(raw):
            values.add(f"{kind}:{_normalize(str(raw))}")
    return values


def voices(
    supporting: Iterable[tuple[str, Mapping[str, Any]]]
) -> list[list[int]]:
    """The first level: sources grouped into voices, as indices into the input.

    Union-find over ``same_moment_set`` and nothing else. Returned rather than
    counted so the second level, the cases and the simulations all read the same
    partition instead of three re-implementations of it.
    """
    items = list(supporting)
    if not items:
        return []

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

    # An index from handle to the first source carrying it, so this is linear
    # in the number of shared handles rather than quadratic in sources.
    seen: dict[str, int] = {}
    for index, (source_id, source) in enumerate(items):
        for value in same_moment_set(source_id, source):
            first = seen.setdefault(value, index)
            if first != index:
                union(first, index)

    grouped: dict[int, list[int]] = {}
    for index in range(len(items)):
        grouped.setdefault(find(index), []).append(index)
    return list(grouped.values())


def independent_groups(
    supporting: Iterable[tuple[str, Mapping[str, Any]]]
) -> int:
    """How many genuinely independent supports these sources represent.

    The two levels, and the second is a **map rather than a union**: each voice
    answers to its single origin if it has one, and otherwise to itself unless
    everyone in it is already counted. Two voices meet only by answering to the
    same handle, and every handle is decided against a set fixed before any of
    them is asked — so nothing chains through a third and no density of overlap
    can collapse a mailbox, which is the failure ``tools/percolation_sim.py``
    exists to keep measured.
    """
    items = list(supporting)
    if not items:
        return 0

    groups = voices(items)
    origins = [
        [origin_of(items[index][1]) for index in members] for members in groups
    ]
    speakers = [one_voice(group) for group in origins]

    # Fixed before anything is decided against it. A speaker discovered later
    # cannot absorb a conversation already counted, and a conversation cannot
    # ever make somebody a speaker — either would be a chain, and a chain is
    # what percolates.
    spoken = {speaker for speaker in speakers if speaker is not None}

    # Namespaced apart, so a voice standing for itself can never answer to the
    # same handle as a voice speaking with an origin.
    answers = {f"{ORIGIN_KIND}:{speaker}" for speaker in spoken}
    for position, (group, speaker) in enumerate(zip(origins, speakers)):
        if speaker is None and adds_a_voice(group, spoken):
            answers.add(f"voice:{position}")
    return len(answers)


_check_axes()
