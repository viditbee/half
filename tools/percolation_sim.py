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

from tests.mailshapes import (
    DISCLAIMER,
    FOOTER_LINE,
    REJECTED_FLOOR,
    under_a_footer,
)

from half.derive.particular import MAX_SOURCES
from half.ingest import echo
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


#: The legal footer and the note that carries it are ``tests/mailshapes.py``'s,
#: imported rather than copied. They were duplicated verbatim here and in
#: ``tests/test_echo.py``, which is the confound the shipped rule was chosen
#: over living in two places: an edit to one copy that did not reach the other
#: would leave the suite and this sweep measuring two different mailboxes and
#: agreeing with each other about the answer.
def with_a_disclaimer(i: int, day: int) -> str:
    """One ordinary note with the company footer stapled to the end of it."""
    return under_a_footer(i, day)


#: Story 18's fractional first version, kept here as the rule it was, for the
#: reason ``FLAT_FIELDS`` keeps story 17's: it is the thing being measured
#: against. It scored *the fraction of the smaller body's vocabulary present in
#: the larger* and fired at 0.98. Every true positive it was chosen on sits at
#: exactly 1.00 and the nearest hand-built confound at 0.93, so two points looked
#: like room. The sweep below is what disagreed.
#:
#: The value is ``tests.mailshapes.REJECTED_FLOOR``, imported rather than
#: written again: the same number is quoted in ``half/ingest/echo.py``'s
#: docstring and asserted in ``tests/test_echo.py``, and it is the whole
#: argument for the shipped rule, so three copies is three places to drift.
FRACTIONAL_FLOOR = REJECTED_FLOOR


def fractional(mine: frozenset[str], theirs: frozenset[str]) -> bool:
    """The rejected rule: containment as a fraction, above a floor."""
    if not mine or not theirs:
        return False
    inner, outer = (mine, theirs) if len(mine) <= len(theirs) else (theirs, mine)
    return len(inner & outer) / len(inner) >= FRACTIONAL_FLOOR


def total_set(mine: frozenset[str], theirs: frozenset[str]) -> bool:
    """**The third rejected rule**: the same fraction with the floor at 1.00.

    Total containment of the smaller body's *vocabulary* rather than of its
    sequence. It is here because ``half/ingest/echo.py`` cited a number for it
    and nothing in the tree produced that number — a cited measurement nothing
    measures is exactly the shape story 17's percolation was hiding in. Now it
    is a column, and the docstring quotes what this prints.
    """
    if not mine or not theirs:
        return False
    return mine <= theirs or theirs <= mine


def a_mailbox_with_a_disclaimer(msgs: int, people: int, threads: int,
                                *, seed: int = 18, rule: str = "sequence",
                                window: int | None = MAX_SOURCES,
                                footer_only_at: int | None = None,
                                footer: str = DISCLAIMER):
    """The same mailbox, with story 18's declared key live on every message.

    **The anti-outage measurement, and it belongs in the sweep for the reason
    the origin's does.** Story 17 argued the sender belonged in the union-find
    and every hand-built fixture agreed; the sweep is what disagreed. Story 18
    adds a *content* axis to the same union-find, and the argument for it —
    containment chains only with itself, so a chain of containments is a genuine
    chain of derivation — is exactly the kind of argument that was wrong last
    time. So it is measured rather than trusted.

    Every message here carries one long shared legal footer, which is the densest
    realistic overlap a real mailbox has, and every message is otherwise
    unrelated to every other. The truth is therefore ``msgs`` voices, and any
    number below that is the rule collapsing strangers.

    ``window`` is how many earlier bodies each arriving one is compared against.
    ``MAX_SOURCES`` is the *size* ``Run.hold`` bounds the product to and ``None``
    is every earlier message, which is a hundred times more comparison than Half
    ever pays for.

    **It is not, and no longer claims to be, exactly what ``Run.hold`` does.**
    ``hold`` *displaces* at the ceiling — a source bringing independence evicts
    a held one bringing none — and this appends until the window is full and
    then stops. The difference matters and its direction is knowable: a
    displacing window throws held bodies away, so it offers an arriving message
    *fewer* things to adopt and produces more distinct keys. Append-until-full
    is therefore the pessimistic side of the real rule, which is the right side
    for a sweep looking for collapse, and the third ceiling that displacement
    creates is a case in ``tests/test_echo.py`` rather than a column here.

    ``footer_only_at`` inserts the shared block **as a message of its own** at
    that position, which is the shape this sweep could not see at all until a
    review found it: a block contained in two bodies that do not contain each
    other makes those two one voice, and every corporate mailbox has that block
    arriving alone the day the policy changes.
    """
    # Two generators, and that is not fussiness: the bodies must not move the
    # thread and sender draws, or this mailbox would not be the same mailbox
    # `a_mailbox` builds and the two counts below could not be compared.
    r = random.Random(seed)
    days = random.Random(seed + 1)
    mail = []
    held: list[tuple[str, str]] = []
    for i in range(msgs):
        body = (footer if i == footer_only_at
                else under_a_footer(i, days.randrange(28) + 1, footer))
        if rule == "sequence":
            # **The shipped rule is the shipped function, called.** This loop
            # used to spell containment out again over cached units, and the
            # copy had already drifted: it never checked `long_enough` on the
            # *held* body and it never skipped a held body that had declared
            # nothing. `echo.inside` was made public so that a second consumer
            # would not need a second implementation, and a second
            # implementation arrived anyway. There is now one.
            key = echo.declaring(body, held)
        else:
            key = _declaring_by(body, held, BY_FRACTION if rule == "fraction"
                                else BY_SET)
        if window is None or len(held) < window:
            held.append((key, body))
        mail.append((f"m{i}", {"thread_id": f"t{r.randrange(threads)}",
                               "sender": f"p{r.randrange(people)}@x",
                               "digest": f"d{i}",
                               "independence_key": key}))
    return mail


#: The three containment tests, each over one body's ``(units, vocabulary)``.
#: Two rules are rejected and one is the shipped rule's own test, kept here so
#: that ``_declaring_by`` can be run against ``echo.declaring`` and *shown* to
#: agree rather than asserted to.
BY_FRACTION = staticmethod(lambda mine, theirs: fractional(mine[1], theirs[1]))
BY_SET = staticmethod(lambda mine, theirs: total_set(mine[1], theirs[1]))
BY_SEQUENCE = staticmethod(lambda mine, theirs: echo.inside(mine[0], theirs[0]))


def _declaring_by(body: str, held: list[tuple[str, str]], same) -> str:
    """``echo.declaring``'s shape, with the containment test as a parameter.

    **Only the two rejected rules come through here in the sweep.** The shipped
    rule calls ``echo.declaring`` itself, and ``main`` runs this skeleton with
    ``BY_SEQUENCE`` — the shipped test — over the same window and prints whether
    the two agree. A divergence is then a printed answer rather than the silent
    one this file was already carrying.

    The three things it does that the version this replaced did not, each
    because ``declaring`` does: it skips a held body that declared nothing, it
    checks ``long_enough`` on the **held** body as well as on the arriving one,
    and it falls back to the arriving body's own handle only after the whole
    window has been read.
    """
    mine = echo.units(body)
    if not echo.long_enough(mine):
        return ""
    ours = (mine, frozenset(mine))
    for key, text in held:
        if not key:
            continue
        theirs = echo.units(text)
        if not echo.long_enough(theirs):
            continue
        if same(ours, (theirs, frozenset(theirs))):
            return key
    return echo.own_key(body)


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

    print("\n  Story 18's declared key — the same mailbox, one legal footer on\n"
          "  every message, every message otherwise a stranger\n")
    print(f"  {'msgs':>6}{'people':>8}{'threads':>9}{'seq':>6}{'set':>6}"
          f"{'frac':>7}{'levels':>8}   verdict")
    print("  " + "─" * 65)
    for msgs, people, threads in SWEEP:
        mail = a_mailbox_with_a_disclaimer(msgs, people, threads)
        sequence_keys = len({m["independence_key"] for _, m in mail})
        by_set = a_mailbox_with_a_disclaimer(msgs, people, threads, rule="set")
        set_keys = len({m["independence_key"] for _, m in by_set})
        rejected = a_mailbox_with_a_disclaimer(msgs, people, threads,
                                               rule="fraction")
        fraction_keys = len({m["independence_key"] for _, m in rejected})
        levels = independent_groups(mail)
        plain = independent_groups(a_mailbox(msgs, people, threads, seed=18))
        # The key must not cost this mailbox a single support: `plain` is the
        # identical mailbox with no declared key at all, so anything below it is
        # the footer firing. Below two supports the gate never opens, which is
        # the outage rather than restraint.
        verdict = ("COLLAPSED — the gate never opens" if levels < 2
                   else f"the footer cost {plain - levels} supports"
                   if levels < plain else "")
        print(f"  {msgs:>6}{people:>8}{threads:>9}{sequence_keys:>6}"
              f"{set_keys:>6}{fraction_keys:>7}{levels:>8}   {verdict}")
    print("  " + "─" * 65)
    print("  seq    = distinct declared keys under the shipped rule — the "
          "smaller body's\n           whole term sequence inside the larger. "
          "One per message is the rule\n           declining to collapse "
          "anything, which is what strangers must produce.")
    print("  set    = the second rejected rule: total containment of the "
          "smaller body's\n           *vocabulary* — the same fraction with the "
          "floor at 1.00. It is a\n           column because "
          "half/ingest/echo.py cited a number for it and nothing\n           "
          "in the tree produced that number. Two notes whose words happen to "
          "be a\n           subset of each other's still collapse.")
    print(f"  frac   = the first rejected version: containment as a *fraction* "
          f"of the\n           smaller body's vocabulary, above a floor of "
          f"{FRACTIONAL_FLOOR}. Every true\n           positive it was chosen on "
          f"is at 1.00 and the nearest hand-built\n           confound at 0.93 — "
          f"and it still collapses a mailbox to a handful of\n           voices, "
          f"because a long shared footer drags unrelated pairs over the\n"
          f"           floor. Two points of air was not air.")
    print("\n  The window is MAX_SOURCES in size. It appends until full where "
          "Run.hold\n  displaces, which is the pessimistic side of the real "
          "rule — a displacing\n  window offers an arriving message fewer "
          "things to adopt. Unbounded, every\n  message against every earlier "
          "one, is the worst case below.\n")

    print("  Unbounded worst case, every pair compared\n")
    print(f"  {'msgs':>6}{'seq':>6}{'set':>6}{'frac':>7}   verdict")
    print("  " + "─" * 65)
    for msgs in (100, 300):
        seq_all = a_mailbox_with_a_disclaimer(msgs, 60, 120, window=None)
        set_all = a_mailbox_with_a_disclaimer(msgs, 60, 120, window=None,
                                              rule="set")
        frac_all = a_mailbox_with_a_disclaimer(msgs, 60, 120, window=None,
                                               rule="fraction")
        seq_keys = len({m["independence_key"] for _, m in seq_all})
        set_keys = len({m["independence_key"] for _, m in set_all})
        frac_keys = len({m["independence_key"] for _, m in frac_all})
        verdict = "" if seq_keys == msgs else "COLLAPSED"
        print(f"  {msgs:>6}{seq_keys:>6}{set_keys:>6}{frac_keys:>7}   {verdict}")
    print("  " + "─" * 65 + "\n")

    print("\n  The shape the sweep above could not see: the shared block "
          "arriving as a\n  message of its own. Truth is one voice per "
          "message in every row.\n")
    print(f"  {'msgs':>6}{'block':>18}{'arrives':>9}{'seq':>6}{'truth':>7}"
          f"   verdict")
    print("  " + "─" * 65)
    for label, block in (("legal footer", DISCLAIMER),
                         ("one-line footer", FOOTER_LINE)):
        for msgs, position in ((31, 0), (31, 5), (7, 0), (7, 3)):
            mail = a_mailbox_with_a_disclaimer(msgs, 60, 120,
                                               footer_only_at=position,
                                               footer=block)
            keys = len({m["independence_key"] for _, m in mail})
            verdict = "" if keys == msgs else "COLLAPSED"
            print(f"  {msgs:>6}{label:>18}{position:>9}{keys:>6}{msgs:>7}"
                  f"   {verdict}")
    print("  " + "─" * 65)
    print("  A block contained in two bodies that do not contain each other "
          "makes those\n  two one voice: both adopt its handle. The damage "
          "stops where the block\n  lands in the arrival order, because what "
          "it can reach is what it was\n  compared against. Four measured "
          "levers were rejected — see echo.py's\n  docstring and "
          "deferred-work.md. The direction is MERGING, so Half\n  under-counts "
          "and admits fewer claims, which is the conservative side.\n")

    # The skeleton the two rejected rules run through must stay the shipped
    # function's shape. Cross-checked rather than asserted in a comment,
    # because a copy of `declaring` living in this file is exactly the drift
    # that made this section necessary.
    probe = [(echo.own_key(under_a_footer(i, i + 1)), under_a_footer(i, i + 1))
             for i in range(MAX_SOURCES)]
    # A stranger, a forward of a held body, a body too short to declare, and a
    # held entry that declared nothing — the four answers `declaring` gives.
    checked = [under_a_footer(99, 3), "FYI\n\n" + under_a_footer(3, 4),
               "Thanks!", DISCLAIMER]
    disagreements = sum(
        _declaring_by(body, [("", "a held body that declared nothing"), *probe],
                      BY_SEQUENCE)
        != echo.declaring(body, [("", "a held body that declared nothing"),
                                 *probe])
        for body in checked
    )
    print(f"  the rejected rules' skeleton, run with the shipped containment "
          f"test,\n  disagrees with echo.declaring on {disagreements} of "
          f"{len(checked)} probes.\n")

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
