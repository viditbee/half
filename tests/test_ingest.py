"""Ingestion: capture, idempotency, and the byte-level safety property."""

from __future__ import annotations

import asyncio
import base64
from pathlib import Path

import pytest

from half.ingest.gmail import GmailSource, normalize
from half.ingest.pipeline import Pipeline
from half.ingest.port import MailSource, Message
from half.store.sources import LocalSourceStore, digest

SECRET = "AKIA" + "IOSFODNN7EXAMPLE"


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


def message(i, body, *, thread="t1", sender="a@x"):
    return Message(
        external_id=f"m{i}", thread_id=thread, sender=sender, subject="s",
        body=body if isinstance(body, bytes) else body.encode(),
        t=f"2026-08-{i + 1:02d}T00:00:00Z",
    )


@pytest.fixture
def store(tmp_path):
    return LocalSourceStore(tmp_path / "sources")


def run(source, store, **kw):
    return asyncio.run(Pipeline(source, store).ingest(**kw))


def all_bytes(root: Path) -> bytes:
    return b"".join(p.read_bytes() for p in root.rglob("*") if p.is_file())


# -- capture -----------------------------------------------------------------

def test_a_message_is_captured_content_addressed(store, tmp_path):
    result = run(FakeMail([message(0, "lunch at 1pm?")]), store)
    assert len(result.captured) == 1
    assert store.has(result.captured[0].address)
    assert len(store) == 1


def test_re_ingesting_captures_nothing_twice(store):
    mail = FakeMail([message(0, "lunch at 1pm?"), message(1, "swim thursday")])
    first = run(mail, store)
    second = run(mail, store)
    assert len(store) == 2
    assert all(c.already_present for c in second.captured)
    assert [c.address for c in first.captured] == [c.address for c in second.captured]


def test_the_cursor_advances_to_the_newest_message(store):
    result = run(FakeMail([message(0, "a"), message(1, "b"), message(2, "c")]), store)
    assert result.cursor == "2026-08-03T00:00:00Z"


def test_a_cursor_resumes_rather_than_replaying(store):
    mail = FakeMail([message(0, "a"), message(1, "b"), message(2, "c")])
    run(mail, store)
    resumed = run(mail, store, since="2026-08-02T00:00:00Z")
    assert [c.external_id for c in resumed.captured] == ["m2"]


# -- the safety property, verified at the byte level -------------------------

def test_no_secret_byte_reaches_disk(store, tmp_path):
    """CAP-13's criterion is checkable by construction: walk every byte
    written rather than trusting the scrubber's return value."""
    run(FakeMail([
        message(0, f"the key is {SECRET} please use it"),
        message(1, "your verification code is 483920"),
        message(2, "lunch at 1pm?"),
    ]), store)
    written = all_bytes(tmp_path / "sources")
    assert SECRET.encode() not in written
    assert b"483920" not in written
    assert b"lunch at 1pm?" in written  # the innocent message survived


def test_a_secret_only_message_is_not_captured_at_all(store):
    result = run(FakeMail([message(0, SECRET)]), store)
    assert result.captured == []
    assert result.skipped_secret_only == 1
    assert len(store) == 0


def test_undecodable_content_is_not_captured(store):
    result = run(FakeMail([message(0, b"\xff\xfe binary junk")]), store)
    assert result.captured == []
    assert result.skipped_undecodable == 1
    assert len(store) == 0


def test_a_redacted_message_records_kinds_but_never_values(store):
    result = run(FakeMail([message(0, f"key {SECRET}")]), store)
    captured = result.captured[0]
    assert captured.redactions == {"aws access key id": 1}
    assert SECRET not in repr(captured)


def test_redaction_changes_the_content_address(store):
    """The digest must be of the redacted bytes, or the address itself leaks
    which unredacted body produced it."""
    clean = run(FakeMail([message(0, "key [redacted: aws access key id]")]), store)
    assert clean.captured[0].address == digest(
        store.get(clean.captured[0].address)
    )


# -- failure ------------------------------------------------------------------

def test_a_failure_mid_page_leaves_earlier_captures_valid(store):
    mail = FakeMail([message(0, "a"), message(1, "b"), message(2, "c")], fail_after=2)
    with pytest.raises(RuntimeError):
        run(mail, store)
    assert len(store) == 2  # the two before the failure are intact


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


def test_the_gmail_adapter_satisfies_the_port():
    assert isinstance(GmailSource(transport=None), MailSource)


def test_gmail_normalization_feeds_the_pipeline_unchanged(store):
    """The contract between the network edge and the pipeline, pinned — the
    failure mode story 2 taught: a renamed key leaves tests green while Half
    silently ingests nothing."""
    normalized = normalize(_gmail_raw())
    assert normalized is not None
    result = run(FakeMail([normalized]), store)
    assert len(result.captured) == 1
    assert result.captured[0].thread_id == "t1"
    assert result.captured[0].sender == "a@x"


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


def test_a_gmail_message_with_no_readable_part_is_skipped():
    assert normalize({"id": "x", "payload": {"mimeType": "image/png"}}) is None


def test_a_malformed_internal_date_does_not_abort_normalization():
    assert normalize(_gmail_raw() | {"internalDate": "not-a-number"}).t.endswith("Z")
