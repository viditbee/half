"""Ingestion: capture, idempotency, and the byte-level safety property."""

from __future__ import annotations

import asyncio
import base64
import quopri
from pathlib import Path

import pytest

from half.errors import ChannelError
from half.ingest.gmail import GmailSource, normalize
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


def _gmail_raw(body="lunch at 1pm?", mid="m1"):
    return {
        "id": mid, "threadId": "t1", "internalDate": "1755158400000",
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
    class Paged:
        def __init__(self):
            self.pages = [
                {"messages": [{"id": "m1"}], "nextPageToken": "p2"},
                {"messages": [{"id": "m2"}]},
            ]
        async def list_messages(self, *, query, page_token):
            return self.pages.pop(0)
        async def get_message(self, message_id):
            return _gmail_raw(mid=message_id)

    async def collect():
        return [m async for m in GmailSource(Paged()).fetch()]

    assert [m.external_id for m in asyncio.run(collect())] == ["m1", "m2"]


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
