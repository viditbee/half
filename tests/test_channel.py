"""Channel port behaviour — one test per I/O matrix row."""

from __future__ import annotations

import asyncio

import pytest

from urllib.parse import parse_qs, urlparse

from half.channel.port import Channel, Inbound, Reachability
from half.channel.telegram import MAX_MESSAGE_UNITS, TelegramChannel, split, utf16_len
from tests.conftest import FakeTransport, msg
import datetime as _dt

from half.channel.window import (
    LatchRule,
    ReachabilityTracker,
    RollingWindowRule,
)
from half.errors import ForbiddenRecipient, NotReachable, SendFailed


def channel(updates=None, fail=None, mains=None):
    return TelegramChannel(
        transport=FakeTransport(updates, fail), mains=mains or {"123": "vidit"}
    )


# -- the port is what the spine says it is -----------------------------------

def test_the_adapter_satisfies_the_port():
    assert isinstance(channel(), Channel)


def test_the_port_has_exactly_four_operations():
    ops = set(Channel.__protocol_attrs__) - {"name"}
    assert ops == {"receive", "send", "draft_link", "capability_query"}


# -- inbound -----------------------------------------------------------------

def test_inbound_from_a_registered_main_is_routed():
    ch = channel([msg(text="i want to fly again")])
    got = asyncio.run(_collect(ch))
    assert len(got) == 1
    assert got[0].main_id == "vidit"
    assert got[0].text == "i want to fly again"


def test_an_unknown_sender_is_dropped_and_never_recorded():
    ch = channel([msg(chat_id="999", text="stranger")])
    assert asyncio.run(_collect(ch)) == []


def test_inbound_normalizes_the_timestamp_to_utc_iso():
    ch = channel([msg(date=1_788_264_000)])
    assert asyncio.run(_collect(ch))[0].t == "2026-09-01T12:00:00Z"


def test_an_inbound_date_is_clamped_into_the_range_the_store_can_read():
    """Story 9a moved the epoch-to-stamp conversion into the one clock module,
    and moved the clamp with it — into **the range the store validates**, not
    the range ``datetime`` can render.

    ``half.civil.instant`` refuses anything outside 2000–2200, and it is what
    every floor, timescale and due-time comparison in the product is measured
    with. So a 1970 stamp is not a harmless oddity: it renders, it stores, and
    then every consumer silently declines to act on it. An epoch-zero date is
    not a real Telegram message anyway; being visibly clamped beats being
    invisibly unreadable.
    """
    from half.civil import instant

    for date in (0, -1, 10 ** 30):
        stamp = asyncio.run(_collect(channel([msg(date=date)])))[0].t
        assert instant(stamp) is not None, f"{date} produced an unreadable {stamp}"


# -- reachability ------------------------------------------------------------

def test_a_main_who_has_never_written_is_not_reachable():
    assert channel().capability_query("vidit") is Reachability.NEVER_CONTACTED


def test_one_inbound_opens_telegram_permanently():
    ch = channel([msg()])
    asyncio.run(_collect(ch))
    assert ch.capability_query("vidit") is Reachability.OPEN


def test_a_rolling_window_closes_after_its_period():
    tracker = ReachabilityTracker(rule=RollingWindowRule(seconds=100))
    tracker.note_inbound("vidit", epoch=0)
    assert tracker.reachability("vidit", now=50) is Reachability.OPEN
    assert tracker.reachability("vidit", now=500) is Reachability.WINDOW_CLOSED


def test_only_open_permits_a_freeform_message():
    assert Reachability.OPEN.may_send_freeform
    assert not Reachability.NEVER_CONTACTED.may_send_freeform
    assert not Reachability.WINDOW_CLOSED.may_send_freeform


def test_a_latch_never_closes_however_long_the_silence():
    tracker = ReachabilityTracker(rule=LatchRule())
    tracker.note_inbound("vidit", epoch=0)
    assert tracker.reachability("vidit", now=10**12) is Reachability.OPEN


def test_send_refuses_when_the_main_is_not_reachable():
    ch = channel()
    with pytest.raises(NotReachable):
        asyncio.run(ch.send("vidit", "unprompted"))
    assert ch.transport.sent == []  # no API call attempted


# -- outbound ----------------------------------------------------------------

def test_send_reaches_the_mains_own_thread():
    ch = channel([msg()])
    asyncio.run(_collect(ch))
    result = asyncio.run(ch.send("vidit", "hello"))
    assert ch.transport.sent == [("123", "hello")]
    assert result.parts == 1


def test_send_to_anyone_other_than_the_main_is_refused():
    ch = channel([msg()])
    asyncio.run(_collect(ch))
    with pytest.raises(ForbiddenRecipient):
        asyncio.run(ch.send("someone-else", "hi"))
    assert ch.transport.sent == []


def test_a_draft_link_to_a_named_person_targets_that_conversation():
    """An earlier version put the recipient in the share sheet's `url`
    parameter — the shared *link*, not an addressee — so it neither targeted
    anyone nor was discarded."""
    link = channel().draft_link("dinner friday?", to="priya")
    parsed = urlparse(link)
    assert parsed.netloc == "t.me"
    assert parsed.path == "/priya"
    assert parse_qs(parsed.query)["text"] == ["dinner friday?"]


def test_a_draft_link_without_a_recipient_opens_the_share_sheet():
    link = channel().draft_link("dinner friday?")
    parsed = urlparse(link)
    assert parsed.path == "/share/url"
    assert parse_qs(parsed.query)["text"] == ["dinner friday?"]


def test_a_leading_at_sign_is_not_doubled():
    assert "/@" not in channel().draft_link("hi", to="@priya")


@pytest.mark.parametrize(
    "error,retryable",
    [
        (TimeoutError("timed out"), True),
        (ConnectionError("reset"), True),
        (RuntimeError("Forbidden: bot was blocked by the user"), False),
        (RuntimeError("Bad Request: chat not found"), False),
    ],
)
def test_transport_errors_become_domain_errors_with_a_retryable_verdict(error, retryable):
    ch = channel([msg()], fail=error)
    asyncio.run(_collect(ch))
    with pytest.raises(SendFailed) as excinfo:
        asyncio.run(ch.send("vidit", "hello"))
    assert excinfo.value.retryable is retryable


# -- splitting ---------------------------------------------------------------

def test_a_long_reply_is_split_in_order_under_the_platform_limit():
    text = "\n\n".join(f"paragraph {i} " + "word " * 200 for i in range(12))
    parts = split(text, MAX_MESSAGE_UNITS)
    assert len(parts) > 1
    assert all(len(p) <= MAX_MESSAGE_UNITS for p in parts)
    assert "".join(p.replace("\n", " ") for p in parts).split()[:3] == text.split()[:3]


def test_a_short_reply_is_not_split():
    assert split("short", MAX_MESSAGE_UNITS) == ["short"]


def test_splitting_prefers_a_boundary_over_cutting_a_word():
    parts = split("alpha beta gamma delta", 12)
    assert all(not p.endswith(("alph", "bet", "gamm")) for p in parts)


def test_send_splits_and_preserves_order():
    ch = channel([msg()])
    asyncio.run(_collect(ch))
    result = asyncio.run(ch.send("vidit", "word " * 2000))
    assert result.parts == len(ch.transport.sent) > 1


async def _collect(ch) -> list[Inbound]:
    return [m async for m in ch.receive()]


# -- the concrete transport --------------------------------------------------

def test_the_real_transport_refuses_an_empty_token():
    """Credentials come from the environment, never a store tree (AD-11)."""
    from half.errors import ChannelError
    from half.channel.telegram_transport import PTBTransport

    with pytest.raises(ChannelError):
        PTBTransport("")


def test_the_real_transport_satisfies_the_adapter_contract():
    """The adapter only needs poll and send_message, so the fake used
    throughout these tests is a faithful stand-in rather than a convenience."""
    from half.channel.telegram_transport import PTBTransport

    for operation in ("poll", "send_message"):
        assert hasattr(PTBTransport, operation)
        assert hasattr(FakeTransport, operation)


# ── review findings: gaps the original suite could not observe ─────────────

def test_splitting_respects_utf16_units_not_characters():
    """Telegram counts UTF-16 code units. An emoji is one character and two
    units, so a code-point measure ships an unsendable message — and every
    original split test was ASCII, where the two coincide."""
    parts = split("\U0001F600" * 3000, MAX_MESSAGE_UNITS)
    assert len(parts) > 1
    assert all(utf16_len(p) <= MAX_MESSAGE_UNITS for p in parts)


def test_splitting_never_severs_a_surrogate_pair():
    for part in split("\U0001F600" * 3000, MAX_MESSAGE_UNITS):
        part.encode("utf-8")  # raises on a lone surrogate


def test_splitting_is_lossless_over_the_whole_text():
    """The original assertion compared only the first three words, so a lossy
    splitter passed."""
    text = "\n\n".join(f"paragraph {i} " + "word " * 200 for i in range(12))
    assert " ".join(split(text, MAX_MESSAGE_UNITS)).split() == text.split()


@pytest.mark.parametrize("text", ["", "   ", "\n\n\t"])
def test_whitespace_only_text_produces_no_chunks(text):
    assert split(text, MAX_MESSAGE_UNITS) == []


def test_split_rejects_a_non_positive_limit():
    """A zero limit used to loop forever, hanging the worker for every main."""
    with pytest.raises(ValueError):
        split("anything", 0)


def test_send_refuses_an_empty_body_rather_than_posting_one():
    ch = channel([msg()])
    asyncio.run(_collect(ch))
    result = asyncio.run(ch.send("vidit", "   "))
    assert result.parts == 0
    assert ch.transport.sent == []


@pytest.mark.parametrize("bug", [TypeError("bad call"), AttributeError("no attr")])
def test_a_programming_error_is_not_reclassified_as_a_transport_fault(bug):
    """Substring matching used to call these retryable, so a bug would be
    retried forever."""
    ch = channel([msg()], fail=bug)
    asyncio.run(_collect(ch))
    with pytest.raises(type(bug)):
        asyncio.run(ch.send("vidit", "hello"))


def test_an_unknown_exception_shape_is_treated_as_permanent():
    ch = channel([msg()], fail=RuntimeError("something new"))
    asyncio.run(_collect(ch))
    with pytest.raises(SendFailed) as excinfo:
        asyncio.run(ch.send("vidit", "hello"))
    assert excinfo.value.retryable is False


@pytest.mark.parametrize("date", [None, "not-a-number", {}, []])
def test_a_malformed_timestamp_does_not_kill_the_receive_loop(date):
    ch = channel([msg(date=date)])
    got = asyncio.run(_collect(ch))
    assert len(got) == 1 and got[0].t.endswith("Z")


@pytest.mark.parametrize("date", [10**18, -10**18])
def test_an_absurd_timestamp_does_not_abort_processing(date):
    ch = channel([msg(date=date)])
    assert len(asyncio.run(_collect(ch))) == 1


def test_a_window_closes_exactly_at_expiry():
    tracker = ReachabilityTracker(rule=RollingWindowRule(seconds=100))
    tracker.note_inbound("vidit", epoch=0)
    assert tracker.reachability("vidit", now=100) is Reachability.WINDOW_CLOSED


def test_a_future_dated_inbound_does_not_hold_a_window_open():
    tracker = ReachabilityTracker(rule=RollingWindowRule(seconds=100))
    tracker.note_inbound("vidit", epoch=10_000)
    assert tracker.reachability("vidit", now=0) is Reachability.WINDOW_CLOSED


def test_reachability_is_rebuilt_from_the_log_after_a_restart(tmp_path):
    """The tracker claimed to be derived from the log but was populated only by
    live traffic, so a restart reported every main NEVER_CONTACTED and the
    morning surface was dead on boot."""
    from half.store.ops import Op
    from half.store.store import Store

    with Store(tmp_path / "vidit") as store:
        store.record(Op.ASSERT, "b_1", "2026-08-14T09:12:00Z",
                     subject="self", claim="hello", ledger="stated")
        tracker = ReachabilityTracker(rule=LatchRule())
        assert tracker.reachability("vidit", now=1e9) is Reachability.NEVER_CONTACTED
        tracker.rebuild_from("vidit", store.log)
        assert tracker.reachability("vidit", now=1e9) is Reachability.OPEN


# -- the transport/adapter dict contract ------------------------------------

class _FakeMessage:
    def __init__(self, text=None, caption=None):
        self.chat_id = 123
        self.message_id = 7
        self.text = text
        self.caption = caption
        self.date = _dt.datetime(2026, 8, 14, 9, 12, tzinfo=_dt.UTC)


class _FakeUpdate:
    def __init__(self, message=None, edited=None):
        self.update_id = 1
        self.message = message
        self.edited_message = edited


def test_the_transport_emits_exactly_the_keys_the_adapter_reads():
    """Renaming one key used to leave all tests green while Half polled,
    received, and silently discarded every message from every main."""
    from half.channel.telegram_transport import normalize

    payload = normalize(_FakeUpdate(_FakeMessage(text="i want to fly again")))
    assert payload is not None

    ch = TelegramChannel(transport=FakeTransport([payload]), mains={"123": "vidit"})
    got = asyncio.run(_collect(ch))
    assert len(got) == 1
    assert got[0].main_id == "vidit"
    assert got[0].text == "i want to fly again"
    assert got[0].external_id == "7"
    assert got[0].t == "2026-08-14T09:12:00Z"


def test_an_edited_message_still_counts_as_the_main_speaking():
    from half.channel.telegram_transport import normalize
    assert normalize(_FakeUpdate(edited=_FakeMessage(text="actually, no"))) is not None


def test_a_caption_is_not_discarded():
    from half.channel.telegram_transport import normalize
    assert normalize(_FakeUpdate(_FakeMessage(caption="look at this"))) is not None


def test_an_update_with_no_text_is_skipped():
    from half.channel.telegram_transport import normalize
    assert normalize(_FakeUpdate(_FakeMessage())) is None
    assert normalize(_FakeUpdate()) is None
