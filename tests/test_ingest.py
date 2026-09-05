"""Ingestion: capture, idempotency, and the byte-level safety property."""

from __future__ import annotations

import asyncio
import base64
import datetime
import quopri
from pathlib import Path

import pytest

from half.errors import ChannelError
from half.ingest.gmail import (
    EMPTY_BEFORE_SEARCH,
    MAX_PAGES,
    MAX_PROBES,
    WINDOW_DAYS,
    GmailRecent,
    GmailSource,
    normalize,
)
from half.ingest.pipeline import Pipeline, Receipt
from half.ingest.port import Draining, MailSource, Message
from half.ingest.scrub import Scrubbed
from half.store.sources import LocalSourceStore, digest
from tests.mailshapes import Cut, Mailbox, Transport, internal_date

SECRET = "".join(("AKIA", "IOSFODNN7EXAMPLE"))
OTP = "your verification code is {}".format("483920")

#: A real binary payload — a PNG header. Two high bytes decode cleanly as
#: latin-1 text, so they prove nothing about failing closed.
BINARY = b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x01\x00" + bytes(range(32)) * 4


class FakeMail:
    """The whole surface the pipeline needs, so tests stay offline."""

    name = "fake"

    def __init__(self, messages, fail_after=None):
        self.messages = messages
        self.fail_after = fail_after

    async def fetch(self, *, since=None):
        for index, message in enumerate(self.messages):
            if self.fail_after is not None and index == self.fail_after:
                raise RuntimeError("provider blew up mid-page")
            if since is None or message.t > since:
                yield message


def message(i, body, *, thread="t1", sender="a@x", subject="s", headers=None):
    return Message(
        external_id=f"m{i}", thread_id=thread, sender=sender, subject=subject,
        body=body if isinstance(body, bytes) else body.encode(),
        t=f"2026-08-{i + 1:02d}T00:00:00Z", headers=headers or {},
    )


@pytest.fixture
def store(tmp_path):
    return LocalSourceStore(tmp_path / "sources")


def run(source, store, *, consumer=None, **kw):
    return asyncio.run(Pipeline(source, store, consumer=consumer).ingest(**kw))


def all_bytes(root: Path) -> bytes:
    return b"".join(p.read_bytes() for p in root.rglob("*") if p.is_file())


# -- receipts, not bodies ----------------------------------------------------

def test_a_message_yields_a_receipt(store):
    result = run(FakeMail([message(0, "lunch at 1pm?")]), store)
    assert len(result.receipts) == 1
    assert store.has(result.receipts[0].digest) or len(store) == 1


def test_no_body_text_ever_reaches_disk(store, tmp_path):
    """AD-13: the body is normalised, scanned, handed on, and discarded."""
    run(FakeMail([message(0, "let's meet on thursday about the farmland")]), store)
    assert b"farmland" not in all_bytes(tmp_path / "sources")


def test_the_consumer_receives_the_scrubbed_body_in_memory(store):
    """Story 15b types this seam with the scrubber's own output rather than
    with ``str``: a consumer may hand what it is given to a model provider, and
    the type is what lets it refuse a body that never went through ``scrub``.
    So the assertion is over ``Scrubbed`` and the text inside it."""
    seen: list[tuple[str, str]] = []

    async def consume(receipt, body):
        assert isinstance(body, Scrubbed)
        seen.append((receipt.external_id, body.text))

    run(FakeMail([message(0, "lunch at 1pm?")]), store, consumer=consume)
    assert seen == [("m0", "lunch at 1pm?")]


def test_re_ingesting_stores_nothing_twice(store):
    mail = FakeMail([message(0, "lunch at 1pm?"), message(1, "swim thursday")])
    run(mail, store)
    second = run(mail, store)
    assert len(store) == 2
    assert second.receipts == [] and second.already_seen == 2


def test_the_cursor_advances_even_when_nothing_is_captured(store):
    """A window of skipped messages must not be re-fetched forever."""
    result = run(FakeMail([message(0, BINARY)]), store)
    assert result.receipts == []
    assert result.cursor == "2026-08-01T00:00:00Z"


def test_a_cursor_resumes_rather_than_replaying(store):
    mail = FakeMail([message(0, "a"), message(1, "b"), message(2, "c")])
    run(mail, store)
    resumed = run(mail, store, since="2026-08-02T00:00:00Z")
    assert [r.external_id for r in resumed.receipts] == []  # already seen
    assert resumed.already_seen == 1


# -- the safety property, verified at the byte level -------------------------

def test_no_secret_byte_reaches_disk_from_a_body(store, tmp_path):
    run(FakeMail([message(0, f"the key is {SECRET} please use it"), message(1, OTP)]), store)
    written = all_bytes(tmp_path / "sources")
    assert SECRET.encode() not in written
    assert b"483920" not in written


def test_no_secret_byte_reaches_disk_from_a_subject(store, tmp_path):
    """The leak three reviewers found: only the body was scrubbed."""
    run(FakeMail([
        message(0, "see subject", subject=f"Reset key {SECRET}"),
        message(1, "see subject", subject=OTP),
    ]), store)
    written = all_bytes(tmp_path / "sources")
    assert SECRET.encode() not in written
    assert b"483920" not in written


def test_no_secret_byte_reaches_disk_from_a_sender(store, tmp_path):
    run(FakeMail([message(0, "hi", sender=f"{SECRET}@x.test")]), store)
    assert SECRET.encode() not in all_bytes(tmp_path / "sources")


@pytest.mark.parametrize("field", ["subject", "sender"])
def test_a_secret_in_any_receipt_field_is_recorded_as_redacted(store, field):
    result = run(FakeMail([message(0, "hi", **{field: f"key {SECRET}"})]), store)
    assert "aws access key id" in result.receipts[0].redactions


def test_every_receipt_field_is_scrubber_output(store, tmp_path):
    """Pins the envelope's shape. Adding a field that bypasses the scrubber
    used to ship with the whole suite green."""
    import dataclasses

    run(FakeMail([message(0, f"body {SECRET}", subject=f"subj {SECRET}",
                          sender=f"{SECRET}@x")]), store)
    written = all_bytes(tmp_path / "sources").decode("utf-8", errors="replace")
    text_fields = {f.name for f in dataclasses.fields(Receipt)} - {"redactions"}
    assert text_fields <= {"digest", "external_id", "thread_id", "sender",
                           "subject", "t"}, "a new receipt field needs a scrub decision"
    assert SECRET not in written


# -- encodings that used to defeat detection ---------------------------------

@pytest.mark.parametrize("name,body,headers", [
    ("quoted-printable",
     quopri.encodestring(SECRET.encode()).replace(b"AMPLE", b"=\nAMPLE"),
     {"content-transfer-encoding": "quoted-printable"}),
    ("base64 transfer", base64.b64encode(SECRET.encode()),
     {"content-transfer-encoding": "base64"}),
    ("utf-16", SECRET.encode("utf-16"), {"content-type": "text/plain; charset=utf-16"}),
    ("latin-1", ("café " + SECRET).encode("latin-1"),
     {"content-type": "text/plain; charset=latin-1"}),
    ("html tags", b"AKIA<b></b>IOSFODNN7EXAMPLE",
     {"content-type": "text/html"}),
])
def test_an_encoded_secret_is_detected_and_never_written(store, tmp_path, name, body, headers):
    run(FakeMail([message(0, body, headers=headers)]), store)
    assert SECRET.encode() not in all_bytes(tmp_path / "sources")


def test_unresolvable_content_is_skipped_rather_than_stored(store):
    result = run(FakeMail([message(0, BINARY)]), store)
    assert result.receipts == [] and result.skipped_unreadable == 1
    assert len(store) == 0


def test_an_oversized_body_fails_closed(store):
    result = run(FakeMail([message(0, b"x" * 300_000)]), store)
    assert result.skipped_unreadable == 1


# -- failure ------------------------------------------------------------------

def test_a_failure_mid_page_leaves_earlier_receipts_valid(store):
    mail = FakeMail([message(0, "a"), message(1, "b"), message(2, "c")], fail_after=2)
    with pytest.raises(RuntimeError):
        run(mail, store)
    assert len(store) == 2


# -- the gmail contract ------------------------------------------------------


def _gmail_raw(body="lunch at 1pm?", mid="m1", at=None):
    return {
        "id": mid, "threadId": "t1",
        "internalDate": at if at is not None else "1755158400000",
        "payload": {
            "mimeType": "multipart/alternative",
            "headers": [{"name": "From", "value": "a@x"},
                        {"name": "Subject", "value": "lunch"}],
            "parts": [{"mimeType": "text/plain",
                       "body": {"data": base64.urlsafe_b64encode(body.encode()).decode()}}],
        },
    }


def test_the_gmail_adapter_drives_as_an_async_iterator():
    """isinstance against a runtime_checkable Protocol only checks attribute
    names — it cannot see an async-generator mismatch."""
    class One:
        async def list_messages(self, *, query, page_token):
            return {"messages": [{"id": "m1"}]}
        async def get_message(self, message_id):
            return _gmail_raw(mid=message_id)

    async def collect():
        return [m async for m in GmailSource(One()).fetch()]

    assert [m.external_id for m in asyncio.run(collect())] == ["m1"]


def test_gmail_normalization_feeds_the_pipeline_unchanged(store):
    normalized = normalize(_gmail_raw())
    assert normalized is not None
    result = run(FakeMail([normalized]), store)
    assert result.receipts[0].thread_id == "t1"
    assert result.receipts[0].sender == "a@x"


def test_gmail_walks_pages_until_exhausted():
    """Every page of a window is listed before any of it is read."""
    mail = FakeGmail({"m1": "2026-08-03", "m2": "2026-08-04"}, page_size=1)

    async def collect():
        return [m async for m in GmailSource(mail).fetch()]

    assert [m.external_id for m in asyncio.run(collect())] == ["m1", "m2"]
    assert len(mail.lists) > 1, "the second page was never asked for"


def test_a_repeating_page_token_is_a_fault_and_not_the_end_of_a_window():
    """The guard, reached — which the case named for it no longer was.

    It used to drive a double answering ``{"messages": [], ...}``, so the walk
    ended at the first list call and the windowed branch where the guard now
    lives was never entered: deleting the guard left the case green. This
    double answers with mail *and* one token for ever, which is the only shape
    that reaches it.

    And it **raises** rather than stopping quietly. A listing that repeats a
    token has not named the oldest page of its window — Gmail lists
    newest-first — so returning what it has and calling the window drained
    steps the cursor over messages no later query can name. That is this
    story's own defect one level down, so it is not expressible.
    """
    mail = FakeGmail(a_month(9), page_size=3, loops=True)

    async def collect():
        return [m async for m in GmailSource(mail).fetch()]

    with pytest.raises(ChannelError):
        asyncio.run(collect())
    assert len(mail.lists) < MAX_PAGES, "the guard let the listing run to its ceiling"


def test_a_window_whose_listing_stops_early_loses_nothing(store):
    """Review's reproduction, kept: the partial listing that used to be drained.

    ``_window_ids`` broke out of its page loop on a repeated token and returned
    the ids it had, with no signal — and the walk then marked that window
    drained. Because the provider lists newest-first, the page that went
    missing was the **oldest** one, so the cursor stepped over the three oldest
    messages of the window and ``after:`` never named them again. Measured on
    the shipped build: nine messages, listing stopped after six, six runs, and
    ``m00``–``m02`` were never ingested.

    Now the listing raises, so the run keeps its receipts, moves no cursor, and
    the next run starts where this one did.
    """
    days = a_month(9)
    mail = FakeGmail(days, page_size=3, loops=True)
    cursor, ingested = None, set()

    for _ in range(6):
        try:
            result = run(GmailSource(mail), store, since=cursor)
        except ChannelError:
            continue
        ingested.update(r.external_id for r in result.receipts)
        cursor = result.cursor

    assert cursor is None, "a partial listing moved the cursor"
    assert not ingested - set(days), "a message arrived that the walk never listed"


def test_a_transport_error_never_carries_the_token():
    class Leaky:
        async def list_messages(self, **kw):
            raise RuntimeError("401 https://gmail/?access_token=LIVE-SECRET")
        async def get_message(self, message_id):
            return {}

    async def collect():
        return [m async for m in GmailSource(Leaky()).fetch()]

    with pytest.raises(ChannelError) as excinfo:
        asyncio.run(collect())
    assert "LIVE-SECRET" not in str(excinfo.value)


def test_a_gmail_message_with_no_readable_part_is_skipped():
    assert normalize({"id": "x", "payload": {"mimeType": "image/png"}}) is None


def test_a_malformed_internal_date_skips_the_message(store):
    """Stamping now() dragged the cursor to the present and skipped every
    genuinely older message forever."""
    assert normalize(_gmail_raw() | {"internalDate": "not-a-number"}) is None


def test_malformed_base64_does_not_abort_the_run():
    raw = _gmail_raw()
    raw["payload"]["parts"][0]["body"]["data"] = "!!!not-base64!!!"
    assert normalize(raw) is None


# ═════════════════════════════════════════════════════════════════════════════
# story 20: the order that was promised — one case per row of the matrix
# ═════════════════════════════════════════════════════════════════════════════

#: The mailbox double lives in ``tests/mailshapes.py`` — the same one the
#: transport suite and ``tools/window_sim.py`` drive, because three copies of a
#: mailbox is three mailboxes that can disagree about what Gmail does.
def FakeGmail(days, *, page_size=100, breaks_on=None, undated=(), loops=False,
              zone_hours=0.0):
    """A transport over a mailbox of ``{id: day}``. Records what it was asked."""
    return Transport(Mailbox(days, page_size=page_size, breaks_on=breaks_on,
                             undated=undated, loops=loops, zone_hours=zone_hours))


def a_month(count=20, *, start="2026-08-01"):
    """``count`` messages, one a day, spanning several windows."""
    first = datetime.date.fromisoformat(start)
    return {
        f"m{i:02d}": (first + datetime.timedelta(days=i)).isoformat()
        for i in range(count)
    }


def walk(source, *, since=None):
    async def collect():
        return [m async for m in source.fetch(since=since)]

    return asyncio.run(collect())


# -- the promise, made true ---------------------------------------------------

def test_a_full_walk_yields_every_message_oldest_first():
    """Matrix: *a full walk*. The promise, against a provider that answers
    newest-first — which is the only shape in which the assertion is about the
    walk rather than about the fixture."""
    days = a_month(20)
    mail = FakeGmail(days, page_size=3)
    got = walk(GmailSource(mail))

    assert [m.external_id for m in got] == sorted(days)
    assert [m.t for m in got] == sorted(m.t for m in got)


def test_the_provider_is_still_asked_newest_first():
    """The fixture's own premise, pinned. If Gmail's list ever answered
    oldest-first every case above would pass against a build that reverses
    nothing, so the double's order is asserted rather than assumed."""
    assert Mailbox(a_month(5)).matching("") == [
        "m04", "m03", "m02", "m01", "m00"
    ]


# -- the defect: what a cut costs ---------------------------------------------

def test_a_walk_cut_mid_window_leaves_the_cursor_where_it_was(store):
    """Matrix: *a walk cut mid-window*. Cursor unmoved; nothing lost.

    The window is a week and the cut lands on day three of it, so there is
    undrained ground inside the window the walk was in. A cursor that moved
    there would put ``after:`` past four messages no later query could name.
    """
    days = a_month(20)
    mail = GmailSource(FakeGmail(days, page_size=5))
    result = run(Cut(mail, after=3), store)

    assert len(result.receipts) == 3, "the cut did not fall mid-window"
    assert result.cursor is None, "a cut mid-window moved the history cursor"
    assert result.read_through == "2026-08-03T08:00:00Z"


def test_a_walk_cut_on_a_window_boundary_keeps_that_window(store):
    """Matrix: *a walk cut on a window boundary*. Progress is kept.

    Seven messages, one a day, is exactly the first window — so the cut lands
    where the walk has finished something, and the cursor may move to the end
    of it and no further.
    """
    mail = GmailSource(FakeGmail(a_month(20), page_size=5))
    result = run(Cut(mail, after=WINDOW_DAYS), store)

    assert len(result.receipts) == WINDOW_DAYS
    assert result.cursor == "2026-08-08T00:00:00Z", (
        "the cursor did not stop at the end of the window that was drained"
    )


def test_a_cut_walk_resumed_repeatedly_ingests_every_message_exactly_once(store):
    """Matrix: *resume*, and the acceptance criterion.

    Run it until it stops making progress and every message is captured once —
    the twenty of twenty the story measured. The re-read of a window that was
    cut costs an ``already_seen`` and nothing else, which is the whole trade:
    a repeat is free because the digest deduplicates it, and a loss is not.
    """
    days = a_month(20)
    mail = GmailSource(FakeGmail(days, page_size=5))
    cursor, ingested, runs = None, [], 0

    while runs < 20:
        runs += 1
        result = run(Cut(mail, after=WINDOW_DAYS), store, since=cursor)
        ingested.extend(r.external_id for r in result.receipts)
        if not result.receipts and result.cursor == cursor:
            break
        cursor = result.cursor

    assert sorted(ingested) == sorted(days), "a message was never ingested"
    assert len(ingested) == len(set(ingested)), "a message was ingested twice"


def test_the_order_is_what_makes_the_repetition_converge(store, tmp_path):
    """The counterexample, recorded rather than described.

    The same real ``Pipeline`` over the same twenty messages, cut after five,
    run until it stops making progress — once yielding oldest-first and once
    newest-first. Both finish at the same cursor. One of them has ingested
    five messages and can never reach the other fifteen, because ``after:``
    will not name them again.

    This is the measurement the story was written from, and it is here so that
    a build which "fixes" the defect by declaring newest-first to be the
    contract fails a case rather than passing a review.
    """
    from half.store.sources import LocalSourceStore

    class Ordered:
        """Yields in a chosen order and stops after ``cut`` messages."""

        name = "ordered"

        def __init__(self, messages, *, oldest_first, cut):
            self.messages = messages
            self.oldest_first = oldest_first
            self.cut = cut

        async def fetch(self, *, since=None):
            due = [m for m in self.messages if since is None or m.t > since]
            due.sort(key=lambda m: m.t, reverse=not self.oldest_first)
            for one in due[:self.cut]:
                yield one

    mail = [message(i, f"body {i}") for i in range(20)]

    def until_it_stops(oldest_first):
        into = LocalSourceStore(tmp_path / f"sources-{oldest_first}")
        source = Ordered(mail, oldest_first=oldest_first, cut=5)
        cursor, captured = None, set()
        for _ in range(20):
            result = run(source, into, since=cursor)
            captured.update(r.external_id for r in result.receipts)
            if not result.receipts and result.cursor == cursor:
                break
            cursor = result.cursor
        return captured, cursor

    forward, forward_cursor = until_it_stops(True)
    backward, backward_cursor = until_it_stops(False)

    assert len(forward) == 20, "oldest-first lost history"
    assert len(backward) == 5, (
        "newest-first ingested more than the newest cut; the counterexample "
        "this case records has stopped being the counterexample"
    )
    assert forward_cursor == backward_cursor == "2026-08-20T00:00:00Z", (
        "the two runs no longer end at the same cursor, which is what made "
        "the loss invisible"
    )


def test_a_provider_failure_mid_window_raises_and_moves_no_cursor(store):
    """Matrix: *a provider failure mid-window*. Story 3's vocabulary, unchanged.

    The failure is raised rather than swallowed, so there is no ``Ingested`` to
    carry a cursor at all — which is the strongest form of *cursor unmoved* —
    and the receipts written before it stay written.
    """
    mail = FakeGmail(a_month(20), page_size=5, breaks_on="m03")
    with pytest.raises(ChannelError):
        run(GmailSource(mail), store)
    assert len(store) == 3, "the receipts written before the failure were lost"


# -- windows that hold nothing, and windows that hold too much ----------------

def test_a_sparse_mailbox_terminates_without_stalling(store):
    """Matrix: *an empty window*. Skipped, and the walk still ends.

    Two messages three years apart is a hundred and fifty empty weeks between
    them. The walk crosses them, ingests both, and stops — a walk that stalled
    on an empty window would never reach the second.
    """
    mail = FakeGmail({"old": "2023-02-01", "new": "2026-02-01"})
    result = run(GmailSource(mail), store)

    assert [r.external_id for r in result.receipts] == ["old", "new"]
    # A step for each of the first few empty windows and one search for the
    # rest of the gap — not one list call per week of the three years.
    assert len(mail.lists) < 2 * MAX_PROBES + 2 * EMPTY_BEFORE_SEARCH + 8, (
        f"the walk spent {len(mail.lists)} requests crossing three empty years"
    )


def test_a_dense_window_is_paged_within_the_window():
    """Matrix: *a very dense window*. More than one page, still oldest first."""
    days = {f"m{i:03d}": "2026-08-03" for i in range(25)}
    mail = FakeGmail(days, page_size=4)
    got = walk(GmailSource(mail))

    assert [m.external_id for m in got] == sorted(days)
    # Twenty-five messages at four to a page is seven pages, and they are all
    # inside one window: the day they all land on.
    assert sum(1 for q in mail.lists if "before:" in q) >= len(days) // 4, (
        "the window never paged"
    )


# -- the cursor's own edges ---------------------------------------------------

@pytest.mark.parametrize("bad", ["yesterday", "2026-8-1", "2026-13-45", "not-iso"])
def test_a_malformed_cursor_is_refused_rather_than_widening_the_window(store, bad):
    """Matrix: *a malformed cursor*. Story 3's error, unchanged.

    ``2026-13-45`` is the one worth having: it has the shape of a date and
    names no day, so a build that checked the shape alone would hand Gmail a
    window whose bounds are the provider's guess.
    """
    with pytest.raises(ChannelError):
        run(GmailSource(FakeGmail(a_month(3))), store, since=bad)


def test_a_message_dated_in_the_future_cannot_strand_the_cursor(store):
    """Matrix: *clock skew*. A future stamp must not end the walk.

    One message stamped six years out, among ordinary mail. Nothing here reads
    a clock, so the only evidence a date is not in the future is that mail
    exists at or after it — and one stamp is evidence nobody corroborated. A
    horizon taken from it would put the cursor in 2032 and every message that
    arrives before then would be skipped for ever, which is precisely the loss
    this story removes, arriving through the door that replaced it.
    """
    days = a_month(12) | {"skewed": "2032-01-01"}
    result = run(GmailSource(FakeGmail(days)), store)

    assert result.cursor is not None
    assert result.cursor < "2027-01-01", (
        f"one future-dated message dragged the cursor to {result.cursor}"
    )
    assert "m00" in {r.external_id for r in result.receipts}, "real mail was skipped"


def test_a_message_with_no_date_is_skipped_and_the_cursor_stays_behind(store):
    """Matrix: *a message with no date*. Skipped, as today.

    It cannot be placed in time, so it cannot move a cursor; what it must not
    do is take the cursor to *now*, which would skip every older message.
    """
    mail = FakeGmail(a_month(3), undated=("m02",))
    result = run(GmailSource(mail), store)

    assert {r.external_id for r in result.receipts} == {"m00", "m01"}
    assert result.cursor is not None and result.cursor <= "2026-08-04T00:00:00Z"


# -- the demonstration, which reads and does not drain ------------------------

def test_the_demonstration_reads_recent_mail_and_moves_no_history_cursor(store):
    """Matrix: *the demonstration*. Recent mail; history cursor unmoved.

    CAP-2 asks what this person has been doing *lately* and is cut at ninety
    seconds. Answering it with the history walk reads the oldest mail in the
    mailbox and — before this story — moved the cursor to whatever the cut
    happened to reach. ``GmailRecent`` reads the newest window and publishes no
    watermark at all, so there is no code path by which it can move one.
    """
    days = a_month(40)                       # nearly six weeks, several windows
    recent = GmailRecent(FakeGmail(days, page_size=5))
    result = run(recent, store)

    read = {r.external_id for r in result.receipts}
    assert read, "the demonstration read nothing"
    assert "m39" in read, "the newest thing the main did was left out"
    # A week of it, and nothing like the six weeks the history walk reads.
    assert read <= set(sorted(days)[-(WINDOW_DAYS + 1):]), (
        "the demonstration read old mail"
    )
    assert result.cursor is None, "a bounded read moved the history cursor"
    assert result.read_through is not None, "it recorded no position of its own"


def test_the_demonstration_leaves_a_history_cursor_exactly_where_it_found_it(store):
    """The same rule from the other side: given a cursor, it gives it back."""
    recent = GmailRecent(FakeGmail(a_month(40), page_size=5))
    result = run(recent, store, since="2026-08-05T00:00:00Z")
    assert result.cursor == "2026-08-05T00:00:00Z"


def test_a_recent_read_and_a_forward_walk_answer_different_questions():
    """Two reads of one mailbox, and they do not overlap by accident."""
    days = a_month(40)
    first = walk(GmailSource(FakeGmail(days, page_size=5)))
    recent = walk(GmailRecent(FakeGmail(days, page_size=5)))

    assert first[0].external_id == "m00", "the history walk did not start oldest"
    assert recent[-1].external_id == "m39", "the recent read missed the newest"
    assert len(recent) < len(first), "the recent read was not bounded"


# -- the query the window becomes ---------------------------------------------

def test_a_window_reaches_the_provider_bounded_at_both_ends():
    """The task the story names: ``_query_for`` bounds a window at both ends.

    **As epoch seconds and not as ``YYYY/MM/DD``.** Gmail's date form is
    evaluated in the mailbox's own timezone while every stamp this walk
    computes from is UTC, so a window built in one and read in the other
    excludes messages the walk then steps past. A timestamp is one instant
    everywhere.

    A second of cushion at each end, because the provider's inclusivity at a
    bound is documented neither way: an overlap costs a digest the pipeline
    already deduplicates, and a gap costs a message no later query names.
    """
    from half.ingest.gmail import _instant, _query_for

    start = _instant("2026-03-04T00:00:00Z")
    end = _instant("2026-03-11T00:00:00Z")
    assert _query_for(start) == "after:1772582399"
    assert _query_for(start, end) == "after:1772582399 before:1773187201"
    assert _query_for(None, end) == "before:1773187201"
    assert _query_for() == "", "no bound at all is the whole mailbox, as before"
    assert _instant("1970-01-01T00:00:00Z") is not None
    assert _query_for(_instant("1970-01-01T00:00:00Z")) == "after:0", (
        "a negative timestamp is not a query"
    )


def test_a_mailbox_in_another_timezone_still_loses_no_boundary_message(store):
    """Matrix: *a full walk*, at the seam a date-shaped bound would open.

    The double evaluates a ``YYYY/MM/DD`` bound at **its own** offset, the way
    Gmail does, and holds messages in the hours a thirteen-hour shift moves
    across a window edge. A walk that sent dates would list a window that did
    not contain them and mark that window drained regardless — the boundary
    message gone, by the exact mechanism this story exists to close. A walk
    that sends instants cannot express the mistake.
    """
    edges = {"m0": "2026-08-01T01:00:00Z", "m1": "2026-08-07T22:00:00Z",
             "m2": "2026-08-08T01:00:00Z", "m3": "2026-08-14T23:30:00Z"}
    mail = FakeGmail(edges, page_size=1, zone_hours=13)
    result = run(GmailSource(mail), store)

    assert {r.external_id for r in result.receipts} == set(edges)
    assert not any("/" in q for q in mail.lists), (
        "a date-shaped bound reached the provider, and a date has a timezone"
    )


def test_a_windowed_walk_asks_for_both_bounds():
    """And the bounds are on the wire, not merely computable."""
    mail = FakeGmail(a_month(20), page_size=5)
    walk(GmailSource(mail))
    windows = [q for q in mail.lists if "after:" in q and "before:" in q]
    assert windows, "no window query was ever made"
    assert all(q.startswith("after:") for q in windows)


# -- the budget wrapper, which must not swallow the watermark ------------------

def test_the_budget_wrapper_carries_the_watermark_of_what_it_wraps():
    """``half.__main__.bounded`` is the shape of CAP-2's budget on a pull.

    A wrapper that swallowed the watermark would leave the pipeline with no
    watermark at all and send it back to the ``max()`` this story removed —
    silently, and with every case above still green, because they drive the
    source directly.

    **And it must be swallowed where a type check can see it.** The first
    version forwarded through ``__getattr__``, which answers a plain attribute
    lookup and is invisible to ``isinstance`` against a protocol — protocols
    resolve members statically. It read correctly, asserted correctly, and was
    not ``Draining`` to the pipeline at all.
    """
    from half.__main__ import bounded

    walking = GmailSource(FakeGmail(a_month(20), page_size=5))
    wrapped = bounded(walking, seconds=30.0)
    walking.drained_through = "2026-08-08T00:00:00Z"
    assert wrapped.drained_through == "2026-08-08T00:00:00Z"
    assert isinstance(wrapped, Draining), (
        "the pipeline asks with isinstance and would not have seen this"
    )

    plain = bounded(FakeMail([message(0, "a")]), seconds=30.0)
    assert not isinstance(plain, Draining), (
        "a wrapper around a source with no watermark must not appear to have one"
    )


def test_the_shipped_walk_is_the_kind_of_source_the_pipeline_looks_for():
    """The misspelling case, and it is the whole of the duck-typing risk.

    ``Pipeline`` asks ``isinstance(source, Draining)``. Rename the attribute in
    ``GmailSource`` and the check answers no, the pipeline falls back to the
    ``max()`` cursor that loses history, and nothing else in the suite notices
    — the fallback is the original defect. This is the case that notices.
    """
    assert isinstance(GmailSource(object()), Draining)
    assert isinstance(GmailRecent(object()), Draining)
    assert not isinstance(FakeMail([]), Draining), (
        "an in-memory source drains what it yields and claims nothing"
    )


def test_a_recent_read_cannot_be_made_to_move_a_cursor():
    """``GmailRecent.drained_through`` is a property, so there is no setter.

    It was a ``Final[None]`` class attribute with a comment claiming no code
    path could set it, which ``Final`` does not enforce at runtime and an
    instance assignment simply ignored.
    """
    recent = GmailRecent(object())
    assert recent.drained_through is None
    with pytest.raises(AttributeError):
        recent.drained_through = "2026-08-08T00:00:00Z"


def test_the_demonstrations_own_wiring_moves_no_history_cursor(store):
    """CAP-2 as it is actually wired: bounded, over the recent read.

    ``half.__main__.onboard`` wraps the source in ``bounded`` and
    ``half.__main__.onboarded`` builds a ``GmailRecent``. Both together are the
    ninety seconds, and together they must leave the history cursor exactly
    where they found it — which is the acceptance criterion, over the two
    objects the shipped path composes rather than over one of them.
    """
    from half.__main__ import bounded

    recent = bounded(GmailRecent(FakeGmail(a_month(40), page_size=5)),
                     seconds=30.0)
    result = run(recent, store, since="2026-08-05T00:00:00Z")

    assert result.receipts, "the demonstration read nothing"
    assert result.cursor == "2026-08-05T00:00:00Z"


# -- where a first walk begins, and where it ends -----------------------------

def test_a_first_walk_finds_where_the_mailbox_begins_rather_than_the_floor(store):
    """A first walk has no cursor, and the floor is fifty years back.

    Stepping a week at a time from ``MAILBOX_FLOOR`` would be correct and would
    spend two and a half thousand list calls on empty weeks before reaching any
    mail — under a caller's deadline, a first pull that reads nothing at all,
    every time. The halving search is what makes the first walk affordable, and
    its cost is bounded by ``MAX_PROBES``.
    """
    mail = FakeGmail({"a": "2019-06-04", "b": "2019-06-05", "c": "2019-06-06",
                      "d": "2019-06-07", "e": "2026-08-01"}, page_size=2)
    result = run(GmailSource(mail), store)

    assert {r.external_id for r in result.receipts} == {"a", "b", "c", "d", "e"}
    # Two searches at most — one for the floor, one for the seven-year gap —
    # and a step for each window in between.
    assert len(mail.lists) <= 2 * MAX_PROBES + 4 * EMPTY_BEFORE_SEARCH + 8, (
        f"the walk spent {len(mail.lists)} list calls crossing two gaps"
    )


def test_the_walk_reaches_the_newest_message_however_old_its_horizon_is(store):
    """The stall this story nearly shipped with, kept as a case.

    The horizon guards against a stamp nothing corroborates, and for a while it
    was also where the walk stopped. On a mailbox whose newest messages are
    years apart that stops the walk short of the newest ones *and* leaves the
    cursor at the same place next run, so those messages are read never — the
    loss this story exists to remove, rebuilt out of the defence against clock
    skew.

    Two numbers, not one: the walk goes to the newest stamp there is, and the
    cursor is clamped to the corroborated one.
    """
    days = {"a": "2019-06-04", "b": "2019-06-05", "c": "2019-06-06",
            "d": "2022-01-10", "e": "2026-08-01"}
    result = run(GmailSource(FakeGmail(days, page_size=2)), store)

    assert {r.external_id for r in result.receipts} == set(days)
    assert result.cursor is not None and result.cursor <= "2022-01-18T00:00:00Z", (
        "the cursor followed the walk past its corroborated horizon"
    )


def test_a_small_mailbox_still_advances_its_cursor(store):
    """The horizon is a lag, not a rank, and this is why.

    Taking the third-newest stamp outright punished a mailbox for being small:
    with three messages the third-newest *is* the oldest, so the cursor sat at
    the oldest for ever and every run re-read all three. Ordinary mail arrives
    in clusters; a year of daylight between two of a mailbox's newest messages
    is a broken clock, and three messages in three days is a Tuesday.
    """
    mail = FakeGmail({"a": "2026-08-01", "b": "2026-08-02", "c": "2026-08-03"})
    first = run(GmailSource(mail), store)

    assert len(first.receipts) == 3
    assert first.cursor == "2026-08-03T08:00:00Z", (
        "a mailbox of three messages could not move its cursor past the first"
    )
    again = run(GmailSource(mail), store, since=first.cursor)
    assert again.already_seen <= 1, (
        f"the whole mailbox was re-read: {again.already_seen} already seen"
    )


def test_a_gap_of_years_is_searched_and_a_gap_of_weeks_is_stepped(store):
    """Matrix: *an empty window*, at both sizes it comes in.

    Searching at the first empty window makes a dormant mailbox **dearer**: a
    halving search is about fifteen list calls and stepping one empty week is
    one. So a week of silence is stepped and a month of it is searched, and the
    seven-year gap below costs about the same as the four weeks in front of it.
    """
    far = FakeGmail({"old": "2019-01-02", "old2": "2019-01-03",
                     "new": "2026-08-01", "new2": "2026-08-02"}, page_size=1)
    result = run(GmailSource(far), store)
    assert len(result.receipts) == 4
    assert len(far.lists) < 2 * MAX_PROBES + 20, (
        f"the seven-year gap cost {len(far.lists)} list calls; it was stepped"
    )

    near = FakeGmail({"a": "2026-01-05", "b": "2026-02-02"}, page_size=1)
    run(GmailSource(near), store)
    assert len(near.lists) < MAX_PROBES + 12, (
        f"a four-week gap cost {len(near.lists)} list calls; it was searched, "
        "and a search costs more than the steps it replaced"
    )


def test_the_demonstration_bounds_its_window_even_on_a_small_mailbox(store):
    """The bound is not conditional on the mailbox being big.

    One Gmail page holds a hundred messages. Reading a hundred oldest-first
    under a ninety-second cut spends the whole demonstration on the *oldest*
    mail a new main has — the wrong week, read carefully — so this read bounds
    a window whether or not the remainder happens to fit in one answer.
    """
    days = a_month(40)                        # one page, and six weeks of mail
    mail = FakeGmail(days)
    result = run(GmailRecent(mail), store)

    read = {r.external_id for r in result.receipts}
    assert "m39" in read and "m00" not in read
    assert len(read) <= WINDOW_DAYS + 1
    assert any("before:" in q and "after:" in q for q in mail.lists)


def test_a_recent_read_with_a_cursor_past_every_message_reads_nothing(store):
    """A window whose start would sit after its end is not a window.

    Reachable whenever a demonstration re-runs against a cursor already past
    the mailbox: the newest stamp is behind the cursor, so the computed window
    inverts. It must answer nothing rather than query backwards.
    """
    mail = FakeGmail(a_month(3))
    result = run(GmailRecent(mail), store, since="2027-01-01T00:00:00Z")
    assert result.receipts == [] and result.cursor == "2027-01-01T00:00:00Z"


def test_a_mailbox_whose_newest_messages_have_no_date_is_still_read(store):
    """Review's reproduction, kept: the outage the horizon probe used to be.

    The probe read six ids of the **first page only**, so a mailbox whose six
    newest messages carried no ``internalDate`` yielded no stamp, and the walk
    logged and returned. Measured on the shipped build: fifty-six messages,
    page size ten, the six newest undated — nought of fifty-six ingested over
    four runs, the cursor never moving, repeating every run for ever. Not a
    loss, and a total outage for that mailbox.

    The probe now walks on through pages, bounded by ``HORIZON_PROBES`` reads.
    """
    days = a_month(56)
    newest = sorted(days)[-6:]
    mail = FakeGmail(days, page_size=10, undated=tuple(newest))
    result = run(GmailSource(mail), store)

    read = {r.external_id for r in result.receipts}
    assert len(read) == 50, f"{len(read)} of the 50 readable messages were read"
    assert not read & set(newest), "an undated message was somehow stamped"
    assert result.cursor is not None, "the cursor did not move at all"


def test_a_mailbox_with_no_readable_date_anywhere_stops_and_says_so(store, caplog):
    """And the bail-out is still reachable, which is the other half.

    A mailbox with nothing readable in ``HORIZON_PROBES`` reads cannot be
    placed in time at all. It stops — the walk cannot invent a window, and
    stamping one from a clock is the fabrication ``_iso_from_internal_date``
    already refuses — and it says so, in counts (AD-22).
    """
    days = a_month(60)
    mail = FakeGmail(days, page_size=10, undated=tuple(days))
    with caplog.at_level("WARNING"):
        result = run(GmailSource(mail), store)

    assert result.receipts == [] and result.cursor is None
    said = "\n".join(r.getMessage() for r in caplog.records)
    assert "cannot bound a window" in said
    assert not any(mid in said for mid in days), "an id reached a log line"


def test_the_shipped_window_is_the_one_the_measurement_argues_for():
    """The constant's justification, checkable rather than asserted in prose.

    ``WINDOW_MEASUREMENT`` is regenerated by ``tools/window_sim.py`` driving
    this walk, and it is here so that a change to the walk which moves the
    numbers is visible. What it has to show is that the shipped width is not
    the worst on either axis: not the dearest per message on the mailbox least
    able to afford requests, and not the one asking a busy mailbox to drain a
    window no deadline can finish.
    """
    from half.ingest.gmail import WINDOW_MEASUREMENT

    assert WINDOW_DAYS in WINDOW_MEASUREMENT, "the shipped width is unmeasured"
    costs = {w: rows["dormant"][0] for w, rows in WINDOW_MEASUREMENT.items()}
    drains = {w: rows["firehose"][1] for w, rows in WINDOW_MEASUREMENT.items()}

    assert costs[WINDOW_DAYS] < costs[min(costs)], (
        "the shipped width is the dearest per message on a sparse mailbox"
    )
    assert drains[WINDOW_DAYS] < drains[max(drains)], (
        "the shipped width asks the busiest mailbox to drain the largest window"
    )


# -- the bounds, and the shapes that are build mistakes -----------------------

@pytest.mark.parametrize("bad", [0, -1, "a week", None, 1.5])
def test_a_window_that_walks_nothing_forward_is_refused(bad):
    """A window of no days repeats one instant for ever while looking like
    progress, and a window that is not a number of days is a build mistake.
    Both are refused at construction, in this module's own vocabulary."""
    if bad == 1.5:
        assert GmailSource(object(), window_days=bad).window_days == 1
        return
    with pytest.raises(ChannelError):
        GmailSource(object(), window_days=bad)


def test_a_stamp_beyond_any_calendar_is_refused_rather_than_raised_raw(store):
    """A provider answering with an absurd ``internalDate`` must not throw an
    ``OverflowError`` out of a walk: it is neither a ``ChannelError`` nor
    anything a caller of this port is told to expect."""
    from half.ingest.gmail import _instant, _plus

    with pytest.raises(ChannelError):
        _plus(_instant("9999-12-31T00:00:00Z"), 30)


def test_the_watermark_is_cleared_when_a_pull_is_asked_for(store):
    """The reset is at the call and not at the first message.

    ``fetch`` used to be an async generator, whose body does not run until
    something asks it for a message — so a pull built and dropped, or a second
    pull over one source, left the previous walk's watermark standing and
    naming ground this pull has not covered.
    """
    walking = GmailSource(FakeGmail(a_month(20), page_size=5))
    run(walking, store)
    assert walking.drained_through is not None

    walking.fetch(since=None)          # asked for, never driven
    assert walking.drained_through is None, (
        "a pull that was asked for left the last one's watermark standing"
    )


def test_a_walk_that_spends_its_window_budget_says_so(store, caplog):
    """Every bound in this module reports itself. A walk that runs out of
    windows stops where it drained — it does not move the watermark past ground
    it did not cover — and the next pull continues from there."""
    from half.ingest import gmail as module

    mail = FakeGmail({"a": "2020-01-01", "z": "2026-08-01"}, page_size=1)
    with caplog.at_level("WARNING"):
        with pytest.MonkeyPatch.context() as patch:
            patch.setattr(module, "MAX_WINDOWS", 2)
            result = run(GmailSource(mail), store)

    said = "\n".join(r.getMessage() for r in caplog.records)
    assert "windows" in said, "a bound was reached and nothing said so"
    assert result.cursor is not None and result.cursor < "2026-01-01T00:00:00Z"
