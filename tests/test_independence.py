"""Two-level corroboration: ten mentions in one thread is one support, and one
sender in eight threads is one support.

**Read the helpers before the cases.** Until story 17 this file's ``source()``
took a ``sender``, stored it in the fixture dict, and the union-find never
looked at it. Every case here *read* as though it exercised an origin axis and
none of them did: the one named *a forward from another sender* varied the
sender across two messages and passed because of the **content**; the one that
built thirty messages from one address passed because there was no axis to
collapse them. A fixture that supplies a field the implementation ignores is
worse than no fixture, because it tells the next reader the axis is covered.

Story 17's own first version then made the same mistake one level up. It added
the origin as a fourth union-find axis, wrote a case called *ten senders across
ten threads stay ten supports* to prove the result could not over-collapse, and
built that case with **one sender per thread** — so the chaining that causes the
over-collapse could not occur in it. The fixture was unfailable, on the guard
written to prevent exactly the failure it was hiding. That case is now
``test_a_mailbox_dense_enough_to_percolate_does_not_collapse``, and it carries
the rejected rule with it and asserts that rule returns **one** on the same
sources — so the density is demonstrated rather than claimed.

Three rules hold here, and they are the point of the file:

* ``source()`` **requires** a sender. A case cannot get one by default, and
  therefore cannot collapse by origin without saying that it meant to.
* every case that names an origin asserts ``without_origin`` — what the same
  sources would count to with the origin never read. A case whose two numbers
  are equal is not evidence for the origin, and it says which axis it *is*
  evidence for instead.
* any case claiming a rule does not over-collapse must show a shape where
  something **does**, or it is asserting about a mailbox that could not have
  failed.
"""

from __future__ import annotations

import ast
import inspect
from pathlib import Path

import pytest

from half.ingest import independence

from half.ingest.independence import (
    ORIGIN_AXIS,
    ORIGIN_FIELD,
    ORIGIN_KIND,
    SAME_MOMENT_FIELDS,
    _check_axes,
    _normalize,
    adds_a_voice,
    an_identity,
    independent_groups,
    one_voice,
    origin_of,
    same_moment_set,
    unions_the_origin,
    voices,
)

#: Sources whose sender is deliberately not an identity. ``None`` omits the key
#: altogether — a provider that returns no ``from`` header at all — and the
#: strings are the shapes a header can arrive in when it is technically present
#: and says nothing.
NO_ORIGIN = (None, "", "   ", "\t\n")


def source(sid, *, sender, thread="t", dgst=None, declared=None):
    """One source. **``sender`` is required and has no default.**

    ``sender=None`` omits the key, which is a source with no origin at all;
    ``sender=""`` supplies an empty one. Those are two different inputs and the
    empty-origin cases assert both, because a mailbox produces both.
    """
    data = {"thread_id": thread, "digest": dgst or sid}
    if sender is not None:
        data["sender"] = sender
    if declared:
        data["independence_key"] = declared
    return (sid, data)


def without_origin(sources):
    """What these sources would count to with the origin axis deleted.

    The origin is removed by dropping the field ``origin_of`` reads rather than
    by patching the module, so nothing here mutates global state and a case can
    hold both numbers at once. Every voice then stands for itself, which is the
    count the machinery had before story 17. It models the mutation that
    matters — the origin never consulted — and not every possible one; the
    origin *unioned back into the first level* is the opposite mistake and is
    caught by ``unions_the_origin`` and its own guard cases below.
    """
    return independent_groups(
        (sid, {key: value for key, value in src.items() if key != "sender"})
        for sid, src in sources
    )


# ═════════════════════════════════════════════════════════════════════════════
# the origin axis — one sender is one source
# ═════════════════════════════════════════════════════════════════════════════


@pytest.mark.cap3_axes
def test_a_newsletter_from_one_sender_in_eight_threads_is_one_support():
    """**The defect story 17 closed, as its own case.**

    A shop mails you eight times over eight weeks. Eight messages, eight
    threads, eight contents, one sender. A person would call that one source;
    without the origin axis the union-find called it eight, CAP-3 admits at
    two, and the newsletter corroborated itself.
    """
    newsletter = [
        source(f"n{k}", thread=f"t_news_{k}", sender="deals@shop.example",
               dgst=f"d_n{k}")
        for k in range(8)
    ]
    assert independent_groups(newsletter) == 1
    assert without_origin(newsletter) == 8, (
        "the case would be green with the origin axis deleted, which is what "
        "it is here to refuse"
    )


@pytest.mark.cap3_axes
def test_one_sender_across_ten_threads_at_scale_is_one_support():
    """The same rule where it was hidden: thirty messages, ten threads, one
    address.

    **This case is the inverse of the one it replaces.** Until story 17 this
    shape asserted **ten**, under a docstring arguing that unioning on sender
    is transitive and would trend a mailbox to one group. The transitivity is
    real and it is now the rule rather than a side effect — one sender's mail
    is one source however many threads it arrives in, exactly as one thread is
    one source however many people speak in it. What stops it trending to one
    group is that it only ever collapses sources sharing a value, which is the
    case below.
    """
    mailbox = [
        source(f"s{i}", thread=f"t{i // 3}", sender="newsletter@acme.test",
               dgst=f"d{i}")
        for i in range(30)
    ]
    assert independent_groups(mailbox) == 1
    assert without_origin(mailbox) == 10


PEOPLE, SHARED_THREADS = 60, 150


def a_percolating_mailbox():
    """A mailbox dense enough that a flat union-find collapses it to one.

    Sixty people. Each has a thread of their own, and each also shares a thread
    with the next person round a ring — so every thread overlaps two others by a
    participant, and the overlap graph is connected. 360 messages, 210 threads,
    every digest distinct, so nothing here collapses by content.

    **Built to make the failure possible, which is the whole point.** The case
    this replaces used one sender per thread, so no sender ever spanned a thread
    boundary and the chaining that percolates could not happen in it. It would
    have passed on the build that shipped the outage.
    """
    mail = [
        source(f"solo{p}", thread=f"ts{p}", sender=f"p{p}@x", dgst=f"ds{p}")
        for p in range(PEOPLE)
    ]
    for i in range(SHARED_THREADS):
        left, right = i % PEOPLE, (i + 1) % PEOPLE
        mail.append(source(f"c{i}a", thread=f"tc{i}", sender=f"p{left}@x",
                           dgst=f"dca{i}"))
        mail.append(source(f"c{i}b", thread=f"tc{i}", sender=f"p{right}@x",
                           dgst=f"dcb{i}"))
    return mail


def flat_union_find(sources):
    """The rejected rule: the origin as a fourth union-find axis.

    Carried here, in the tests, because a case asserting *the shipped rule does
    not collapse* is worth nothing unless the same sources are shown to collapse
    something. This is the shape of the mistake, kept next to the assertion that
    it was a mistake. ``tools/percolation_sim.py`` measures it across densities.
    """
    items = list(sources)
    parents = list(range(len(items)))

    def find(index):
        while parents[index] != index:
            parents[index] = parents[parents[index]]
            index = parents[index]
        return index

    def union(left, right):
        left_root, right_root = find(left), find(right)
        if left_root != right_root:
            parents[right_root] = left_root

    seen = {}
    for index, (source_id, src) in enumerate(items):
        values = set(same_moment_set(source_id, src))
        raw = src.get(ORIGIN_FIELD)
        if an_identity(raw):
            values.add(f"{ORIGIN_KIND}:{_normalize(str(raw))}")
        for value in values:
            first = seen.setdefault(value, index)
            if first != index:
                union(first, index)
    return len({find(index) for index in range(len(items))})


@pytest.mark.cap3_axes
def test_a_mailbox_dense_enough_to_percolate_does_not_collapse():
    """**The anti-outage case, rebuilt so that it can fail.**

    The failure mode of a collapsing rule is not a wrong claim. It is that Half
    finds one support everywhere, admits nothing, and goes quiet — which reads
    as a careful product with nothing to say. Story 17's first version shipped
    exactly that, and the case written to prevent it was built so the chaining
    could not occur.

    So this case asserts three things in order, and the first two are what make
    the third mean anything:

    * the mailbox really is dense enough — ``flat_union_find``, the rejected
      rule, returns **one** on these very sources, so a shape that cannot
      percolate would fail here rather than pass quietly;
    * one is below CAP-3's floor of two, so under that rule this mailbox admits
      nothing at all, for ever;
    * and the shipped rule returns **sixty**, exactly the number of people who
      wrote — not merely *more than one*, because *more than one* is satisfied
      by two and would hide almost the whole of the collapse.
    """
    mailbox = a_percolating_mailbox()
    assert len(mailbox) == PEOPLE + 2 * SHARED_THREADS

    assert flat_union_find(mailbox) == 1, (
        "the fixture is not dense enough to percolate, so this case cannot "
        "fail and is not evidence — which is exactly what was wrong with the "
        "case it replaces"
    )
    assert independent_groups(mailbox) == PEOPLE, (
        "the count no longer tracks the number of people who wrote"
    )


@pytest.mark.cap3_axes
def test_the_percolating_shape_is_not_a_special_case_of_its_own_size():
    """The same shape without the solo threads — nothing but conversations.

    Still collapses to one under the rejected rule; still does not under the
    shipped one. It is here because the case above could be satisfied by a rule
    that keys on *solo threads existing*, and this one has none: every thread
    has two speakers, and none of them has written alone, so no conversation can
    be absorbed and each stands for itself.
    """
    conversations = [
        entry for entry in a_percolating_mailbox()
        if not entry[0].startswith("solo")
    ]
    assert flat_union_find(conversations) == 1
    assert independent_groups(conversations) == SHARED_THREADS


@pytest.mark.cap3_axes
def test_ten_senders_across_ten_threads_stay_ten_supports():
    """The small anti-outage shape, kept — but no longer asked to carry the
    outage, because it cannot: one sender per thread, so nothing spans a thread
    boundary and there is no chaining for any rule to get wrong.

    It says what it is evidence for, which is that the second level does not
    collapse voices that answer to different origins.
    """
    mailbox = [
        source(f"s{i}", thread=f"t{i // 3}", sender=f"p{i // 3}@acme.test",
               dgst=f"d{i}")
        for i in range(30)
    ]
    assert independent_groups(mailbox) == 10
    assert without_origin(mailbox) == 10
    assert flat_union_find(mailbox) == 10, (
        "even the rejected rule is green here, which is why this case is not "
        "the anti-outage one"
    )


@pytest.mark.cap3_axes
def test_two_spellings_of_one_address_are_one_origin():
    """Matrix: *address spelling*. Two threads, two digests, one address in two
    spellings — so the origin is the only axis that can collapse these, and it
    does it with ``_normalize`` and nothing else.

    No parsing: nothing splits at ``@``, reads a domain, strips a display name
    or drops a plus-address. NFC and casefold are the whole matching rule, and
    this case would still pass if they were the whole matching rule for ever.
    """
    spellings = [
        source("a", thread="t1", sender="A@Example.com", dgst="d1"),
        source("b", thread="t2", sender="a@example.com", dgst="d2"),
    ]
    assert independent_groups(spellings) == 1
    assert without_origin(spellings) == 2


@pytest.mark.cap3_axes
def test_two_unrelated_senders_on_unrelated_threads_are_two_supports():
    """Matrix: *two businesses*. Unchanged by story 17, and the case that says
    the origin axis collapses sources that **share** an origin rather than all
    of them.

    Its two numbers are equal, so it is not evidence that the axis exists — it
    is evidence about what the axis must not do, which is why it also asserts
    that the two origin handles are distinct rather than only that the count is
    two. A mutation normalising every address to one value passes the count
    check by accident of there being two threads; it fails this.
    """
    two = [
        source("a", thread="t1", sender="booking@airline.example", dgst="d1"),
        source("b", thread="t2", sender="stay@hotel.example", dgst="d2"),
    ]
    assert independent_groups(two) == 2
    assert without_origin(two) == 2
    left, right = origin_of(two[0][1]), origin_of(two[1][1])
    assert left and right and left != right
    # And neither address is a same-moment handle at all: the origin is read at
    # the second level, so a mutation moving it back into the first would put
    # `origin:` values into this set and is caught here as well as by the guard.
    assert not any(value.startswith(f"{ORIGIN_KIND}:")
                   for value in same_moment_set(*two[0]))


@pytest.mark.cap3_axes
def test_one_sender_in_one_thread_is_one_support():
    """Matrix: *the ordinary reply chain*. Both axes say one; the answer is one
    and not two, which is what a union rather than a sum means."""
    chain = [
        source(f"r{k}", thread="t_convo", sender="me@work.example",
               dgst=f"d{k}")
        for k in range(4)
    ]
    assert independent_groups(chain) == 1
    assert without_origin(chain) == 1


# ═════════════════════════════════════════════════════════════════════════════
# a missing origin is not an identity — the difference between a fix and an
# outage
# ═════════════════════════════════════════════════════════════════════════════


@pytest.mark.cap3_axes
@pytest.mark.parametrize("blank", NO_ORIGIN)
def test_sources_with_no_origin_union_with_nothing(blank):
    """Matrix: *no sender*. **Be hardest on this one.**

    Eight sources whose sender is absent, empty, or whitespace, on eight
    threads with eight contents. They are eight supports. Were a blank origin
    an identity, all eight would carry the handle ``origin:`` and union into a
    single group — and the symptom would not be a crash. It would be Half
    finding one support everywhere, admitting nothing, and going quiet, which
    reads as restraint and is an outage.

    Parametrised over every shape a missing sender arrives in, because ``None``
    (no header at all) and ``""`` (a header that says nothing) take different
    paths into ``identity_set`` and only one of them was ever exercised.
    """
    senderless = [
        source(f"s{k}", thread=f"t{k}", sender=blank, dgst=f"d{k}")
        for k in range(8)
    ]
    assert independent_groups(senderless) == 8
    assert without_origin(senderless) == 8, (
        "a blank origin must count exactly as the axis being absent does"
    )


@pytest.mark.cap3_axes
def test_a_mailbox_where_only_some_sources_have_an_origin_is_not_emptied():
    """The mixed mailbox, which is the realistic one: a transport that fails to
    parse a ``from`` header on some messages and not others.

    Two real senders, each mailing twice on two threads — two supports — plus
    four senderless messages that are four more. Six, and a run that still
    admits. The failure this refuses is subtler than the one above: the blank
    sources union into one group *and take a real one with them*, so the count
    drops without reaching the obvious zero.
    """
    mixed = [
        source("a1", thread="t1", sender="booking@airline.example", dgst="d1"),
        source("a2", thread="t2", sender="booking@airline.example", dgst="d2"),
        source("h1", thread="t3", sender="stay@hotel.example", dgst="d3"),
        source("h2", thread="t4", sender="stay@hotel.example", dgst="d4"),
        source("u1", thread="t5", sender="", dgst="d5"),
        source("u2", thread="t6", sender=None, dgst="d6"),
        source("u3", thread="t7", sender="  ", dgst="d7"),
        source("u4", thread="t8", sender="\t", dgst="d8"),
    ]
    assert independent_groups(mixed) == 6
    assert without_origin(mixed) == 8


@pytest.mark.cap3_axes
def test_an_identity_is_the_one_rule_and_a_blank_is_never_one():
    """The predicate the runtime reads, read directly. **The bypass case for
    the empty-origin rule**, so a mutation of it is red by name here rather
    than only red everywhere at once in the cases above.

    ``0`` is included deliberately: it is falsy, and a rule written as
    ``if raw:`` rather than ``if an_identity(raw):`` would drop a thread id of
    zero and count one conversation as many.
    """
    for blank in NO_ORIGIN:
        assert an_identity(blank) is False
    for real in ("a@x", " a@x ", 0, 1, "0", "ゼロ"):
        assert an_identity(real) is True
    for blank in NO_ORIGIN:
        assert origin_of({"sender": blank, "digest": "d1"}) is None
    assert origin_of({"sender": "A@X ", "digest": "d1"}) == "a@x"


# ═════════════════════════════════════════════════════════════════════════════
# the other axes — each case says which one it rests on
# ═════════════════════════════════════════════════════════════════════════════


@pytest.mark.cap3_axes
def test_ten_messages_in_one_thread_are_one_support():
    """Without this the belief set inflates with echoes of a single moment.

    **Ten distinct senders**, so the thread is the only axis that can be doing
    this — and ``without_origin`` is one as well, which is this case saying out
    loud that it is not evidence for the origin axis. It was the case that
    looked most like one and never was.
    """
    thread = [source(f"s{i}", thread="t", sender=f"p{i}@x") for i in range(10)]
    assert independent_groups(thread) == 1
    assert without_origin(thread) == 1


@pytest.mark.cap3_axes
def test_a_forward_from_another_sender_collapses_by_content():
    """Two senders, two threads, one digest. **Content is the only axis left**,
    which is what makes this a content case rather than a second thread case.

    A *real* forward is not this: it arrives wrapped in ``Fwd:`` boilerplate,
    so its scrubbed body differs, its digest differs, and no axis collapses it.
    That hole is recorded in ``deferred-work.md`` and is deliberately not
    closed here — a forward from a different person genuinely has a different
    origin, and collapsing it needs content similarity over scrubbed bodies.
    """
    forward = [
        source("a", thread="t1", sender="billing@service.example", dgst="SAME"),
        source("b", thread="t2", sender="assistant@work.example", dgst="SAME"),
    ]
    assert independent_groups(forward) == 1
    assert without_origin(forward) == 1


@pytest.mark.cap3_axes
def test_collapsing_is_transitive():
    """a and b share a digest; b and c share a thread; all three are one — and
    **no two of them share a sender**, so the transitivity being demonstrated
    is the union-find's rather than the origin axis quietly doing all three."""
    chain = [
        source("a", thread="t1", sender="x@x", dgst="SAME"),
        source("b", thread="t2", sender="y@y", dgst="SAME"),
        source("c", thread="t2", sender="z@z", dgst="d3"),
    ]
    assert independent_groups(chain) == 1
    assert without_origin(chain) == 1


@pytest.mark.cap3_axes
def test_a_declared_key_collapses_sources_nothing_else_would():
    """Story 3's axis, and *nothing else would* is now a stronger claim than it
    was: two threads, two digests **and two senders**, so the declared key is
    the only thing these share."""
    declared = [
        source("a", thread="t1", sender="x@x", dgst="d1",
               declared="acme-newsletter"),
        source("b", thread="t2", sender="y@y", dgst="d2",
               declared="acme-newsletter"),
    ]
    assert independent_groups(declared) == 1
    assert without_origin(declared) == 1


@pytest.mark.cap3_axes
def test_a_non_string_identity_still_unions():
    """A provider handing back an integer thread id used to drop the identity
    silently, counting ten messages in one thread as ten supports."""
    assert independent_groups([
        ("a", {"thread_id": 1, "sender": "x@x", "digest": "d1"}),
        ("b", {"thread_id": 1, "sender": "y@y", "digest": "d2"}),
    ]) == 1


@pytest.mark.cap3_axes
def test_an_empty_source_id_is_refused():
    """Two sources sharing the empty 'source:' handle would union."""
    with pytest.raises(ValueError):
        independent_groups([("", {"digest": "d1"}), ("", {"digest": "d2"})])


@pytest.mark.cap3_axes
def test_no_sources_is_no_support():
    assert independent_groups([]) == 0


@pytest.mark.cap3_axes
def test_one_source_is_one_support():
    assert independent_groups([source("a", sender="a@x")]) == 1


@pytest.mark.cap3_axes
def test_identities_are_namespaced_so_kinds_cannot_collide():
    """A thread id must never match a digest, and — new with the origin axis —
    **an address must never match a thread id or a digest** that happens to be
    the same string.

    Not hypothetical: a mailing-list transport can hand back the list address
    as the thread key, and a digest is a hex string an address could be. Three
    sources, each carrying ``SHARED`` on a different axis, must stay three.
    """
    collisions = [
        ("a", {"thread_id": "SHARED", "sender": "x@x", "digest": "d1"}),
        ("b", {"thread_id": "t2", "sender": "SHARED", "digest": "d2"}),
        ("c", {"thread_id": "t3", "sender": "z@z", "digest": "SHARED"}),
    ]
    assert independent_groups(collisions) == 3


@pytest.mark.cap3_axes
def test_spelling_differences_do_not_defeat_collapsing_on_the_thread():
    """The thread's own normalisation, with **two senders**, so the origin axis
    is not what is collapsing these."""
    spellings = [
        source("a", thread="T1", sender="x@x", dgst="d1"),
        source("b", thread="t1 ", sender="y@y", dgst="d2"),
    ]
    assert independent_groups(spellings) == 1
    assert without_origin(spellings) == 1


@pytest.mark.cap3_axes
def test_a_missing_field_is_simply_not_an_identity():
    """Two sources with nothing but a sender each, and the senders differ — so
    the absent thread and the absent digest union nothing."""
    assert independent_groups([
        ("a", {"sender": "x@x"}),
        ("b", {"sender": "y@y"}),
    ]) == 2


@pytest.mark.cap3_axes
def test_same_moment_values_carry_their_kind_and_never_the_origin():
    """Namespaced handles, and the origin is **not among them** — which is the
    difference between the shipped rule and the one that percolated. The origin
    is read separately, by ``origin_of``, and never becomes a value two sources
    can be unioned by."""
    values = same_moment_set("s1", {"thread_id": "t1", "sender": "a@x",
                                    "digest": "d1",
                                    "independence_key": "k1"})
    assert "thread:t1" in values
    assert "content:d1" in values
    assert "declared:k1" in values
    assert "source:s1" in values
    assert not any(value.startswith(f"{ORIGIN_KIND}:") for value in values)
    assert "a@x" not in {value.split(":", 1)[1] for value in values}
    assert origin_of({"sender": "a@x"}) == "a@x"


# ═════════════════════════════════════════════════════════════════════════════
# the guard, and its bypass cases
# ═════════════════════════════════════════════════════════════════════════════


@pytest.mark.cap3_axes
def test_the_shipped_axes_keep_the_origin_out_of_the_union_and_are_accepted():
    """The other half a bypass case needs: the predicate is false of the shipped
    table, and ``_check_axes`` passes on it. A guard that is red everywhere is
    not a guard.

    The shipped same-moment table is the thread, the content and the declared
    key — the three that describe *the same moment* — and the origin is a pair
    of its own, read at the second level. Asserted as the exact list rather than
    as a membership test, so an axis added or removed is red here by name.
    """
    assert unions_the_origin(SAME_MOMENT_FIELDS) is False
    assert [kind for _, kind in SAME_MOMENT_FIELDS] == [
        "thread", "content", "declared"
    ]
    assert ORIGIN_AXIS == (ORIGIN_FIELD, ORIGIN_KIND) == ("sender", "origin")
    _check_axes()


@pytest.mark.cap3_axes
@pytest.mark.parametrize("axes, why", [
    ((("thread_id", "thread"), ("sender", "origin"), ("digest", "content")),
     "the origin put back among the union axes — the outage, verbatim"),
    ((("thread_id", "thread"), ("sender", "whatever")),
     "the same field unioned under another name"),
    ((("from", "origin"), ("digest", "content")),
     "another field unioned into the origin's own namespace"),
])
def test_the_predicate_catches_a_same_moment_table_that_unions_the_origin(
        axes, why):
    """**The bypass case.** ``unions_the_origin`` is asked directly about tables
    that are not the shipped one, so a mutation of the predicate is red *by name
    here* and not only red across the whole suite at once.

    Every row is a real way the percolation comes back, and the last two are the
    ones a membership test on the exact pair would miss: unioning on ``sender``
    under a different namespace still chains sender to thread, and putting some
    other field into the ``origin`` namespace puts a voice's handle back into
    the union-find's value space.
    """
    assert unions_the_origin(axes) is True, why


@pytest.mark.cap3_axes
@pytest.mark.parametrize("axes", [
    (("thread_id", "thread"), ("digest", "content")),
    (("thread_id", "thread"),),
    (),
])
def test_the_predicate_passes_tables_that_leave_the_origin_alone(axes):
    """The other direction, so the predicate is not simply always true — which
    would make every row above green for the wrong reason and the guard
    impossible to satisfy."""
    assert unions_the_origin(axes) is False


@pytest.mark.cap3_axes
def test_the_module_refuses_to_import_a_table_that_unions_the_origin(
        monkeypatch):
    """The guard itself, driven. A raise rather than a bare ``assert``, because
    a guarantee ``python -O`` removes is not a guarantee — and the message names
    the percolation and the tool that measures it, so a build that trips this
    says *why* rather than that something is wrong."""
    monkeypatch.setattr(
        "half.ingest.independence.SAME_MOMENT_FIELDS",
        (("thread_id", "thread"), ("sender", "origin"), ("digest", "content")),
    )
    with pytest.raises(ValueError) as raised:
        _check_axes()
    assert "origin" in str(raised.value)
    assert "percolation_sim" in str(raised.value), (
        "the refusal does not point at the measurement, so the next reader "
        "gets the rule without the reason and undoes it again"
    )


@pytest.mark.cap3_axes
@pytest.mark.parametrize("axes, expected", [
    ((("thread_id", "thread"), ("digest", "thread")), "namespace"),
    ((("thread_id", "thread"), ("thread_id", "content")), "same field"),
])
def test_the_module_refuses_same_moment_axes_that_collide(axes, expected,
                                                          monkeypatch):
    """Two axes in one namespace deletes the namespacing that keeps a thread id
    from matching a digest; two axes on one field is an axis that can never
    disagree with the other. Both are how a later edit adds an axis and silently
    removes one."""
    monkeypatch.setattr("half.ingest.independence.SAME_MOMENT_FIELDS", axes)
    with pytest.raises(ValueError) as raised:
        _check_axes()
    assert expected in str(raised.value)


# ═════════════════════════════════════════════════════════════════════════════
# the second level, as two predicates
# ═════════════════════════════════════════════════════════════════════════════


@pytest.mark.cap3_axes
def test_one_voice_answers_for_a_single_speaker_and_never_for_a_conversation():
    """**The bypass case for the second level.** ``one_voice`` decides whether a
    group of sources speaks with one origin, and it is the whole of what makes a
    newsletter one support and a ten-person thread not somebody's newsletter.

    A conversation answering to one of its participants would be the
    over-collapse from the other side: a stranger's thread absorbed into
    whichever member of it happened to be picked.
    """
    assert one_voice(["a@x"]) == "a@x"
    assert one_voice(["a@x", "a@x", "a@x"]) == "a@x"
    assert one_voice(["a@x", "b@y"]) is None
    assert one_voice([]) is None
    assert one_voice([None, None]) is None
    # A thread carrying one real sender and one header nothing could be read
    # out of is still that sender's voice, rather than a conversation.
    assert one_voice([None, "a@x", ""]) == "a@x"


@pytest.mark.cap3_axes
def test_a_conversation_adds_nothing_when_everyone_in_it_already_spoke():
    """**The bypass case for the third clause**, which is the one that keeps the
    count near the number of people who wrote rather than near the number of
    threads.

    Without it, five hundred messages from ten people count as one hundred and
    forty-two supports — the over-count that is the mirror of the percolation,
    and the direction CAP-3 exists to refuse. Measured in
    ``tools/percolation_sim.py``.

    A voice with nothing readable always adds, because *nothing is known about
    who spoke* is not *everyone here is already counted*, and treating the first
    as the second is how a mailbox with no parseable senders would count as
    nothing at all.
    """
    assert adds_a_voice(["a@x", "b@y"], {"a@x", "b@y"}) is False
    assert adds_a_voice(["a@x", "b@y"], {"a@x"}) is True
    assert adds_a_voice(["a@x", "b@y"], set()) is True
    assert adds_a_voice([None, None], {"a@x", "b@y"}) is True
    assert adds_a_voice([], {"a@x"}) is True
    # Blanks are not speakers, so they neither absorb nor block absorption.
    assert adds_a_voice(["a@x", "", None], {"a@x"}) is False


@pytest.mark.cap3_axes
def test_the_two_levels_are_the_partition_and_the_answer():
    """``voices`` is the first level and nothing else — the origin cannot appear
    in it. Asserted directly, because every behavioural case above reads the two
    levels through one number and could not tell which of them moved."""
    mailbox = [
        source("a", thread="t1", sender="shop@x", dgst="d1"),
        source("b", thread="t1", sender="shop@x", dgst="d2"),
        source("c", thread="t2", sender="shop@x", dgst="d3"),
    ]
    grouped = voices(mailbox)
    assert sorted(len(members) for members in grouped) == [1, 2], (
        "the first level did not group by thread alone; the origin has leaked "
        "into it and a and c are one voice before the second level runs"
    )
    assert independent_groups(mailbox) == 1, "the second level did not run"


def _called_at_import(source: str, name: str) -> int:
    """How many times ``name()`` is called at a module's top level.

    Counted rather than ``any``-ed, so a renamed function is a **dead anchor
    that fails** — zero — rather than a scan that quietly watches nothing.
    """
    tree = ast.parse(source)
    return sum(
        1 for node in tree.body
        if isinstance(node, ast.Expr) and isinstance(node.value, ast.Call)
        and isinstance(node.value.func, ast.Name) and node.value.func.id == name
    )


@pytest.mark.cap3_axes
def test_the_guard_is_actually_run_when_the_module_is_imported():
    """A guard nothing calls is a comment.

    ``_check_axes`` has its own cases above, and every one of them calls it by
    hand — so deleting the call at the bottom of the module leaves all of them
    green and leaves the guard switched off. Found in the module's own syntax
    tree, because that is the only place the difference between *defined* and
    *called at import* is visible.
    """
    module = Path(inspect.getfile(independence)).read_text("utf-8")
    assert _called_at_import(module, "_check_axes") == 1, (
        "half/ingest/independence.py no longer runs its axis guard at import"
    )


@pytest.mark.cap3_axes
def test_the_import_scan_finds_nothing_where_there_is_nothing():
    """**The bypass case for the scan itself**, so a mutation of the finder is
    red by name here rather than turning the case above into a guard that can
    only ever pass. A call inside a function is not a call at import, and a
    call to something else is not this one."""
    assert _called_at_import("def f():\n    _check_axes()\n", "_check_axes") == 0
    assert _called_at_import("_check_something_else()\n", "_check_axes") == 0
    assert _called_at_import("_check_axes()\n", "_check_axes") == 1
