"""Union-find corroboration: ten mentions in one thread is one support, and
one sender in eight threads is one support.

**Read the helper before the cases.** Until story 17 this file's ``source()``
took a ``sender``, stored it in the fixture dict, and ``identity_set`` never
looked at it. Every case here *read* as though it exercised an origin axis and
none of them did: the one named *a forward from another sender* varied the
sender across two messages and passed because of the **content**; the one that
built thirty messages from one address passed because there was no axis to
collapse them. A fixture that supplies a field the implementation ignores is
worse than no fixture, because it tells the next reader the axis is covered.

So two rules hold here now, and they are the point of the file:

* ``source()`` **requires** a sender. A case cannot get one by default, and
  therefore cannot collapse by origin without saying that it meant to.
* every case that names an origin asserts ``without_origin`` — what the same
  sources would count to with the axis gone. A case whose two numbers are
  equal is not evidence for the axis, and it says which axis it *is* evidence
  for instead.
"""

from __future__ import annotations

import pytest

from half.ingest.independence import (
    IDENTITY_FIELDS,
    ORIGIN_AXIS,
    _check_axes,
    an_identity,
    identity_set,
    independent_groups,
    names_the_origin,
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

    The axis is removed by dropping the field ``IDENTITY_FIELDS`` reads rather
    than by patching the table, so nothing here mutates module state and a case
    can hold both numbers at once. It models the mutation that matters — the
    axis absent — and not every possible one; a *renamed* axis is caught by
    ``names_the_origin`` and its own guard cases below.
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


@pytest.mark.cap3_axes
def test_ten_senders_across_ten_threads_at_scale_stay_ten_supports():
    """**The anti-outage half, at the same size.** The failure mode of a
    collapsing fix is that everything collapses, Half finds one support
    everywhere, admits nothing and goes quiet — which looks like restraint.

    Thirty messages, ten threads, ten senders, one sender per thread. Nothing
    is shared across a thread boundary, so nothing crosses one.
    """
    mailbox = [
        source(f"s{i}", thread=f"t{i // 3}", sender=f"p{i // 3}@acme.test",
               dgst=f"d{i}")
        for i in range(30)
    ]
    assert independent_groups(mailbox) == 10
    assert without_origin(mailbox) == 10


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
    left = {v for v in identity_set(*two[0]) if v.startswith("origin:")}
    right = {v for v in identity_set(*two[1]) if v.startswith("origin:")}
    assert left and right and not (left & right)


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
    assert "origin:" not in identity_set("s1", {"sender": "", "digest": "d1"})
    assert "origin:a@x" in identity_set("s1", {"sender": "A@X", "digest": "d1"})


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
def test_identity_values_carry_their_kind():
    values = identity_set("s1", {"thread_id": "t1", "sender": "a@x",
                                 "digest": "d1"})
    assert "thread:t1" in values
    assert "origin:a@x" in values
    assert "content:d1" in values


# ═════════════════════════════════════════════════════════════════════════════
# the guard, and its bypass cases
# ═════════════════════════════════════════════════════════════════════════════


@pytest.mark.cap3_axes
def test_the_shipped_axes_name_the_origin_and_the_module_accepts_them():
    """The other half a bypass case needs: the predicate is true of the shipped
    constant, and ``_check_axes`` passes on it. A guard that is red everywhere
    is not a guard."""
    assert ORIGIN_AXIS in IDENTITY_FIELDS
    assert names_the_origin(IDENTITY_FIELDS) is True
    _check_axes()
    assert [kind for _, kind in IDENTITY_FIELDS] == [
        "thread", "origin", "content", "declared"
    ]


@pytest.mark.cap3_axes
@pytest.mark.parametrize("axes, why", [
    ((("thread_id", "thread"), ("digest", "content"),
      ("independence_key", "declared")), "the axis simply deleted"),
    ((("thread_id", "thread"), ("sender", "thread"),
      ("digest", "content")), "the right field in the wrong namespace"),
    ((("from", "origin"), ("digest", "content")), "the right namespace, a "
     "field no receipt carries"),
    ((), "no axes at all"),
])
def test_the_predicate_refuses_axes_that_do_not_name_the_origin(axes, why):
    """**The bypass case.** ``names_the_origin`` is asked directly about tables
    that are not the shipped one, so a mutation of the predicate is red *by
    name here* and not only red across the whole suite at once.

    Every row is a real way the axis could go missing again, and the middle two
    are the ones a count-based check would never see: a ``sender`` filed under
    the thread namespace reads as an axis and collapses a stranger's mail into
    a thread, and an ``origin`` axis reading a field called ``from`` finds
    nothing in any source Half builds.
    """
    assert names_the_origin(axes) is False, why


@pytest.mark.cap3_axes
def test_the_module_refuses_to_import_axes_without_an_origin(monkeypatch):
    """The guard itself, driven. A raise rather than a bare ``assert``, because
    a guarantee ``python -O`` removes is not a guarantee — and the message
    names the axis, so a build that trips it says what is missing rather than
    that something is wrong."""
    monkeypatch.setattr(
        "half.ingest.independence.IDENTITY_FIELDS",
        (("thread_id", "thread"), ("digest", "content")),
    )
    with pytest.raises(ValueError) as raised:
        _check_axes()
    assert "origin" in str(raised.value)


@pytest.mark.cap3_axes
@pytest.mark.parametrize("axes, expected", [
    ((("thread_id", "thread"), ("sender", "origin"), ("digest", "thread")),
     "namespace"),
    ((("thread_id", "thread"), ("sender", "origin"), ("sender", "content")),
     "same field"),
])
def test_the_module_refuses_axes_that_collide(axes, expected, monkeypatch):
    """Two axes in one namespace deletes the namespacing that keeps an address
    from matching a thread id; two axes on one field is an axis that can never
    disagree with the other. Both are how a later edit adds an axis and
    silently removes one."""
    monkeypatch.setattr("half.ingest.independence.IDENTITY_FIELDS", axes)
    with pytest.raises(ValueError) as raised:
        _check_axes()
    assert expected in str(raised.value)
