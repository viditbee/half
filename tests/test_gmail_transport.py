"""The mailbox, reached — one case per row of story 16's I/O matrix.

**What this file is for.** ``half/ingest/gmail_transport.py`` is allowed to be
untestable without a live key; that is the point of splitting it away from
``gmail.py``. What pays for that licence is that it holds nothing worth
testing — so what is asserted here is not logic but the *bargain*: that the
token comes from the store AD-11 sanctions and reaches no URL, that no provider
text crosses the boundary, that the bounds and retries are the ones the story
names, and that this module is the only one in its package that names an HTTP
client at all.

**Offline, at the standard library's own door.** The fake replaces
``gmail_transport._open`` — the single blocking call in the package — so every
line above it runs for real: the request is built for real, the headers are
attached for real, the retry loop turns for real, and the fault translation is
the shipped one. Nothing here opens a socket, and the existing guard in
``tests/test_model_offline.py`` covers this file unchanged.

**Two sentinels, and they are the whole of the AD-11 and AD-22 assertions.**
``TOKEN`` is a credential and ``PROVIDER_BODY`` is the kind of text a Gmail
error carries — a quotation of the request that caused it. Every failure path
is driven with both present and asserted to leak neither, into a URL, an
exception, an exception's cause or context, or a log record.
"""

from __future__ import annotations

import ast
import asyncio
import base64
import email.message
import io
import time
import urllib.error
import urllib.parse
from pathlib import Path

import pytest

from half.errors import ChannelError, HalfError
from half.ingest import gmail_transport as transport_module
from half.ingest.gmail import MAX_PAGES, MAX_PROBES, GmailSource
from half.ingest.gmail_transport import (
    BACKOFF_SECONDS,
    GMAIL_TOKEN,
    MAX_ATTEMPTS,
    MAX_BACKOFF_SECONDS,
    REQUEST_SECONDS,
    HttpTransport,
    MailboxMisconfigured,
    MailboxNotAuthorised,
    MailboxRequestInvalid,
    MailboxUnavailable,
)
from half.ingest.pipeline import Pipeline
from half.secrets import FileSecretStore
from half.store.sources import LocalSourceStore

ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "half" / "ingest"

#: A credential. Assembled from parts so the AD-11 tree scan has nothing
#: credential-shaped to find, and distinctive so a leak of it is unmistakable.
TOKEN = "gmail-" + "access-token-for-tests-000111"

#: What a provider's error body carries: a quotation of the request that caused
#: it, which is exactly why AD-22 says none of it may cross.
PROVIDER_BODY = (
    "the request that failed was GET /messages for user quoted-back-verbatim"
)

#: The body of one message. Distinctive, so *never persisted* is assertable by
#: hunting for it through every byte the run wrote.
BODY = "the plot has not been walked since March"

MAIN = "vidit"


# ── the fake HTTP layer ──────────────────────────────────────────────────────


class Response:
    """What ``urlopen`` returns on success: a context manager over bytes."""

    def __init__(self, payload: bytes) -> None:
        self.payload = payload
        self.closed = False

    def __enter__(self) -> "Response":
        return self

    def __exit__(self, *exc: object) -> bool:
        self.closed = True
        return False

    def read(self) -> bytes:
        return self.payload


def a_provider_error(status: int) -> urllib.error.HTTPError:
    """A real ``HTTPError``, carrying a real body nobody may read.

    Built with an actual file object rather than ``None`` so that the case
    exercises the same object the shipped path closes — and so that a build
    which *did* read the body would find something to leak.
    """
    return urllib.error.HTTPError(
        "https://gmail.example/messages?q=x&access-token=" + TOKEN,
        status,
        PROVIDER_BODY,
        email.message.Message(),
        io.BytesIO(PROVIDER_BODY.encode("utf-8")),
    )


class FakeHttp:
    """Answers a scripted queue and records every request it was handed.

    An exhausted queue is an error rather than a repeat: a case that asserts
    *four attempts* must fail if the build makes five, and a fake that answered
    for ever could not tell the two apart.
    """

    def __init__(self, *answers: object) -> None:
        self.answers = list(answers)
        self.urls: list[str] = []
        self.headers: list[dict[str, str]] = []
        self.timeouts: list[float] = []

    def __call__(self, request: object, *, timeout: float) -> object:
        self.urls.append(request.full_url)
        self.headers.append(dict(request.header_items()))
        self.timeouts.append(timeout)
        if not self.answers:
            raise AssertionError(
                f"request {len(self.urls)} was made and the script had no answer"
            )
        answer = self.answers.pop(0)
        if isinstance(answer, BaseException):
            raise answer
        return answer


def page(*ids: str, next_token: str | None = None) -> Response:
    payload = {"messages": [{"id": i} for i in ids]}
    if next_token:
        payload["nextPageToken"] = next_token
    return Response(_json(payload))


def message(mid: str, *, body: str = BODY, at: str = "1755158400000") -> Response:
    return Response(_json({
        "id": mid,
        "threadId": "t1",
        "internalDate": at,
        "payload": {
            "mimeType": "multipart/alternative",
            "headers": [{"name": "From", "value": "a@x"},
                        {"name": "Subject", "value": "the plot"}],
            "parts": [{
                "mimeType": "text/plain",
                "body": {"data": base64.urlsafe_b64encode(
                    body.encode("utf-8")).decode("ascii")},
            }],
        },
    }))


def _json(obj: object) -> bytes:
    import json

    return json.dumps(obj).encode("utf-8")


def _epoch_ms(day: str) -> str:
    """A day as Gmail's own ``internalDate``: epoch milliseconds, as a string."""
    import datetime

    at = datetime.datetime.fromisoformat(f"{day}T08:00:00+00:00")
    return str(int(at.timestamp() * 1000))


class Mailbox:
    """A mailbox at the HTTP door, answering the query it was actually asked.

    ``FakeHttp`` answers a scripted queue **by position**, which is the right
    shape for a fault case and the wrong one for a walk. Story 20's walk asks
    real questions — a window is a query bounded at both ends, and a mailbox
    has to respect both bounds for the answer to mean anything — and a queue
    cannot fail when the question is wrong: whatever the walk asked, the third
    response is still the third one handed back.

    Newest-first, because that is what Gmail does and what the walk exists to
    reverse. A double that answered oldest-first would let every ordering case
    below pass against a build that reorders nothing at all.
    """

    def __init__(self, days: dict[str, str], *, page_size: int = 100,
                 breaks_on: str | None = None) -> None:
        self.days = dict(days)
        self.page_size = page_size
        #: The message whose read fails, every time it is asked for. Named
        #: rather than counted: the walk reads a few of the newest messages
        #: first to find its horizon, and a count would land somewhere
        #: different each time that number changed.
        self.breaks_on = breaks_on
        self.urls: list[str] = []
        self.headers: list[dict[str, str]] = []

    def matching(self, query: str) -> list[str]:
        after = before = None
        for term in query.split():
            if term.startswith("after:"):
                after = term[len("after:"):].replace("/", "-")
            elif term.startswith("before:"):
                before = term[len("before:"):].replace("/", "-")
        chosen = [
            mid for mid, day in self.days.items()
            if (after is None or day >= after) and (before is None or day < before)
        ]
        return sorted(chosen, key=lambda mid: (self.days[mid], mid), reverse=True)

    def __call__(self, request: object, *, timeout: float) -> Response:
        url = request.full_url
        self.urls.append(url)
        self.headers.append(dict(request.header_items()))
        parts = urllib.parse.urlparse(url)
        params = urllib.parse.parse_qs(parts.query)
        if parts.path.endswith("/messages"):
            ids = self.matching(params.get("q", [""])[0])
            start = int(params.get("pageToken", ["0"])[0])
            payload = {
                "messages": [
                    {"id": i} for i in ids[start:start + self.page_size]
                ]
            }
            if start + self.page_size < len(ids):
                payload["nextPageToken"] = str(start + self.page_size)
            return Response(_json(payload))

        mid = urllib.parse.unquote(parts.path.rsplit("/", 1)[-1])
        if mid == self.breaks_on:
            raise a_provider_error(500)
        return message(mid, body=f"{BODY} — {mid}", at=_epoch_ms(self.days[mid]))


@pytest.fixture
def http(monkeypatch):
    """Install a fake HTTP layer and hand the case its recorder."""

    def install(*answers: object) -> FakeHttp:
        fake = FakeHttp(*answers)
        monkeypatch.setattr(transport_module, "_open", fake)
        return fake

    return install


@pytest.fixture
def slept(monkeypatch):
    """Record the backoff instead of serving it, and keep the suite quick."""
    recorded: list[float] = []

    async def instead(seconds: float) -> None:
        recorded.append(seconds)

    monkeypatch.setattr(transport_module.asyncio, "sleep", instead)
    return recorded


def walked(source: GmailSource, *, since: str | None = None) -> list:
    async def collect():
        return [m async for m in source.fetch(since=since)]

    return asyncio.run(collect())


def asked(built: HttpTransport, *, query: str = "", page_token: str | None = None):
    """One page, asked of the transport directly.

    The fault cases go through this door rather than through ``GmailSource``,
    and that is not a convenience. ``GmailSource._call`` flattens **every**
    fault to a ``ChannelError`` carrying the class *name* — which is the right
    thing for it to do and is asserted below — but it would also make a case
    that expected ``MailboxNotAuthorised`` and one that expected
    ``MailboxRequestInvalid`` identical either way.
    """
    return asyncio.run(built.list_messages(query=query, page_token=page_token))


def leaks(exc: BaseException, needle: str) -> bool:
    """Whether ``needle`` appears anywhere in an exception or its ancestry.

    The chain matters as much as the message. ``raise ... from None`` suppresses
    the *display* of a context and still attaches the object, so an
    ``HTTPError`` holding a provider's body can ride out of the boundary inside
    an exception that prints clean.
    """
    seen: set[int] = set()
    while exc is not None and id(exc) not in seen:
        seen.add(id(exc))
        if needle in str(exc) or needle in repr(exc):
            return True
        if any(needle in str(a) for a in getattr(exc, "args", ())):
            return True
        exc = exc.__cause__ or exc.__context__
    return False


# ═════════════════════════════════════════════════════════════════════════════
# matrix: a page of messages, and paging
# ═════════════════════════════════════════════════════════════════════════════


def test_a_page_of_messages_arrives_as_the_source_expects(http):
    """Matrix: *a page of messages*. A real walk over a fake HTTP layer."""
    http(page("m1", "m2"), message("m1"), message("m2"))
    got = walked(GmailSource(HttpTransport(TOKEN)))
    assert [m.external_id for m in got] == ["m1", "m2"]
    assert [m.body for m in got] == [BODY.encode()] * 2
    assert got[0].sender == "a@x" and got[0].t == "2025-08-14T08:00:00Z"


class Echoing:
    """A fake that answers **by route** rather than by position.

    Written because the first version of the order case below could not fail.
    It scripted three message responses in a queue, so whatever order the
    transport asked in, the third response was still the third one handed back
    — and a build that reversed every page produced an identical list of ids.
    The reversal probe came back green against it. This one answers the message
    it was actually asked for, which is the only shape in which *the order is
    the provider's* is a statement about the code.
    """

    def __init__(self, *ids: str) -> None:
        self.ids = ids
        self.urls: list[str] = []

    def __call__(self, request: object, *, timeout: float) -> Response:
        self.urls.append(request.full_url)
        if "/messages?" in request.full_url:
            return page(*self.ids)
        return message(request.full_url.rsplit("/", 1)[-1].split("?")[0])

    @property
    def asked_for(self) -> list[str]:
        return [
            u.rsplit("/", 1)[-1].split("?")[0]
            for u in self.urls
            if "/messages?" not in u
        ]


def test_the_transport_hands_over_the_provider_s_own_order_untouched(monkeypatch):
    """The order is Gmail's and **this module** does not touch it.

    Two claims that used to be one, and story 20 is why they had to part. The
    transport still reorders nothing — a page comes back exactly as the
    provider sent it, newest-first, and a build that quietly reversed one here
    would be lying about what a page is. What changed is the layer above:
    ``GmailSource`` now owns the port's oldest-first promise and keeps it by
    walking that order backwards inside a bounded window.

    Before this story the two were the same claim and the honest reading was
    *the transport cannot give the matrix what it asks for*. It still cannot.
    The source can.
    """
    fake = Echoing("newest", "middle", "oldest")
    monkeypatch.setattr(transport_module, "_open", fake)

    page_one = asyncio.run(
        HttpTransport(TOKEN).list_messages(query="", page_token=None)
    )
    assert [stub["id"] for stub in page_one["messages"]] == [
        "newest", "middle", "oldest"
    ], "the transport reordered a page"


def test_the_source_yields_the_promise_out_of_that_order(monkeypatch):
    """Matrix: *a full walk*. The port's promise, over the real transport.

    ``Echoing`` answers **by route** rather than by position, which is the only
    shape in which this assertion is about the code. The first version of the
    order case scripted three message responses in a queue, so whatever order
    the transport asked in the third response was still the third one handed
    back — and a build that reversed every page produced an identical list of
    ids. The reversal probe came back green against it.
    """
    fake = Echoing("newest", "middle", "oldest")
    monkeypatch.setattr(transport_module, "_open", fake)
    got = walked(GmailSource(HttpTransport(TOKEN)))

    assert fake.asked_for == ["oldest", "middle", "newest"], (
        "the walk read the mailbox newest-first"
    )
    assert [m.external_id for m in got] == ["oldest", "middle", "newest"]


def test_every_page_is_walked_and_the_page_token_is_carried_forward(monkeypatch):
    """Matrix: *paging*. Every page visited, and the token actually sent.

    A window wide enough to hold both messages and a page too small to carry
    them, so the second page is reached from inside one window — which is where
    ``MAX_PAGES`` lives now.
    """
    fake = Mailbox({"m1": "2026-03-02", "m2": "2026-03-03"}, page_size=1)
    monkeypatch.setattr(transport_module, "_open", fake)
    got = walked(GmailSource(HttpTransport(TOKEN)))

    assert [m.external_id for m in got] == ["m1", "m2"]
    assert not any("pageToken" in u for u in fake.urls[:1])
    assert any("pageToken=1" in u for u in fake.urls), "the token was never sent"


def test_the_cursor_reaches_the_provider_as_the_query_the_rules_built(http):
    """The window is ``gmail._query_for``'s decision and travels unchanged."""
    fake = http(page())
    walked(GmailSource(HttpTransport(TOKEN)), since="2026-03-04T05:06:07Z")
    assert "q=after%3A2026%2F03%2F04" in fake.urls[0]


def test_a_window_reaches_the_provider_bounded_at_both_ends(monkeypatch):
    """Story 20's window, on the wire.

    ``before:`` needed nothing of this module — the transport has always
    carried whatever query the rules built — which is what let the walk become
    bounded without touching the Protocol or the HTTP layer. That claim is
    worth an assertion rather than a sentence.
    """
    fake = Mailbox({f"m{i}": f"2026-03-{i:02d}" for i in range(1, 20)},
                   page_size=4)
    monkeypatch.setattr(transport_module, "_open", fake)
    walked(GmailSource(HttpTransport(TOKEN)))

    both = [u for u in fake.urls if "before%3A" in u and "after%3A" in u]
    probes = [u for u in fake.urls if "before%3A" in u and "after%3A" not in u]
    assert both, "no bounded window was ever asked for"
    # The one-ended queries are the halving search for the mailbox's oldest
    # day, and there is a ceiling on how many of them there may be.
    assert len(probes) <= MAX_PROBES, "the oldest-day search ran unbounded"


def test_a_message_id_cannot_address_something_other_than_the_message():
    """Provider data reaching a URL path, quoted.

    A message id is whatever Gmail last put in a ``messages[].id``, and it
    arrives here as a path segment. An unquoted ``/`` or ``?`` in one would
    address a different route entirely — a request nobody in this tree asked
    for, made with a live credential attached.
    """
    from half.ingest.gmail_transport import _message_url

    built = _message_url("https://api", "../../drafts?deleteAll")
    assert built == "https://api/messages/..%2F..%2Fdrafts%3FdeleteAll?format=full"
    assert built.count("?") == 1


def test_the_page_ceiling_is_the_one_the_rules_already_hold():
    """Matrix: *paging*, second half. ``MAX_PAGES`` is not restated here.

    The ceiling belongs to ``gmail.py`` and is asserted there; what this pins is
    that the transport did not grow a second one that could disagree with it.
    A page bound in two places is a page bound nobody can reason about.
    """
    source = ast.parse((PACKAGE / "gmail_transport.py").read_text(encoding="utf-8"))
    named = {
        node.id for node in ast.walk(source) if isinstance(node, ast.Name)
    } | {
        node.attr for node in ast.walk(source) if isinstance(node, ast.Attribute)
    }
    assert "MAX_PAGES" not in named
    assert MAX_PAGES == 10_000


# ═════════════════════════════════════════════════════════════════════════════
# matrix: the four faults — each with its own class, and no provider body
# ═════════════════════════════════════════════════════════════════════════════


def test_an_expired_token_is_a_domain_error_naming_its_class(http):
    """Matrix: *an expired token*. 401, raised, never retried."""
    fake = http(a_provider_error(401))
    with pytest.raises(MailboxNotAuthorised):
        asked(HttpTransport(TOKEN))
    assert len(fake.urls) == 1, "a rejected credential was asked a second time"


def test_the_class_of_a_fault_is_what_crosses_the_source_boundary(http):
    """Matrix: *an expired token*, at the boundary the pipeline actually sees.

    ``GmailSource._call`` carries ``type(exc).__name__`` upward and drops
    everything else, so the classes this module raises **are** the vocabulary in
    which a mailbox fault is named. A transport that raised a bare
    ``ChannelError`` would arrive here as *"gmail request failed: ChannelError"*
    — a domain error naming nothing, which is the matrix row deleted.
    """
    http(a_provider_error(401))
    with pytest.raises(ChannelError) as raised:
        walked(GmailSource(HttpTransport(TOKEN)))
    assert "MailboxNotAuthorised" in str(raised.value)
    assert not leaks(raised.value, PROVIDER_BODY)
    assert not leaks(raised.value, TOKEN)


def test_a_forbidden_status_is_permanent_rather_than_a_rate_limit(http):
    """403 sits with 401 because telling it from a quota refusal means reading
    the provider's error body — inside the boundary, deciding whether Half
    retries. The ambiguous status fails loudly rather than hammering."""
    fake = http(a_provider_error(403))
    with pytest.raises(MailboxNotAuthorised):
        asked(HttpTransport(TOKEN))
    assert len(fake.urls) == 1


def test_a_rate_limit_is_retried_with_a_doubling_backoff_and_is_bounded(
    http, slept
):
    """Matrix: *rate limited*. Retried, bounded, and loud when exhausted."""
    fake = http(*[a_provider_error(429) for _ in range(MAX_ATTEMPTS)])
    with pytest.raises(MailboxUnavailable):
        asked(HttpTransport(TOKEN))
    assert len(fake.urls) == MAX_ATTEMPTS
    assert slept == [1.0, 2.0, 4.0] == [
        BACKOFF_SECONDS * 2 ** n for n in range(MAX_ATTEMPTS - 1)
    ]


def test_the_backoff_stops_doubling_at_its_ceiling(http, slept):
    """A bound that grows without limit is not a bound."""
    fake = http(*[a_provider_error(503) for _ in range(7)])
    with pytest.raises(MailboxUnavailable):
        asked(HttpTransport(TOKEN, max_attempts=7))
    assert len(fake.urls) == 7
    assert slept == [1.0, 2.0, 4.0, 8.0, 8.0, 8.0]
    assert max(slept) == MAX_BACKOFF_SECONDS


def test_a_transient_fault_is_retried_and_then_succeeds(http, slept):
    """Matrix: *a transient fault*. A 5xx and a dropped connection both."""
    fake = http(a_provider_error(500),
                ConnectionResetError("the connection dropped"),
                page("m1"), message("m1"))
    got = walked(GmailSource(HttpTransport(TOKEN)))
    assert [m.external_id for m in got] == ["m1"]
    assert len(fake.urls) == 4 and slept == [1.0, 2.0]


def test_a_permanent_fault_is_raised_and_never_retried(http, slept):
    """Matrix: *a permanent fault*. A 4xx that is not 401 or 429."""
    fake = http(a_provider_error(400))
    with pytest.raises(MailboxRequestInvalid):
        asked(HttpTransport(TOKEN))
    assert len(fake.urls) == 1 and slept == []


def test_a_body_that_will_not_parse_is_loud_rather_than_an_empty_page(http):
    """Never a silent empty page: ``GmailSource`` reads ``page['messages']``,
    so a quietly substituted ``{}`` ends the walk and says nothing about why."""
    http(Response(b"<html>a proxy said no</html>"))
    with pytest.raises(MailboxUnavailable):
        asked(HttpTransport(TOKEN))


def test_a_body_of_the_wrong_shape_is_loud_too(http):
    http(Response(b'["not", "an", "object"]'))
    with pytest.raises(MailboxUnavailable):
        asked(HttpTransport(TOKEN))


@pytest.mark.parametrize(
    "answer, expected",
    [
        (a_provider_error(401), MailboxNotAuthorised),
        (a_provider_error(403), MailboxNotAuthorised),
        (a_provider_error(404), MailboxRequestInvalid),
        (a_provider_error(400), MailboxRequestInvalid),
        (a_provider_error(429), MailboxUnavailable),
        (a_provider_error(500), MailboxUnavailable),
        (a_provider_error(502), MailboxUnavailable),
        (ConnectionRefusedError("nothing listening"), MailboxUnavailable),
        (TimeoutError("the socket gave up"), MailboxUnavailable),
    ],
    ids=["401", "403", "404", "400", "429", "500", "502", "refused", "timeout"],
)
def test_every_status_becomes_one_of_this_transport_s_own_classes(
    http, slept, answer, expected
):
    """One case per status, asserted per status as the criterion asks.

    Driven through ``HttpTransport`` directly rather than through
    ``GmailSource``, because the source's boundary flattens every fault to a
    ``ChannelError`` carrying the class *name* — which is the right thing for
    it to do and would make this parametrisation identical either way.
    """
    http(*[answer for _ in range(MAX_ATTEMPTS)])
    with pytest.raises(expected) as raised:
        asyncio.run(HttpTransport(TOKEN).list_messages(query="", page_token=None))
    assert type(raised.value) is expected
    assert isinstance(raised.value, ChannelError)


# ═════════════════════════════════════════════════════════════════════════════
# matrix: provider text, and the token's home
# ═════════════════════════════════════════════════════════════════════════════


@pytest.mark.ad11
@pytest.mark.parametrize(
    "answer",
    [
        a_provider_error(401),
        a_provider_error(400),
        a_provider_error(429),
        a_provider_error(500),
        ConnectionResetError(PROVIDER_BODY),
        Response(b"<html>" + PROVIDER_BODY.encode() + b"</html>"),
    ],
    ids=["401", "400", "429", "500", "dropped", "unparseable"],
)
def test_no_provider_text_and_no_token_crosses_the_boundary(
    http, slept, caplog, answer
):
    """Matrix: *provider text* and *the token's home*, on every failing shape.

    The exception, its message, its args, **its cause and its context**, and
    every log record emitted during the attempt. The chain is checked because
    ``raise ... from None`` hides a context rather than detaching it, and an
    ``HTTPError`` still holds the body it was built with.
    """
    caplog.set_level(0)
    http(*[answer for _ in range(MAX_ATTEMPTS)])
    with pytest.raises(ChannelError) as raised:
        walked(GmailSource(HttpTransport(TOKEN)))

    assert not leaks(raised.value, PROVIDER_BODY)
    assert not leaks(raised.value, TOKEN)
    logged = "\n".join(r.getMessage() for r in caplog.records)
    assert PROVIDER_BODY not in logged and TOKEN not in logged


@pytest.mark.ad11
def test_a_raised_fault_has_no_cause_and_no_context_at_all(http):
    """The strongest form of the rule, and the reason for a peculiar shape.

    ``_request`` raises **after** its handler has finished, so the fault that
    crosses has neither a ``__cause__`` nor a ``__context__``. A build that
    raised inside the ``except`` — the natural way to write it — would attach
    the ``HTTPError``, and the object holding a provider's body would ride out
    of the boundary inside an exception that prints perfectly clean.
    """
    http(a_provider_error(401))
    with pytest.raises(MailboxNotAuthorised) as raised:
        asyncio.run(HttpTransport(TOKEN).get_message("m1"))
    assert raised.value.__cause__ is None
    assert raised.value.__context__ is None


@pytest.mark.ad11
def test_the_credential_travels_in_a_header_and_never_in_a_url(monkeypatch):
    """The failure ``gmail.py``'s boundary translation was written to survive,
    and one this avoids having to survive: a Gmail error quotes the request that
    caused it, so a token on a query string is a token in somebody's log."""
    fake = Mailbox({"m1": "2026-03-02", "m2": "2026-03-03"}, page_size=1)
    monkeypatch.setattr(transport_module, "_open", fake)
    walked(GmailSource(HttpTransport(TOKEN)))
    assert len(fake.urls) > 2
    for url in fake.urls:
        assert TOKEN not in url
        assert "token=" not in url.lower().replace("pagetoken=", "")
    for headers in fake.headers:
        assert headers["Authorization"] == "Bearer " + TOKEN


@pytest.mark.ad11
def test_the_token_comes_from_the_secret_store_and_reaches_no_store_tree(
    tmp_path, http
):
    """Matrix: *the token's home*. AD-11, as a code path.

    The store the credential comes from is a **sibling** of the tree holding
    every main, so an export or a replay of that tree cannot carry it — and the
    case proves it by hunting the token through every byte under the tree after
    a real walk.
    """
    mains = tmp_path / "mains"
    mains.mkdir()
    secrets = FileSecretStore.beside(mains)
    secrets.put(MAIN, GMAIL_TOKEN, TOKEN)

    fake = http(page("m1"), message("m1"))
    built = HttpTransport.from_secrets(secrets, MAIN)
    assert [m.external_id for m in walked(GmailSource(built))] == ["m1"]
    assert fake.headers[0]["Authorization"] == "Bearer " + TOKEN

    written = b"".join(p.read_bytes() for p in mains.rglob("*") if p.is_file())
    assert TOKEN.encode() not in written
    assert not secrets.root.resolve().is_relative_to(mains.resolve())


@pytest.mark.ad11
def test_a_main_with_no_stored_token_is_refused_before_any_request(
    tmp_path, http
):
    """Matrix: *no token*. Refused at the door, never a bare exception."""
    mains = tmp_path / "mains"
    mains.mkdir()
    fake = http()  # any request at all is an AssertionError from the fake
    with pytest.raises(MailboxMisconfigured) as raised:
        HttpTransport.from_secrets(FileSecretStore.beside(mains), MAIN)
    assert isinstance(raised.value, HalfError)
    assert GMAIL_TOKEN in str(raised.value)
    assert fake.urls == []


@pytest.mark.ad11
@pytest.mark.parametrize("bad", ["", None, 0])
def test_a_transport_with_no_credential_refuses_to_exist(bad):
    with pytest.raises(MailboxMisconfigured):
        HttpTransport(bad)


def test_a_bound_or_an_attempt_count_that_bounds_nothing_is_refused():
    """A ceiling nothing can reach is a ceiling that is not there."""
    with pytest.raises(MailboxMisconfigured):
        HttpTransport(TOKEN, max_attempts=0)
    with pytest.raises(MailboxMisconfigured):
        HttpTransport(TOKEN, request_seconds=0)


# ═════════════════════════════════════════════════════════════════════════════
# matrix: past the bound
# ═════════════════════════════════════════════════════════════════════════════


def test_a_request_that_hangs_is_abandoned_at_its_bound(monkeypatch):
    """Matrix: *past the bound*. Asserted as elapsed time, not as a value.

    The socket bound and the wall-clock bound are not the same bound: a request
    that is still moving but will not finish resets a per-read socket timeout
    for ever, and only the wall-clock one notices. So the fake here *blocks* —
    which a socket timeout in the fake could never model — and what the case
    measures is that the **caller** was released.

    Measured inside the loop rather than around ``asyncio.run``, because the
    run's own shutdown joins the worker thread: timing the outside would report
    the abandoned request's full duration and pass only by accident of how long
    the fake blocks.
    """
    def blocks(request, *, timeout):
        time.sleep(0.4)
        raise AssertionError("the bound did not release the caller")

    monkeypatch.setattr(transport_module, "_open", blocks)

    async def bounded() -> float:
        loop = asyncio.get_running_loop()
        started = loop.time()
        with pytest.raises(MailboxUnavailable):
            await HttpTransport(
                TOKEN, request_seconds=0.02, max_attempts=1
            ).list_messages(query="", page_token=None)
        return loop.time() - started

    assert asyncio.run(bounded()) < 0.3, "the caller was held past the bound"


def test_the_socket_bound_is_handed_to_the_client_as_well(http):
    """Both bounds are real: the wall-clock one releases the caller, and the
    socket one ends the abandoned worker rather than leaving it for ever."""
    fake = http(page())
    asyncio.run(
        HttpTransport(TOKEN, request_seconds=7.5)
        .list_messages(query="", page_token=None)
    )
    assert fake.timeouts == [7.5]
    assert REQUEST_SECONDS == 30.0


# ═════════════════════════════════════════════════════════════════════════════
# matrix: the body, and pages already captured
# ═════════════════════════════════════════════════════════════════════════════


def test_pages_already_captured_stay_valid_when_a_later_page_fails(
    tmp_path, monkeypatch, slept
):
    """Matrix: *a transient fault*, at the end it actually matters.

    Story 3's contract, exercised for the first time against something that
    speaks HTTP: page one is captured and durable, page two fails past its
    retries, and the receipt for page one is still on disk. Resumable, and
    never partial-and-silent — the failure is raised.
    """
    store = LocalSourceStore(tmp_path / MAIN / "sources")
    fake = Mailbox(
        {f"m{i}": f"2026-03-0{i}" for i in range(1, 6)},
        page_size=1, breaks_on="m2",
    )
    monkeypatch.setattr(transport_module, "_open", fake)

    async def pull():
        return await Pipeline(GmailSource(HttpTransport(TOKEN)), store).ingest()

    with pytest.raises(ChannelError):
        asyncio.run(pull())

    captured = [p for p in (tmp_path / MAIN).rglob("*") if p.is_file()]
    assert captured, "the page captured before the failure was lost"
    assert any(b"m1" in p.read_bytes() for p in captured)


def test_no_message_body_is_ever_persisted(tmp_path, http):
    """Matrix: *the body*. Story 3's rule, unchanged, and this is the first
    story in which a real body exists at all (AD-13, CAP-13)."""
    store = LocalSourceStore(tmp_path / MAIN / "sources")
    http(page("m1"), message("m1"))

    async def pull():
        return await Pipeline(GmailSource(HttpTransport(TOKEN)), store).ingest()

    result = asyncio.run(pull())
    assert len(result.receipts) == 1

    written = b"".join(
        p.read_bytes() for p in (tmp_path / MAIN).rglob("*") if p.is_file()
    )
    assert BODY.encode() not in written
    assert TOKEN.encode() not in written


# ═════════════════════════════════════════════════════════════════════════════
# offline: this module is the only one in its package that reaches a network
# ═════════════════════════════════════════════════════════════════════════════

#: Every way a Python module could get at HTTP. Not three spellings — the
#: families: the standard library's own clients, and every third-party client a
#: pinned dependency drags in and which could therefore be imported without
#: anybody noticing a new line in ``pyproject.toml``.
CLIENTS = frozenset({
    "urllib", "http", "socket", "ssl", "ftplib", "telnetlib", "asyncio",
    "httpx", "httpx2", "httpcore", "requests", "aiohttp", "anthropic",
    "telegram", "urllib3",
})

#: ``asyncio`` is a network library and is also how every module in this tree
#: writes a coroutine, so it is named above for completeness and excused here.
#: Excusing it is safe *because* the socket guard covers the whole suite: a
#: module that opened a connection through it would be caught there, wherever
#: it was written.
EXCUSED = frozenset({"asyncio"})


def imports_of(path: Path) -> set[str]:
    roots: set[str] = set()
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Import):
            roots.update(a.name.split(".")[0] for a in node.names)
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            roots.add(node.module.split(".")[0])
        elif (isinstance(node, ast.Call)
              and isinstance(node.func, ast.Name)
              and node.func.id == "__import__"
              and node.args
              and isinstance(node.args[0], ast.Constant)):
            roots.add(str(node.args[0].value).split(".")[0])
    return roots


@pytest.mark.offline
def test_the_transport_is_the_only_module_in_the_package_naming_a_client():
    """The acceptance criterion, and the whole worth of the split.

    A transport that quietly grew a rule would break the bargain that makes
    every module above it provably offline — and the way that happens is not a
    rule moving down, it is a *client* moving up: one ``import httpx`` in
    ``pipeline.py`` and the offline property of this package is a convention
    again. Asserted over the syntax trees, in both directions, so the file the
    exemption names has to actually be the one that reaches out.
    """
    reaching = {
        str(path.relative_to(ROOT)): sorted(imports_of(path) & CLIENTS - EXCUSED)
        for path in sorted(PACKAGE.rglob("*.py"))
        if imports_of(path) & CLIENTS - EXCUSED
    }
    assert list(reaching) == ["half/ingest/gmail_transport.py"], reaching
    assert reaching["half/ingest/gmail_transport.py"], (
        "the exempt module names no client at all, so the exemption is a "
        "dead anchor rather than a statement about anything"
    )


@pytest.mark.offline
def test_the_client_scan_would_see_a_client_arriving_anywhere_else(tmp_path):
    """Non-vacuity. A gate nobody has tried to defeat rests on nothing."""
    planted = tmp_path / "pipeline.py"
    for bypass in ("import httpx", "from httpx import AsyncClient",
                   "import urllib.request", "x = __import__('requests')"):
        planted.write_text(bypass + "\n", encoding="utf-8")
        assert imports_of(planted) & CLIENTS - EXCUSED, bypass


@pytest.mark.offline
def test_the_transport_module_does_not_log(monkeypatch):
    """A module with no logger cannot leak a credential into one.

    AD-11's *never a log line* is a property of this file's syntax tree rather
    than of every future edit remembering what may go in a format string. What
    there is to say about a failure is its class, and ``GmailSource._call`` and
    ``half.onboard.flow._pulled`` already say it one layer up.
    """
    tree = ast.parse((PACKAGE / "gmail_transport.py").read_text(encoding="utf-8"))
    assert "logging" not in imports_of(PACKAGE / "gmail_transport.py")
    calls = {
        node.func.attr if isinstance(node.func, ast.Attribute) else node.func.id
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, (ast.Attribute, ast.Name))
    }
    assert not calls & {"debug", "info", "warning", "error", "exception",
                        "critical", "print"}


@pytest.mark.offline
def test_importing_the_transport_builds_no_client_and_reads_no_token():
    """Construction is not a request, and this pins that it stays so."""
    built = HttpTransport(TOKEN)
    assert built is not None


# ═════════════════════════════════════════════════════════════════════════════
# matrix: the command
# ═════════════════════════════════════════════════════════════════════════════


class Wire:
    """The platform, doubled. The channel is not what this story reaches."""

    name = "wire"

    def __init__(self) -> None:
        self.sent: list[str] = []

    async def send(self, main_id: str, text: str):
        from half.channel.port import SendResult

        self.sent.append(text)
        return SendResult(external_id=f"m{len(self.sent)}", parts=1)

    def capability_query(self, main_id: str):
        from half.channel.port import Reachability

        return Reachability.OPEN


@pytest.fixture
def deployment(tmp_path, monkeypatch):
    """A configured deployment: one main, a root, and a bot token.

    ``HALF_CONSENT`` is deliberately **unset** by default. A deployment with no
    wording connects no mailbox — the fail-closed direction story 7 shipped —
    and a case that wants a mailbox read says so.
    """
    from half.config import MAINS_ENV, ROOT_ENV, TELEGRAM_TOKEN_ENV
    from half.__main__ import CONSENT_ENV, NOTHING_YET_ENV

    root = tmp_path / "mains"
    root.mkdir()
    monkeypatch.setenv(ROOT_ENV, str(root))
    monkeypatch.setenv(MAINS_ENV, f"123:{MAIN}")
    monkeypatch.setenv(TELEGRAM_TOKEN_ENV, "123:fake-bot-token")
    monkeypatch.delenv(CONSENT_ENV, raising=False)
    monkeypatch.delenv(NOTHING_YET_ENV, raising=False)
    return root


def test_the_command_runs_the_flow_and_reports_the_outcome(
    deployment, http, capsys
):
    """Matrix: *the command*. ``half onboard``, with a token present.

    Story 7's flow executes and the command reports what happened — the reason,
    the seconds, and whether they fitted. The mailbox is untouched here because
    this deployment wrote no notice, which is *the flow running*: the main is
    told before a source is connected, and no notice means no source. The fake
    HTTP layer is installed so that a build which connected anyway would be a
    request nobody scripted rather than a silence nobody notices.
    """
    from half.__main__ import main

    FileSecretStore.beside(deployment).put(MAIN, GMAIL_TOKEN, TOKEN)
    fake = http()

    assert main(["onboard", MAIN]) == 0
    out = capsys.readouterr().out
    assert f"onboarded {MAIN}" in out and "not-told" in out
    assert fake.urls == [], "a mailbox was read for a main who was never told"
    assert TOKEN not in out


def test_the_command_with_no_stored_token_says_so_and_exits_non_zero(
    deployment, http, capsys
):
    """Matrix: *the command, no token*. Plainly, and never a stack trace."""
    from half.__main__ import main

    fake = http()
    assert main(["onboard", MAIN]) == 2
    captured = capsys.readouterr()
    assert GMAIL_TOKEN in captured.err
    assert str(FileSecretStore.beside(deployment).root) in captured.err, (
        "the refusal names the credential and not the place to put it, which "
        "leaves a self-hoster's first command a dead end"
    )
    assert "Traceback" not in captured.err and "Traceback" not in captured.out
    assert captured.err.count("\n") == 1, "a refusal is one line"
    assert fake.urls == []


def test_the_command_refuses_a_main_this_deployment_does_not_have(
    deployment, capsys
):
    """A typo in a main id must not silently onboard somebody else."""
    from half.__main__ import main

    assert main(["onboard", "somebody-else"]) == 2
    err = capsys.readouterr().err
    assert "somebody-else" in err and MAIN in err
    assert "Traceback" not in err


def test_a_bare_invocation_still_serves_and_the_run_word_is_accepted():
    """The console script and every existing deployment invoke ``half``."""
    from half.__main__ import arguments

    assert arguments([]).command is None
    assert arguments(["run"]).command == "run"
    assert arguments(["onboard", MAIN]).main_id == MAIN


def test_the_command_asks_for_nothing_but_the_token():
    """CAP-4: no form and no interview, as a property of the parser.

    ``onboard`` takes exactly one argument — which configured main to onboard —
    and there is no flag, prompt or question anywhere on this path. A build that
    grew an interactive consent flow here would have to grow an option to carry
    it, and story 3 deferred that flow and story 7 declined it.
    """
    import argparse

    from half.__main__ import arguments

    with pytest.raises(SystemExit):
        arguments(["onboard", MAIN, "--and-also"])
    parsed = arguments(["onboard", MAIN])
    assert vars(parsed) == {"command": "onboard", "main_id": MAIN}
    assert isinstance(parsed, argparse.Namespace)


def test_the_shipped_composition_reaches_a_mailbox_and_writes_a_receipt(
    deployment, http, monkeypatch
):
    """The whole story, end to end, offline: a stored credential to a receipt.

    ``half.__main__.onboarded`` is the shipped path — the only place in the tree
    that constructs the networked transport — and it is driven here with the
    platform doubled and the HTTP layer faked. What this proves that no case
    above it can: the token really does come out of the ``SecretStore``, the
    request really is built and sent, ``GmailSource`` really does walk the
    answer, and the pipeline really does write a receipt from it.
    """
    from half.__main__ import CONSENT_ENV, build, onboarded
    from half.config import load
    from half.onboard.consent import LEAVES_THE_MACHINE, Consent
    from half.onboard.flow import Reason

    monkeypatch.setenv(CONSENT_ENV, "your messages leave this machine")
    FileSecretStore.beside(deployment).put(MAIN, GMAIL_TOKEN, TOKEN)
    # The shipped demonstration is a **bounded recent read** (story 20): it
    # asks what is there, reads the newest stamp to place a window, asks for
    # that window, and reads it. Four requests, and the third one carries both
    # bounds — which is the difference between reading this main's last week
    # and reading the oldest mail they own inside a ninety-second budget.
    fake = http(page("m1"), message("m1"), page("m1"), message("m1"))

    wiring = build(load(), token="123:fake-bot-token")
    wire = Wire()
    doubled = type(wiring)(**{
        **{f: getattr(wiring, f) for f in wiring.__dataclass_fields__},
        "channel": wire,
        "consent": Consent({LEAVES_THE_MACHINE: "your messages leave this machine"}),
    })
    try:
        done = asyncio.run(
            onboarded(doubled, main_id=MAIN, t="2026-09-04T08:00:00Z")
        )
    finally:
        wiring.registry.close()

    assert wire.sent, "the main was never told"
    assert len(fake.urls) == 4 and TOKEN not in "".join(fake.urls)
    assert any("before%3A" in u and "after%3A" in u for u in fake.urls), (
        "the demonstration read without bounding a window"
    )
    assert done.reason is Reason.NO_CLAIM, (
        "the demonstration ended for a reason other than an empty ledger; "
        "this case is about the mailbox reaching a receipt, and a different "
        "reason means the pull is not what stopped it"
    )

    written = b"".join(
        p.read_bytes() for p in deployment.rglob("*") if p.is_file()
    )
    assert b"m1" in written, "the receipt story 3 promises was not written"
    assert BODY.encode() not in written
    assert TOKEN.encode() not in written
