"""The concrete Gmail transport — the only module here that touches a network.

Kept apart from ``gmail.py`` on purpose, and the precedents are
``half/model/anthropic_transport.py`` and ``half/channel/telegram_transport.py``:
the module above holds every rule that matters (the query a cursor becomes, the
page walk, ``MAX_PAGES``, what a message normalises to and what is skipped) and
is exercised offline against a fake; this file is the thin edge that turns a
request into HTTP.

**Being a separate module is what makes the offline property assertable.**
``half/ingest`` is provably free of an HTTP client in every module but this one,
and this one is constructed by nobody unless a deployment asks — see
``tests/test_gmail_transport.py``, which asserts exactly that over the package's
syntax trees. While an implementation sits beside its rules, the offline scan
can cover the rules and not the implementation.

**Nothing here decides anything, and that is the bargain.** A transport is the
easiest place in a codebase to hide a decision — a filter on what to fetch, a
silent skip of a malformed message, a default that changes what a run sees.
Every one of those belongs in ``gmail.py``, which is tested. What this file
does is: build a URL, attach the credential, read the bytes back, parse them as
JSON, and translate a fault into a class. It filters nothing, drops nothing,
reorders nothing and retries only the shapes that are transient by definition.

**The token never comes from a store tree** (AD-11). It comes from a
``SecretStore``, which lives beside the main's directory rather than inside it,
so a token cannot reach an export or a replay. ``from_secrets`` is that path,
and it is a code path rather than a sentence in a docstring. The credential
travels in a request *header* and never in a URL: ``gmail.py`` translates a
transport fault at its boundary precisely because a Gmail error carries the
request URL, and a URL carrying an access token is a token in a log.

**No text from the provider crosses this boundary** (AD-22). Gmail's error
bodies quote the request that caused them, so an error body is never read at
all — not decoded, not logged, not inspected to classify anything. A fault is
classified on its HTTP status alone, and what crosses is the *class*: the
exception types below, whose names ``GmailSource._call`` carries upward as
``type(exc).__name__`` and nothing else.

**This module does not log.** It has no value it could log that is not a token,
a provider body, or a status somebody above it already reports — and a module
with no logger cannot leak a credential into one. ``half.onboard.flow._pulled``
and ``GmailSource._call`` already report the class of a failure upward, which
is the whole of what there is to say.

**The HTTP client is the standard library's** — a deliberate choice, not an
oversight, and the reasoning is worth keeping. ``httpx`` is present in the lock
file, but only as a transitive dependency of ``python-telegram-bot``; the AD-2
gate (``tests/test_dependencies.py``) admits the runtime's imports against the
*declared* dependencies, so importing ``httpx`` here would either red-build CI
or require declaring a new runtime dependency, which is Ask First. Reaching it
through ``telegram.request.HTTPXRequest`` would make a mail source depend on
the chat channel's SDK — and that SDK is itself moving off ``httpx`` (the lock
already pulls ``httpcore`` for it on 3.14). ``urllib.request`` on a worker
thread adds nothing to the dependency set and is bounded the same way.
"""

from __future__ import annotations

import asyncio
import http.client
import json
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Final

from half.errors import ChannelError
from half.secrets import SecretStore

#: Where a main's mailbox credential lives in their ``SecretStore``. One name,
#: here, so that no caller can invent a second spelling of it.
#:
#: An **access** token, supplied out of band, which is story 3's own deferral
#: ("the token arrives already acquired") and story 7's, unchanged. Refreshing
#: one needs a client id, a client secret and the consent flow that both those
#: stories declined, so an expired credential is reported as a fault here
#: rather than silently renewed.
GMAIL_TOKEN: Final[str] = "gmail_access_token"

#: Gmail's REST v1 root for the authenticated user. ``me`` rather than an
#: address: the token names the mailbox, so nothing here has to be told which.
API_ROOT: Final[str] = "https://gmail.googleapis.com/gmail/v1/users/me"

#: The wall-clock bound on one request. Bounded like every other outward call:
#: a hung request is abandoned rather than allowed to hold a run for ever.
REQUEST_SECONDS: Final[float] = 30.0

#: How many times one request is attempted in total, transient shapes only.
MAX_ATTEMPTS: Final[int] = 4

#: The first backoff, doubled per attempt up to the ceiling below.
BACKOFF_SECONDS: Final[float] = 1.0
MAX_BACKOFF_SECONDS: Final[float] = 8.0


class MailboxMisconfigured(ChannelError):
    """The transport was wired without the credential it cannot run without.

    Deliberately **not** a refusal, on ``ModelMisconfigured``'s terms: nothing
    was asked of a provider and nothing declined. It is raised before any
    request is made, so a deployment with no token refuses at the door instead
    of producing a bare exception from inside a page walk.
    """


class MailboxNotAuthorised(ChannelError):
    """The mailbox rejected the credential.

    Its own class rather than a general fault, because an expired access token
    and a mailbox that is merely unreachable want opposite handling: one is
    fixed by supplying a new credential and the other by waiting. Never
    retried — a rejected credential is not rejected less on the second ask.
    """


class MailboxUnavailable(ChannelError):
    """The mailbox could not be reached, or failed transiently.

    Connection faults, timeouts, rate limits and server errors — and, since it
    is the *only* retryable class here, membership of it is what the retry loop
    reads. A response body that is not JSON is one of these too: it is loud
    rather than an empty page, which is what the story forbids outright.
    """


class MailboxRequestInvalid(ChannelError):
    """The mailbox will never accept this request.

    A build mistake wearing an HTTP status, separated from
    ``MailboxUnavailable`` for the reason ``ModelRequestInvalid`` is separated
    from ``ModelUnavailable``: the two want opposite handling, and a default
    that folded a permanent 4xx into a transient outage would retry a
    permanently broken request for ever.
    """


class HttpTransport:
    """``GmailTransport`` over Gmail's REST API, on the standard library.

    Constructing one opens nothing: a token is checked for presence, a root URL
    is stored, and no connection is made until a method is awaited.
    """

    def __init__(
        self,
        token: str,
        *,
        api_root: str = API_ROOT,
        request_seconds: float = REQUEST_SECONDS,
        max_attempts: int = MAX_ATTEMPTS,
    ) -> None:
        if not isinstance(token, str) or not token:
            raise MailboxMisconfigured(
                "no Gmail token. Supply one from the SecretStore, which lives "
                "beside a main's directory and never inside it (AD-11)"
            )
        if max_attempts < 1:
            raise MailboxMisconfigured(
                "a transport that may attempt nothing reaches no mailbox"
            )
        if request_seconds <= 0:
            raise MailboxMisconfigured(
                "a request bound of zero abandons every request before it is made"
            )
        self._token = token
        self._api_root = api_root.rstrip("/")
        self._request_seconds = float(request_seconds)
        self._max_attempts = int(max_attempts)

    @classmethod
    def from_secrets(
        cls, secrets: SecretStore, main_id: str, **kwargs: Any
    ) -> "HttpTransport":
        """Build from the store where a credential is allowed to live (AD-11).

        The one sanctioned way to get a token into this transport. A missing
        one is ``MailboxMisconfigured`` rather than a refusal, for the reason
        that class gives — and the store is asked per main, because that is how
        ``SecretStore`` is keyed and how a self-hoster's own mailbox reaches
        their own actor.
        """
        token = secrets.get(main_id, GMAIL_TOKEN)
        if not token:
            raise MailboxMisconfigured(
                f"main {main_id!r} has no {GMAIL_TOKEN} in the secret store"
            )
        return cls(token, **kwargs)

    async def list_messages(self, *, query: str, page_token: str | None) -> dict:
        """One page of message stubs, exactly as the provider ordered them.

        **The order is the provider's and this file does not touch it.** Gmail's
        list route offers no sort control and returns most-recent-first, and a
        walk that pages through it cannot be made oldest-first without buffering
        the whole mailbox. Reversing a page here would look like the port's
        *oldest first* and would not be it — page one still holds the newest
        block — so it would be a decision that hides a defect rather than fixes
        one. See this story's report; the rule belongs above, not here.
        """
        return await self._json(_list_url(self._api_root, query, page_token))

    async def get_message(self, message_id: str) -> dict:
        """One message, whole.

        ``format=full`` is stated rather than left to the provider's default
        because it is the shape ``gmail.normalize`` reads — headers and a parsed
        part tree. It is the most complete parsed form there is, so naming it
        narrows nothing about which messages a run sees.
        """
        return await self._json(_message_url(self._api_root, message_id))

    async def _json(self, url: str) -> dict:
        """One bounded, retried request, as a JSON object.

        Retries cover ``MailboxUnavailable`` and nothing else — the transient
        shapes by definition. A rejected credential and a permanently invalid
        request are raised on the first attempt, so no retry here can turn a
        refusal into a second round trip.
        """
        backoff = BACKOFF_SECONDS
        for attempt in range(self._max_attempts):
            try:
                raw = await self._bytes(url)
            except MailboxUnavailable:
                if attempt + 1 >= self._max_attempts:
                    raise
                await asyncio.sleep(backoff)
                backoff = min(backoff * 2, MAX_BACKOFF_SECONDS)
                continue
            return _parsed(raw)
        # Unreachable: the loop either returns or raises on its last attempt.
        # Present so that a future edit to the bound cannot fall out of the
        # loop and return a silent empty page.
        raise MailboxUnavailable("the mailbox was not reached within its bound")

    async def _bytes(self, url: str) -> bytes:
        """The response body, or a fault, within the wall-clock bound.

        Two bounds, and they are not the same one. ``urlopen``'s own timeout is
        a socket bound: it ends a request that has stopped moving. ``wait_for``
        is the wall-clock bound the matrix asks for: it abandons a request that
        is still moving but will not finish, which a per-read socket timeout
        never notices. The abandoned worker thread ends on its own socket bound
        shortly after, and the number of them is bounded by ``max_attempts``.
        """
        try:
            return await asyncio.wait_for(
                asyncio.to_thread(
                    _request, url, self._token, self._request_seconds
                ),
                self._request_seconds,
            )
        except TimeoutError:
            raise MailboxUnavailable(
                "the mailbox did not answer within the request bound"
            ) from None


def _list_url(api_root: str, query: str, page_token: str | None) -> str:
    """The list route for one page. Pure, so the contract is testable.

    ``q`` is passed through exactly as ``gmail._query_for`` built it, including
    empty — narrowing or widening a cursor's window is that function's decision
    and it has already made it. ``pageToken`` is omitted rather than sent empty,
    because an absent token is how the API spells *the first page*.
    """
    params = {"q": query}
    if page_token:
        params["pageToken"] = page_token
    return f"{api_root}/messages?{urllib.parse.urlencode(params)}"


def _message_url(api_root: str, message_id: str) -> str:
    """The route for one message. Pure, so the contract is testable.

    The id is quoted with no safe characters: it is provider data reaching a
    URL path, and an unquoted ``../`` or ``?`` in one would address something
    other than the message that was asked for.
    """
    quoted = urllib.parse.quote(str(message_id), safe="")
    return f"{api_root}/messages/{quoted}?format=full"


def _open(request: urllib.request.Request, *, timeout: float):
    """The one blocking call in this package. Nothing else opens a socket."""
    return urllib.request.urlopen(request, timeout=timeout)


def _request(url: str, token: str, seconds: float) -> bytes:
    """One HTTP GET, blocking, run on a worker thread.

    **The credential goes in a header and never in the URL.** A Gmail error
    quotes the request that caused it, so a token on a query string is a token
    in somebody's log — the failure ``gmail.py``'s own boundary translation was
    written to survive, and one this avoids having to survive at all.

    **Every fault is raised after the handler has finished**, so the raised
    exception has neither a ``__cause__`` nor a ``__context__`` pointing at a
    provider object. ``raise ... from None`` suppresses the *display* of a
    context but still attaches it, and the attached ``HTTPError`` is the object
    holding the body AD-22 forbids carrying (AD-22).
    """
    request = urllib.request.Request(
        url,
        method="GET",
        headers={
            # The scheme is concatenated rather than interpolated so that no
            # line in this file spells a whole credential-bearing header, which
            # is a shape the AD-11 tree scan refuses on sight — correctly, and
            # it should not have to make an exception for the one module whose
            # job is to send one.
            "Authorization": "Bearer " + token,
            "Accept": "application/json",
        },
    )
    fault: ChannelError | None = None
    try:
        with _open(request, timeout=seconds) as response:
            return response.read()
    except urllib.error.HTTPError as exc:
        # Closed without being read. The body is never decoded, never logged
        # and never consulted to classify anything: the status alone decides.
        exc.close()
        fault = _fault_for(exc.code)
    except (OSError, http.client.HTTPException):
        # Connection refused, reset, DNS failure, a socket timeout, a truncated
        # response. Transient by definition, and the class carries no detail of
        # which host or which request (AD-22).
        fault = MailboxUnavailable("the mailbox could not be reached")
    raise fault


def _fault_for(status: int) -> ChannelError:
    """An HTTP status as one of Half's own faults. Pure, and body-blind.

    The status is the whole input. A body is never read, so nothing here can
    depend on provider text — which is what makes *no provider text crosses the
    boundary* a property of this function's signature rather than of somebody
    remembering not to interpolate one.

    403 sits with 401 rather than with 429. Gmail spells some quota refusals
    403 as well, and telling those apart from a genuine permission failure
    means reading the error body's ``reason`` — provider text, inside the
    boundary, deciding whether Half retries. Treating the ambiguous status as
    permanent is the direction that fails loudly instead of hammering a
    mailbox that is answering correctly.
    """
    if status in (401, 403):
        return MailboxNotAuthorised("the mailbox rejected the credentials")
    if status == 429:
        return MailboxUnavailable("the mailbox is rate limiting this credential")
    if 500 <= status <= 599:
        return MailboxUnavailable("the mailbox failed transiently")
    return MailboxRequestInvalid(f"the mailbox refused this request (HTTP {status})")


def _parsed(raw: bytes) -> dict:
    """Response bytes as the object ``gmail.py`` reads. Loud, never empty.

    A body that will not decode, will not parse, or is not an object is a fault
    rather than an empty page: ``GmailSource`` reads ``page.get("messages")``,
    so a quietly substituted ``{}`` is a mailbox that ends its walk early and
    says nothing about why.
    """
    fault: ChannelError | None = None
    try:
        payload = json.loads(raw.decode("utf-8"))
    except (ValueError, UnicodeDecodeError):
        # The body is not carried into the message — a proxy's error page is
        # provider text like any other (AD-22).
        fault = MailboxUnavailable("the mailbox returned a body this build cannot read")
    else:
        if isinstance(payload, dict):
            return payload
        fault = MailboxUnavailable("the mailbox returned a body of the wrong shape")
    raise fault
