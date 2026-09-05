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
    HORIZON_SAMPLES,
    MAX_PROBES,
    WINDOW_DAYS,
    GmailRecent,
    GmailSource,
    normalize,
)
from half.ingest.pipeline import Pipeline, Receipt
from half.ingest.port import MailSource, Message
from half.ingest.scrub import Scrubbed
from half.store.sources import LocalSourceStore, digest

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


def _epoch_ms(day: str) -> str:
    """A day as Gmail's own ``internalDate``: epoch milliseconds, as a string."""
    at = datetime.datetime.fromisoformat(f"{day}T08:00:00+00:00")
    return str(int(at.timestamp() * 1000))


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


def test_a_repeating_page_token_terminates():
    class Looping:
        async def list_messages(self, *, query, page_token):
            return {"messages": [], "nextPageToken": "same"}
        async def get_message(self, message_id):
            return {}

    async def collect():
        return [m async for m in GmailSource(Looping()).fetch()]

    assert asyncio.run(collect()) == []


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

#: A mailbox at the transport door, answering the query it was actually asked.
#:
#: Written because the walk story 20 ships asks *real questions* — a window is a
#: query bounded at both ends, and the answer has to respect both — and a fake
#: answering a scripted queue positionally cannot fail when the query is wrong.
#: It answers **newest-first**, which is what Gmail does and what this walk
#: exists to reverse; a fake that answered oldest-first would make every case
#: below pass against a build that does nothing at all.
class FakeGmail:
    """A mailbox of ``{id: day}``, paged, with `after:` and `before:` honoured."""

    name = "gmail"

    def __init__(self, days, *, page_size=100, fail_on=None):
        self.days = dict(days)
        self.page_size = page_size
        #: The id whose read fails, and every read after it. Named rather than
        #: counted, because the walk reads a few of the newest messages first
        #: to find its horizon and a count would land somewhere different every
        #: time that number changed.
        self.fail_on = fail_on
        self.broken = False
        self.lists: list[str] = []
        self.gets: list[str] = []

    def matching(self, query: str) -> list[str]:
        after = before = None
        for term in query.split():
            if term.startswith("after:"):
                after = term[len("after:"):].replace("/", "-")
            elif term.startswith("before:"):
                before = term[len("before:"):].replace("/", "-")
        chosen = [
            mid for mid, day in self.days.items()
            # Gmail's own reading, and the one ``_query_for`` documents:
            # ``after:`` includes the day it names, ``before:`` excludes it.
            if (after is None or day >= after) and (before is None or day < before)
        ]
        return sorted(chosen, key=lambda mid: (self.days[mid], mid), reverse=True)

    async def list_messages(self, *, query, page_token):
        self.lists.append(query)
        ids = self.matching(query)
        start = int(page_token or 0)
        page = {"messages": [{"id": i} for i in ids[start:start + self.page_size]]}
        if start + self.page_size < len(ids):
            page["nextPageToken"] = str(start + self.page_size)
        return page

    async def get_message(self, message_id):
        self.gets.append(message_id)
        if message_id == self.fail_on:
            self.broken = True
        if self.broken:
            raise RuntimeError("the provider stopped answering mid-window")
        # **A body of its own per message**, because the digest is over the
        # body: a double handing every message the same text gives every
        # receipt the same address, and *twenty of twenty ingested* becomes one
        # receipt and nineteen already-seens against a build that is working.
        return _gmail_raw(
            body=f"the plot at {message_id} has not been walked",
            mid=message_id, at=_epoch_ms(self.days[message_id]),
        )


class Cut:
    """A source that stops yielding after ``after`` messages.

    ``half.__main__.Bounded`` in miniature — the same shape, cutting on a count
    rather than on a clock, so that *what a cut costs* is a property of the walk
    rather than of how fast the suite happens to run. It forwards
    ``drained_through`` for the reason ``Bounded`` does: a wrapper that
    swallowed the watermark would send the pipeline back to the ``max()`` this
    story removed, and every case here would pass for the wrong reason.
    """

    def __init__(self, source, *, after: int):
        self.source = source
        self.name = getattr(source, "name", "cut")
        self.after = after
        self.stopped_early = False

    def __getattr__(self, name):
        if name == "drained_through":
            return getattr(self.source, name)
        raise AttributeError(name)

    async def fetch(self, *, since=None):
        handed = 0
        async for message in self.source.fetch(since=since):
            yield message
            handed += 1
            if handed >= self.after:
                self.stopped_early = True
                return


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
    mail = FakeGmail(a_month(5))
    assert mail.matching("") == ["m04", "m03", "m02", "m01", "m00"]


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
    mail = FakeGmail(a_month(20), page_size=5, fail_on="m03")
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
    assert len(mail.lists) < 200, "the walk spent unbounded requests on nothing"


def test_a_dense_window_is_paged_within_the_window():
    """Matrix: *a very dense window*. More than one page, still oldest first."""
    days = {f"m{i:03d}": "2026-08-03" for i in range(25)}
    mail = FakeGmail(days, page_size=4)
    got = walk(GmailSource(mail))

    assert [m.external_id for m in got] == sorted(days)
    assert sum(1 for q in mail.lists if "before:" in q) >= 6, "the window never paged"


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
    mail = FakeGmail(a_month(3))
    undated = dict(mail.days)
    mail.days = undated

    async def get_message(message_id):
        raw = _gmail_raw(body=f"a body for {message_id}", mid=message_id,
                         at=_epoch_ms(undated[message_id]))
        return raw | ({"internalDate": None} if message_id == "m02" else {})

    mail.get_message = get_message
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
    # A week, plus the lag of the corroborated stamp the window reaches back
    # from — and nothing like the six weeks the history walk would have read.
    assert read <= set(sorted(days)[-(WINDOW_DAYS + HORIZON_SAMPLES):]), (
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

    Half-open, and that is what lets windows tile: ``after:`` includes the day
    it names and ``before:`` excludes it, so the day one window ends on is the
    day the next begins and no message falls between them.
    """
    from half.ingest.gmail import _query_for

    assert _query_for("2026-03-04T05:06:07Z") == "after:2026/03/04"
    assert _query_for("2026-03-04", "2026-03-11") == (
        "after:2026/03/04 before:2026/03/11"
    )
    assert _query_for(None, "2026-03-11") == "before:2026/03/11"
    assert _query_for(None) == "", "no cursor is the whole mailbox, as before"


def test_a_windowed_walk_asks_for_both_bounds():
    """And the bounds are on the wire, not merely computable."""
    mail = FakeGmail(a_month(20), page_size=5)
    walk(GmailSource(mail))
    windows = [q for q in mail.lists if "after:" in q and "before:" in q]
    assert windows, "no window query was ever made"
    assert all(q.startswith("after:") for q in windows)


# -- the budget wrapper, which must not swallow the watermark ------------------

def test_the_budget_wrapper_carries_the_watermark_of_what_it_wraps():
    """``half.__main__.Bounded`` is the shape of CAP-2's budget on a pull.

    A wrapper that swallowed ``drained_through`` would leave the pipeline with
    no watermark at all and send it back to the ``max()`` this story removed —
    silently, and with every case above still green, because they drive the
    source directly.
    """
    from half.__main__ import Bounded

    walking = GmailSource(FakeGmail(a_month(20), page_size=5))
    bounded = Bounded(walking, seconds=30.0)
    walking.drained_through = "2026-08-08T00:00:00Z"
    assert bounded.drained_through == "2026-08-08T00:00:00Z"

    plain = Bounded(FakeMail([message(0, "a")]), seconds=30.0)
    with pytest.raises(AttributeError):
        plain.drained_through  # a source that publishes none must not gain one


def test_the_demonstrations_own_wiring_moves_no_history_cursor(store):
    """CAP-2 as it is actually wired: bounded, over the recent read.

    ``half.__main__.onboard`` wraps the source in ``Bounded`` and
    ``half.__main__.onboarded`` builds a ``GmailRecent``. Both together are the
    ninety seconds, and together they must leave the history cursor exactly
    where they found it — which is the acceptance criterion, over the two
    objects the shipped path composes rather than over one of them.
    """
    from half.__main__ import Bounded

    recent = Bounded(GmailRecent(FakeGmail(a_month(40), page_size=5)),
                     seconds=30.0)
    result = run(recent, store, since="2026-08-05T00:00:00Z")

    assert result.receipts, "the demonstration read nothing"
    assert result.cursor == "2026-08-05T00:00:00Z"


# -- where a first walk begins ------------------------------------------------

def test_a_first_walk_finds_the_mailbox_s_oldest_day_rather_than_the_floor(store):
    """A first walk has no cursor, and the floor is fifty years back.

    Starting at ``MAILBOX_FLOOR`` and stepping a week at a time would be
    correct and would spend two and a half thousand list calls on empty weeks
    before reaching any mail — under a caller's deadline, a first pull that
    reads nothing at all, every time. The halving search is what makes the
    first walk affordable, and its cost is bounded by ``MAX_PROBES``.
    """
    mail = FakeGmail({"a": "2019-06-04", "b": "2019-06-05", "c": "2019-06-06",
                      "d": "2019-06-07", "e": "2026-08-01"}, page_size=2)
    result = run(GmailSource(mail), store)

    assert {r.external_id for r in result.receipts} == {"a", "b", "c", "d", "e"}
    probes = [q for q in mail.lists if q.startswith("before:")]
    assert len(probes) <= MAX_PROBES, "the halving search ran unbounded"
    assert len(mail.lists) < 500, "the walk stepped up from the floor"


def test_mail_older_than_gmail_itself_is_still_walked(store):
    """The floor is the epoch and not the year the service launched.

    Mail older than Gmail lives in Gmail — imported, carrying its original
    date — and ``internalDate`` carries that date. A floor at 2004 would have
    begun the walk after such a message and no later query would ever have
    named it, which is this story's own defect rebuilt out of a plausible
    constant.
    """
    mail = FakeGmail({"ancient": "1998-11-02", "recent": "2026-08-01"},
                     page_size=1)
    result = run(GmailSource(mail), store)
    assert {r.external_id for r in result.receipts} == {"ancient", "recent"}


def test_the_walk_reaches_the_newest_message_however_old_its_horizon_is(store):
    """The stall this story nearly shipped with, kept as a case.

    The horizon is the third-newest stamp, and for a while it was also where
    the walk stopped. On a mailbox whose three newest messages are years apart
    that stops the walk short of the newest ones *and* leaves the cursor at the
    same place next run, so those messages are read never — the loss this story
    exists to remove, rebuilt out of the defence against clock skew.

    Two numbers, not one: the walk goes to the newest stamp there is, and the
    cursor is clamped to the corroborated one.
    """
    days = {"a": "2019-06-04", "b": "2019-06-05", "c": "2019-06-06",
            "d": "2022-01-10", "e": "2026-08-01"}
    mail = FakeGmail(days, page_size=2)
    result = run(GmailSource(mail), store)

    assert {r.external_id for r in result.receipts} == set(days)
    assert result.cursor is not None and result.cursor <= "2022-01-11T00:00:00Z", (
        "the cursor followed the walk past its corroborated horizon"
    )


def test_a_gap_of_years_is_jumped_rather_than_stepped(store):
    """Matrix: *an empty window*, at the size that makes stepping untenable.

    Seven years of empty weeks is three hundred and sixty list calls at a week
    apiece, and a mailbox can hold several such gaps. Halving crosses one for
    about fifteen requests however wide it is.
    """
    mail = FakeGmail({"old": "2019-01-02", "old2": "2019-01-03",
                      "new": "2026-08-01", "new2": "2026-08-02"}, page_size=1)
    result = run(GmailSource(mail), store)

    assert len(result.receipts) == 4
    assert len(mail.lists) < 60, (
        f"the gap cost {len(mail.lists)} list calls; it was stepped, not jumped"
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
    assert len(read) <= WINDOW_DAYS + HORIZON_SAMPLES
    assert any("before:" in q and "after:" in q for q in mail.lists)
