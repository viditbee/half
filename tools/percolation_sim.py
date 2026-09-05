"""Why the origin is a second level and not a fourth axis of the union-find.

Story 17 restored the origin axis that story 3 lost. The first version added it
to the identity table (then `IDENTITY_FIELDS`, now `SAME_MOMENT_FIELDS`)
alongside the thread, which is what both upstream sources
say — and it shipped an outage, because **union-find is transitive across
axes**: A shares a thread with B, B shares a sender with C, so A, B and C are
one group. Above a low density of overlap that percolates into a single giant
component, every mailbox counts as one support, the CAP-3 gate never opens, and
Half says nothing at all. That failure does not look like a bug. It looks like
a careful product with nothing to report.

**The small cases cannot see it.** Every shape in story 17's frozen matrix, and
every shape in `mailbox_sim.py`, is two to thirty hand-built sources, and the
flat union-find gets all of them right. So does the hierarchy. The two rules
only disagree at a size no hand-built fixture reaches, which is why this file
exists and why it sweeps rather than asserting: a table of eight rows is the
argument, and one row of it is the reason the shipped rule is shaped as it is.

Nothing here is a test. It measures, prints, and returns nothing to anybody.
"""
from __future__ import annotations

import random
import sys
from collections.abc import Mapping
from typing import Any

sys.path.insert(0, ".")

from half.ingest.independence import (
    ORIGIN_AXIS,
    ORIGIN_KIND,
    SAME_MOMENT_FIELDS,
    _normalize,
    an_identity,
    independent_groups,
    one_voice,
    origin_of,
    voices,
)

#: Story 17's first version, kept here verbatim as the rule it was — one flat
#: identity set with the origin among the axes, unioned transitively. It is the
#: thing being measured against, so it is spelled out rather than described.
FLAT_FIELDS: tuple[tuple[str, str], ...] = (*SAME_MOMENT_FIELDS, ORIGIN_AXIS)


def flat_union_find(supporting: list[tuple[str, Mapping[str, Any]]]) -> int:
    """The rule that shipped for one commit: origin as a fourth union axis."""
    if not supporting:
        return 0
    parents = list(range(len(supporting)))

    def find(index: int) -> int:
        while parents[index] != index:
            parents[index] = parents[parents[index]]
            index = parents[index]
        return index

    def union(left: int, right: int) -> None:
        left_root, right_root = find(left), find(right)
        if left_root != right_root:
            parents[right_root] = left_root

    seen: dict[str, int] = {}
    for index, (source_id, source) in enumerate(supporting):
        values = {f"source:{_normalize(str(source_id))}"}
        for key, kind in FLAT_FIELDS:
            raw = source.get(key)
            if an_identity(raw):
                values.add(f"{kind}:{_normalize(str(raw))}")
        for value in values:
            first = seen.setdefault(value, index)
            if first != index:
                union(first, index)
    return len({find(index) for index in range(len(supporting))})


# ── the mailboxes ─────────────────────────────────────────────────────────────

def a_mailbox(msgs: int, people: int, threads: int, *, seed: int = 17):
    """A mailbox with realistic overlap: people appear in more than one thread.

    Deliberately the *simplest* generator that produces the overlap, so nobody
    can say the collapse is an artefact of an elaborate one. Every message has
    its own content digest, which is the friendliest case for both rules: the
    content axis unions nothing here, so every group either rule finds comes
    from the thread and the sender alone.
    """
    r = random.Random(seed)
    return [
        (f"m{i}", {"thread_id": f"t{r.randrange(threads)}",
                   "sender": f"p{r.randrange(people)}@x",
                   "digest": f"d{i}"})
        for i in range(msgs)
    ]


#: Story 17's frozen matrix, as the union-find sees it. Every one of these is
#: small, and that is the point of printing them.
def matrix_shapes() -> list[tuple[str, list, int]]:
    def s(sid, thread, sender, dgst, declared=None):
        data = {"thread_id": thread, "digest": dgst}
        if sender is not None:
            data["sender"] = sender
        if declared:
            data["independence_key"] = declared
        return (sid, data)

    return [
        ("a newsletter — 1 sender, 8 threads",
         [s(f"n{k}", f"t{k}", "deals@shop.example", f"d{k}") for k in range(8)],
         1),
        ("two businesses — 2 senders, 2 threads",
         [s("a", "t1", "booking@air.example", "d1"),
          s("b", "t2", "stay@hotel.example", "d2")], 2),
        ("one thread — 10 senders",
         [s(f"c{k}", "t_convo", f"p{k}@x", f"d{k}") for k in range(10)], 1),
        ("one sender, one thread — a reply chain",
         [s(f"r{k}", "t1", "me@work.example", f"d{k}") for k in range(4)], 1),
        ("address spelling — A@X.com and a@x.com",
         [s("a", "t1", "A@X.com", "d1"), s("b", "t2", "a@x.com", "d2")], 1),
        ("no sender — eight blanks",
         [s(f"u{k}", f"t{k}", "", f"d{k}") for k in range(8)], 8),
        ("a real forward — new thread, new digest",
         [s("sub", "t_sub", "billing@svc.example", "d_sub"),
          s("fwd", "t_fwd", "asst@work.example", "d_fwd")], 2),
        ("a byte-identical forward — one digest",
         [s("a", "t1", "x@x", "SAME"), s("b", "t2", "y@y", "SAME")], 1),
        ("a declared key — nothing else shared",
         [s("a", "t1", "x@x", "d1", "acme"),
          s("b", "t2", "y@y", "d2", "acme")], 1),
    ]


def levels_without_absorption(supporting) -> int:
    """**Also rejected**, and rejected on this table rather than on taste.

    The two levels with the third clause left out: every conversation stands for
    itself, whether or not the people in it have already written to you
    separately. It cannot percolate — so it fixes the outage — and it gets every
    shape in the frozen matrix right.

    What it gets wrong is the other direction. Five hundred messages from **ten
    people** count as one hundred and forty-two independent supports, because
    every thread two of those ten happened to share becomes a support of its
    own on top of their ten origins. Fourteen times too many, and over-counting
    is what CAP-3 exists to prevent: it is thin evidence admitted, which is the
    defect story 17 opened with. Both failures are invisible at the size of a
    hand-built fixture, which is the lesson of the first table.
    """
    items = list(supporting)
    if not items:
        return 0
    groups = voices(items)
    speakers = [
        one_voice(origin_of(items[i][1]) for i in members) for members in groups
    ]
    answers = {f"{ORIGIN_KIND}:{s}" for s in speakers if s is not None}
    for position, speaker in enumerate(speakers):
        if speaker is None:
            answers.add(f"voice:{position}")
    return len(answers)


# ── the report ────────────────────────────────────────────────────────────────

SWEEP = [
    (50, 40, 45), (100, 50, 80), (200, 60, 120), (300, 60, 150),
    (500, 80, 200), (500, 20, 200), (500, 10, 400), (1000, 100, 400),
]


def main() -> None:
    print("\n  Story 17's frozen matrix — where all three rules agree\n")
    print(f"  {'shape':<42}{'truth':>6}{'flat':>7}{'levels':>8}{'no-3rd':>9}")
    print("  " + "─" * 65)
    disagreements = 0
    for name, sources, truth in matrix_shapes():
        flat, levels = flat_union_find(sources), independent_groups(sources)
        absorbed = levels_without_absorption(sources)
        disagreements += len({flat, levels, absorbed}) > 1
        mark = "" if levels == truth else "   <- WRONG"
        print(f"  {name:<42}{truth:>6}{flat:>7}{levels:>8}{absorbed:>9}{mark}")
    print("  " + "─" * 65)
    print(f"  the three rules disagree on {disagreements} of "
          f"{len(matrix_shapes())} hand-built shapes — which is why no fixture "
          f"of this\n  size could have caught what the sweep below shows.\n")

    print("\n  A realistic mailbox — where they do not\n")
    print(f"  {'msgs':>6}{'people':>8}{'threads':>9}{'flat':>7}{'levels':>8}"
          f"{'no-3rd':>9}   verdict")
    print("  " + "─" * 65)
    for msgs, people, threads in SWEEP:
        mail = a_mailbox(msgs, people, threads)
        flat, levels = flat_union_find(mail), independent_groups(mail)
        absorbed = levels_without_absorption(mail)
        # A mailbox from this many separate people is not one piece of
        # evidence. Below the admission floor of two it is worse than wrong:
        # it is silent.
        verdict = ("COLLAPSED — the gate never opens" if flat < 2
                   else "flat rule degrading" if flat < people // 4
                   else "")
        print(f"  {msgs:>6}{people:>8}{threads:>9}{flat:>7}{levels:>8}"
              f"{absorbed:>9}   {verdict}")
    print("  " + "─" * 65)
    print("  flat   = the origin as a fourth union-find axis (story 17, first "
          "version)")
    print("  levels = same-moment union-find, then one origin per voice "
          "(shipped)")
    print("  no-3rd = the same two levels WITHOUT the third clause "
          "(rejected): every\n           conversation stands for itself. No "
          "percolation, and every frozen\n           matrix row right — but "
          "500 messages from 10 people count as 142.")
    print("\n  The flat rule collapses because union-find is transitive "
          "*across* axes:\n  one sender in two threads links those threads, and "
          "a mailbox is one component.\n  The second level is a map from voice "
          "to one handle, so nothing chains.\n")


if __name__ == "__main__":
    main()
