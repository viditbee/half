"""Union-find corroboration: ten mentions in one thread is one support."""

from __future__ import annotations

from half.ingest.independence import identity_set, independent_groups


def source(sid, *, thread="t", sender="a@x", dgst=None, declared=None):
    data = {"thread_id": thread, "sender": sender, "digest": dgst or sid}
    if declared:
        data["independence_key"] = declared
    return (sid, data)


def test_ten_messages_in_one_thread_are_one_support():
    """Without this the belief set inflates with echoes of a single moment."""
    thread = [source(f"s{i}", sender=f"p{i}@x") for i in range(10)]
    assert independent_groups(thread) == 1


def test_a_forward_from_another_sender_collapses_by_content():
    assert independent_groups([
        source("a", thread="t1", sender="x@x", dgst="SAME"),
        source("b", thread="t2", sender="y@y", dgst="SAME"),
    ]) == 1


def test_two_unrelated_senders_on_unrelated_threads_are_two_supports():
    assert independent_groups([
        source("a", thread="t1", sender="x@x", dgst="d1"),
        source("b", thread="t2", sender="y@y", dgst="d2"),
    ]) == 2


def test_collapsing_is_transitive():
    """a and b share a sender; b and c share a thread; all three are one."""
    assert independent_groups([
        source("a", thread="t1", sender="x@x", dgst="d1"),
        source("b", thread="t2", sender="x@x", dgst="d2"),
        source("c", thread="t2", sender="z@z", dgst="d3"),
    ]) == 1


def test_a_declared_key_collapses_sources_nothing_else_would():
    assert independent_groups([
        source("a", thread="t1", sender="x@x", dgst="d1", declared="acme-newsletter"),
        source("b", thread="t2", sender="y@y", dgst="d2", declared="acme-newsletter"),
    ]) == 1


def test_no_sources_is_no_support():
    assert independent_groups([]) == 0


def test_one_source_is_one_support():
    assert independent_groups([source("a")]) == 1


def test_identities_are_namespaced_so_kinds_cannot_collide():
    """A thread id must never match a digest that happens to be the same string."""
    assert independent_groups([
        ("a", {"thread_id": "SHARED", "sender": "x@x", "digest": "d1"}),
        ("b", {"thread_id": "t2", "sender": "y@y", "digest": "SHARED"}),
    ]) == 2


def test_spelling_differences_do_not_defeat_collapsing():
    assert independent_groups([
        source("a", thread="T1", sender="X@Example.com", dgst="d1"),
        source("b", thread="t1 ", sender="x@example.com", dgst="d2"),
    ]) == 1


def test_a_missing_field_is_simply_not_an_identity():
    assert independent_groups([
        ("a", {"sender": "x@x"}),
        ("b", {"sender": "y@y"}),
    ]) == 2


def test_identity_values_carry_their_kind():
    values = identity_set("s1", {"thread_id": "t1", "digest": "d1"})
    assert "thread:t1" in values and "content:d1" in values
