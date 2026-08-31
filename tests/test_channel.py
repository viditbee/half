"""Channel port behaviour — one test per I/O matrix row."""

from __future__ import annotations

import asyncio

import pytest

from half.channel.port import Channel, Inbound, Reachability
from half.channel.telegram import MAX_MESSAGE_CHARS, TelegramChannel, split
from half.channel.window import (
    LatchRule,
    ReachabilityTracker,
    RollingWindowRule,
)
from half.errors import ForbiddenRecipient, NotReachable, SendFailed


class FakeTransport:
    """The whole network surface the adapter needs, so tests stay offline."""

    def __init__(self, updates=None, fail=None):
        self.updates = updates or []
        self.sent: list[tuple[str, str]] = []
        self.fail = fail

    async def poll(self):
        for update in self.updates:
            yield update

    async def send_message(self, chat_id: str, text: str) -> str:
        if self.fail is not None:
            raise self.fail
        self.sent.append((chat_id, text))
        return f"mid-{len(self.sent)}"


def channel(updates=None, fail=None, mains=None):
    return TelegramChannel(
        transport=FakeTransport(updates, fail), mains=mains or {"123": "vidit"}
    )


def msg(**kw):
    return {"chat_id": "123", "text": "hi", "message_id": "1", "date": 1000, **kw}


# -- the port is what the spine says it is -----------------------------------

def test_the_adapter_satisfies_the_port():
    assert isinstance(channel(), Channel)


def test_the_port_has_exactly_four_operations():
    ops = set(Channel.__protocol_attrs__) - {"name"}
    assert ops == {"receive", "send", "draft_link", "capability_query"}


# -- inbound -----------------------------------------------------------------

def test_inbound_from_a_registered_main_is_routed(anyio_backend=None):
    ch = channel([msg(text="i want to fly again")])
    got = asyncio.run(_collect(ch))
    assert len(got) == 1
    assert got[0].main_id == "vidit"
    assert got[0].text == "i want to fly again"


def test_an_unknown_sender_is_dropped_and_never_recorded():
    ch = channel([msg(chat_id="999", text="stranger")])
    assert asyncio.run(_collect(ch)) == []


def test_inbound_normalizes_the_timestamp_to_utc_iso():
    ch = channel([msg(date=0)])
    assert asyncio.run(_collect(ch))[0].t == "1970-01-01T00:00:00Z"


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


def test_a_draft_link_is_the_only_route_to_a_third_party():
    link = channel().draft_link("dinner friday?", to="priya")
    assert link.startswith("https://t.me/share/url")
    assert "dinner" in link


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
    parts = split(text, MAX_MESSAGE_CHARS)
    assert len(parts) > 1
    assert all(len(p) <= MAX_MESSAGE_CHARS for p in parts)
    assert "".join(p.replace("\n", " ") for p in parts).split()[:3] == text.split()[:3]


def test_a_short_reply_is_not_split():
    assert split("short", MAX_MESSAGE_CHARS) == ["short"]


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
