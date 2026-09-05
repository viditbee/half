"""A thin Gmail `MailSource` — the only module here that touches the network.

Deliberately thin, following `telegram_transport.py`: every rule that matters
lives in the pipeline and the scrubber and is exercised offline, while this is
the edge that turns those decisions into HTTP.

The token is **supplied**, not acquired. The interactive OAuth consent flow is
deferred: it needs a Google Cloud project and a verified consent screen before
it can be exercised at all, and bundling it would put an unrunnable dependency
in the middle of the safety-critical path.

The credential is held by whatever constructs the transport; nothing in this
module reads or stores one, and no token appears in any exception raised from
here — transport errors are translated at the boundary so a URL carrying an
access token cannot reach a log (AD-11, AD-22).

**The order the port promises is made here, in bounded windows** (story 20).
Gmail's list route offers no sort control and answers newest-first, so a walk
that yields the provider's own order yields the port's promise backwards — and
a pull that is cut, against a cursor that is a ``max()`` over what it saw,
loses every message behind the cut *for ever*, because ``after:`` will never
name them again. Sorting is not the fix: it means reading a whole mailbox
before the first yield, which is unbounded work and cannot live inside CAP-2's
ninety seconds.

So the walk is **forward over windows bounded at both ends**. Gmail's query
takes ``before:`` as well as ``after:``, and the transport already carries an
arbitrary query string, so a window costs the Protocol nothing. Each window is
listed to exhaustion — ids only, which is what keeps the buffer bounded — and
then drained oldest-first by walking the provider's own newest-first order
backwards. ``drained_through`` moves **only at the end of a window that was
drained**, so a cut mid-window costs a repeat and never history; the digest
already deduplicates a repeat, and nothing deduplicates a loss.

**Two reads, two questions, and they must not share a watermark.**
``GmailSource`` is CAP-3's forward walk through history. ``GmailRecent`` is
CAP-2's bounded read of the newest window, and it publishes no
``drained_through`` at all — a read that does not drain must never move the
history cursor, which is the half of story 20 that makes the other half safe.
"""

from __future__ import annotations

import base64
import binascii
import datetime as _dt
import logging
from typing import Any, AsyncIterator, Final, Iterable, Protocol

from half.errors import ChannelError
from half.ingest.port import Message

logger = logging.getLogger(__name__)

#: A page count no real mailbox walk exceeds. A provider echoing the same
#: nextPageToken would otherwise spin forever. Held per window, which is where
#: paging happens.
MAX_PAGES = 10_000

#: How wide one window of the forward walk is, in days.
#:
#: **Measured, not guessed** — ``tools/window_sim.py`` walks five years of
#: synthetic mailbox at four densities and reports what each width costs. The
#: trade has two ends and a week sits between them:
#:
#: * too wide and a window will not drain inside a caller's deadline, so
#:   ``drained_through`` never moves and the walk repeats for ever. A window
#:   holds ``density × width`` messages, and every one of them is a request.
#: * too narrow and a sparse mailbox spends its requests on empty weeks: the
#:   list call for a window with nothing in it is paid whether or not anything
#:   comes back.
#:
#: Over five years at four densities — a dormant mailbox at 0.2 messages a day,
#: an ordinary one at 5, a busy one at 40, a firehose at 200 — the cost in
#: requests per message ingested, and the size of the window that has to drain:
#:
#: ======= ============================ ==========================
#: width   requests per message         messages in the busiest one
#: ======= ============================ ==========================
#: 1 day   6.05 / 1.20 / 1.03 / 1.01    3 / 21 / 78 / 322
#: 7 days  1.77 / 1.03 / 1.01 / 1.01    5 / 59 / 346 / 1,550
#: 30 days 1.22 / 1.02 / 1.01 / 1.01    11 / 182 / 1,364 / 6,543
#: ======= ============================ ==========================
#:
#: A month is marginally cheaper per message and asks the firehose to drain six
#: and a half thousand messages before the cursor may move once — a window no
#: ninety-second budget, and few five-minute ones, will ever finish. A single
#: day drains in a handful of requests and charges the dormant mailbox six
#: requests for every message it holds, which is the mailbox least able to
#: afford them. Seven is where both ends are still cheap, and it is a week —
#: the unit a person's mail already arrives in.
WINDOW_DAYS: Final[int] = 7

#: A window count no real walk exceeds, for the same reason as ``MAX_PAGES``:
#: a bound that a correct run never reaches, so that an incorrect one stops.
MAX_WINDOWS: Final[int] = 10_000

#: The floor of the search that finds a mailbox's oldest day on a first walk.
#:
#: The Unix epoch and **not** the year Gmail launched, which was the first
#: spelling and is wrong: mail older than the service lives in it, imported
#: with its original date, and ``internalDate`` carries that date. A floor at
#: 2004 would have started the walk after such a message and never named it
#: again — this story's own defect, rebuilt out of a plausible constant. The
#: extra reach costs one probe, because the search halves.
MAILBOX_FLOOR: Final[str] = "1970-01-01"

#: How many probes that search may spend. It halves the interval each time and
#: the interval is decades, so a real answer costs about thirteen.
MAX_PROBES: Final[int] = 24

#: How many of the newest stamps the walk's horizon is taken from.
#:
#: **The horizon is a claim about the present, and one stamp is a claim nobody
#: checked.** Nothing here reads a clock (AD-30), so the only evidence that a
#: date is not in the future is that mail exists at or after it. A single
#: message stamped 2099 — clock skew, a broken sender, a forged header — would
#: otherwise become the end of the walk and drag the cursor past every real
#: message behind it, which is the loss this story exists to remove. Taking the
#: third-newest stamp instead costs a lag of two messages, which the digest
#: makes free, and it takes three lying stamps to move it.
HORIZON_SAMPLES: Final[int] = 3

#: How many messages the horizon probe may read to find those stamps. A
#: message with no ``internalDate`` yields none, so the probe needs slack — and
#: a bound, or a mailbox of dateless messages would be read whole.
HORIZON_PROBES: Final[int] = 6

#: Multipart nesting deeper than this is malformed, not merely unusual.
MAX_PART_DEPTH = 20


class GmailTransport(Protocol):
    """The network surface. Injected so the suite stays offline."""

    async def list_messages(self, *, query: str, page_token: str | None) -> dict:
        ...

    async def get_message(self, message_id: str) -> dict:
        ...


class GmailSource:
    """Walks a mailbox forward in bounded windows, oldest first (CAP-3).

    **What the walk publishes beyond the port.** ``drained_through`` is the end
    of the last window this walk drained — ground behind which nothing is left
    unread. ``half.ingest.pipeline`` advances its cursor to that and to nothing
    else, so a walk cut part-way through a window leaves the cursor exactly
    where it was and the next run re-reads the window rather than losing it.
    It is deliberately **not** on the ``MailSource`` Protocol: a source that
    publishes none is taken at its word that it drains what it yields, which is
    true of every in-memory source in this tree.

    The instance is reused across pulls, so ``fetch`` resets the watermark
    before it walks; a watermark left over from a previous pull would name
    ground this one has not covered.
    """

    name = "gmail"

    def __init__(
        self, transport: GmailTransport, *, window_days: int = WINDOW_DAYS
    ) -> None:
        self.transport = transport
        self.window_days = int(window_days)
        if self.window_days <= 0:
            # A window of no days never advances, so the walk would repeat one
            # instant for ever while looking like progress.
            raise ChannelError(
                f"a window of {window_days!r} days walks nothing forward"
            )
        #: The end of the last drained window, or None while none is drained.
        self.drained_through: str | None = None

    async def fetch(self, *, since: str | None = None) -> AsyncIterator[Message]:
        """Every message after ``since``, oldest first (the port's promise).

        Three shapes, and the first two are the cheap ones:

        1. **Nothing after the cursor.** One list call answers it, and the walk
           is over. This is the ordinary case for a mailbox already caught up.
        2. **One page after the cursor.** Then that page *is* the remainder,
           and there is nothing to window: the provider's order is walked
           backwards and the whole of it is drained in one go.
        3. **More than a page.** Only then is the mailbox large enough that a
           bounded walk is worth its requests, and the windows begin.
        """
        self.drained_through = None
        first = await self._list(query=_query_for(since))
        ids = _ids(first)
        if not ids:
            return

        if not first.get("nextPageToken"):
            ordered = list(reversed(ids))
            seen: list[str] = []
            for position, message_id in enumerate(ordered):
                message = await self._one(message_id)
                if message is None:
                    continue
                seen.append(message.t)
                if position == len(ordered) - 1:
                    self.drained_through = _forward(
                        since, _horizon_of(sorted(seen))
                    )
                yield message
            # Drained: every message the provider holds after ``since`` has
            # been handed over, so the whole of that ground is behind us.
            self.drained_through = _forward(since, _horizon_of(sorted(seen)))
            return

        stamps = await self._stamps(ids)
        if not stamps:
            # More than a page of mail and not one readable date among the
            # newest of it. Nothing here can place a window in time, and
            # guessing would be the fabricated "now" ``_iso_from_internal_date``
            # already refuses. The counts only (AD-22).
            logger.warning(
                "a mailbox answered with %d messages and no readable date "
                "among the newest %d; the walk cannot bound a window and "
                "nothing is read", len(ids), HORIZON_PROBES,
            )
            return

        # **How far the walk goes and how far the cursor may follow it are two
        # different numbers**, and collapsing them stalls the walk. ``last`` is
        # the newest stamp there is, because a walk that stopped short of it
        # would leave the newest messages unread *and* leave the cursor at the
        # same place next time — reading them never. ``horizon`` is the
        # corroborated stamp the cursor is clamped to, because one message
        # dated in 2099 must not take the cursor with it.
        last = stamps[-1][:10]
        horizon = _horizon_of(stamps)

        day = _day_of(since) or await self._next_day(after=MAILBOX_FLOOR, last=last)
        if day is None:
            return
        for _ in range(MAX_WINDOWS):
            end = _plus_days(day, self.window_days)
            # Clamped to the horizon, because a window's end is arithmetic and
            # the horizon is evidence. The last window of any walk reaches past
            # the newest message there is, and a cursor left in the future
            # would skip every message that arrives before it catches up.
            boundary = _forward(since, min(_start_of(end), horizon))
            window = await self._window_ids(after=day, before=end)
            ordered = list(reversed(window))
            for position, message_id in enumerate(ordered):
                message = await self._one(message_id)
                if message is None:
                    continue
                if position == len(ordered) - 1:
                    # **Before the last message of the window and not after
                    # it.** The consumer takes what is yielded and finishes
                    # with it before it can ask for anything else, so the
                    # window is drained the instant this hands over — while a
                    # generator learns nothing until it is *resumed*, and a
                    # walk cut on a window boundary is never resumed. Written
                    # after the loop instead, the one case the matrix calls
                    # *progress is kept* would keep none.
                    self.drained_through = boundary
                yield message
            # And again here, for the window that ends without a last message
            # to hang it on: an empty week, or one whose final messages would
            # not normalise. Both are drained; neither yields.
            self.drained_through = boundary
            if end > last:
                return
            if window:
                day = end
                continue
            # **An empty window is jumped, not stepped past.** A mailbox with a
            # three-year gap in it — a dormant account, or a message stamped
            # decades out that the horizon rightly refuses to trust — would
            # otherwise cost one list call per empty week between here and
            # there, and there can be thousands. The same halving search that
            # finds where a mailbox begins finds where its next message is, for
            # about fifteen requests however wide the gap.
            jumped = await self._next_day(after=end, last=last)
            if jumped is None:
                return
            day = max(jumped, end)

    async def _window_ids(self, *, after: str, before: str) -> list[str]:
        """One window's message ids, listed to exhaustion.

        Ids first and messages second, which is what keeps the buffer bounded:
        what is held before the first yield is a window's worth of identifiers,
        never a window's worth of bodies. The bodies are fetched one at a time
        and each is out of scope before the next arrives, exactly as before.
        """
        query = _query_for(after, before)
        ids: list[str] = []
        page_token: str | None = None
        seen_tokens: set[str] = set()

        for _ in range(MAX_PAGES):
            page = await self._list(query=query, page_token=page_token)
            ids.extend(_ids(page))
            page_token = page.get("nextPageToken")
            if not page_token or page_token in seen_tokens:
                break
            seen_tokens.add(page_token)
        return ids

    async def _window(self, *, after: str, before: str) -> AsyncIterator[Message]:
        """One window, drained oldest first. For a read that keeps no cursor."""
        async for message in self._by_id(
            await self._window_ids(after=after, before=before)
        ):
            yield message

    async def _by_id(self, ids: Iterable[str]) -> AsyncIterator[Message]:
        """The provider's own order, walked backwards.

        Gmail lists newest-first and offers no sort control, so the oldest
        message of a bounded set is the last id of its last page. Reversing is
        the whole of the ordering: no dates are compared, nothing is buffered
        but the ids, and a message that will not normalise is skipped as it
        always was.
        """
        for message_id in reversed(list(ids)):
            message = await self._one(message_id)
            if message is not None:
                yield message

    async def _one(self, message_id: str) -> Message | None:
        raw = await self._call(self.transport.get_message(message_id))
        return normalize(raw or {})

    async def _stamps(self, ids: Iterable[str]) -> list[str]:
        """The newest few stamps the provider holds, oldest of them first.

        Read from the newest ids offered, which is the first page of the query
        the walk is about to make. Costs a handful of message reads that the
        walk will make again on its way past them — the digest makes the repeat
        free, and a cursor that a single future-dated message can strand is not
        free at all.
        """
        stamps: list[str] = []
        for message_id in list(ids)[:HORIZON_PROBES]:
            raw = await self._call(self.transport.get_message(message_id))
            message = normalize(raw or {})
            if message is not None:
                stamps.append(message.t)
            if len(stamps) >= HORIZON_SAMPLES:
                break
        return sorted(stamps)

    async def _next_day(self, *, after: str, last: str) -> str | None:
        """The day of the earliest message in ``[after, last]``, or None.

        **One search, used at both ends of the same problem.** A first walk has
        no cursor and needs to know where the mailbox begins; a walk that meets
        an empty window needs to know where its mail resumes. Stepping a week
        at a time answers both, and charges a list call for every empty week
        crossed — while the gaps are measured in years. A first walk stepping
        up from ``MAILBOX_FLOOR`` would spend thousands of requests before
        reading anything at all, which under a caller's deadline is a first
        pull that reads nothing, every time it runs.

        Halving answers either in about fifteen, however wide the gap, and it
        is sound because the question is monotone: a range holding a message
        still holds one when its far end moves later.
        """
        low = _date(after)
        high = _date(last) + _dt.timedelta(days=1)
        if high <= low or not await self._any_between(after, high.isoformat()):
            return None
        for _ in range(MAX_PROBES):
            if (high - low).days <= 1:
                break
            middle = low + (high - low) // 2
            if await self._any_between(after, middle.isoformat()):
                high = middle
            else:
                low = middle
        return (high - _dt.timedelta(days=1)).isoformat()

    async def _any_between(self, after: str, before: str) -> bool:
        return bool(_ids(await self._list(query=_query_for(after, before))))

    async def _list(self, *, query: str, page_token: str | None = None) -> dict:
        page = await self._call(
            self.transport.list_messages(query=query, page_token=page_token)
        )
        return page or {}

    async def _call(self, awaitable):
        """Translate transport faults at the boundary.

        The original exception is dropped rather than chained: a Gmail HTTP
        error carries the request URL, which carries the access token.
        """
        try:
            return await awaitable
        except Exception as exc:  # noqa: BLE001 - translated deliberately
            raise ChannelError(f"gmail request failed: {type(exc).__name__}") from None


class GmailRecent:
    """The demonstration's bounded read: the newest window, oldest first.

    **A recent read and a forward walk are different questions**, and sharing
    one watermark between them is what turned a ninety-second demonstration
    into a permanent loss of history. CAP-2 asks *what has this person been
    doing lately*, answers it from the newest window, and is cut whenever the
    budget runs out — a read that never drains the mailbox and must therefore
    never claim to have.

    So ``drained_through`` is ``None`` and stays ``None``. The pipeline reads
    it, sees that no ground was drained, and leaves the history cursor exactly
    where it found it; what this read reached is reported instead as
    ``Ingested.read_through``, which is its own position and nothing else's.

    Oldest-first inside the window all the same. The window is bounded, so the
    order costs nothing here, and one ordering rule in this module is one rule
    to keep true.
    """

    name = "gmail"

    #: Never moves the history cursor. A class attribute rather than an
    #: instance one, so that no code path can be written that sets it.
    drained_through: Final[None] = None

    def __init__(
        self, transport: GmailTransport, *, window_days: int = WINDOW_DAYS
    ) -> None:
        self.source = GmailSource(transport, window_days=window_days)

    async def fetch(self, *, since: str | None = None) -> AsyncIterator[Message]:
        source = self.source
        first = await source._list(query=_query_for(since))
        ids = _ids(first)
        if not ids:
            return

        # **Bounded even when the mailbox is small**, which is not the obvious
        # choice and is the one that matters. One page holds a hundred
        # messages, and reading a hundred oldest-first under a ninety-second
        # cut spends the whole demonstration on the *oldest* mail a new main
        # has — the wrong week, read carefully. The history walk may take a
        # page as its window because nothing cuts it; this read may not.
        stamps = await source._stamps(ids)
        if not stamps:
            logger.warning(
                "a mailbox answered with no readable date among its newest "
                "messages; there is no recent window to read"
            )
            return

        # **Both ends of this window come from stamps, and from different
        # ones.** It reaches up to the newest message there is, because a
        # demonstration that omitted the two most recent things a person did
        # would be demonstrating the wrong week. It reaches back from the
        # *corroborated* stamp, so that one message dated in 2099 widens the
        # window rather than moving it somewhere there is no mail — a wide
        # window costs a bounded read some requests it was going to spend
        # anyway, and a misplaced one costs the whole demonstration.
        end = _plus_days(stamps[-1][:10], 1)
        start = _plus_days(_horizon_of(stamps)[:10], 1 - source.window_days)
        floor = _day_of(since)
        if floor and floor > start:
            start = floor
        async for message in source._window(after=start, before=end):
            yield message


def normalize(raw: dict[str, Any]) -> Message | None:
    """One Gmail API message to the port's `Message`, or None to skip.

    Module-level and pure, so the contract between this file and the pipeline
    is testable without a network — the failure mode story 2 taught: renaming a
    key here would otherwise leave every test green while Half silently
    ingested nothing.
    """
    payload = raw.get("payload") or {}
    headers = {
        str(h.get("name", "")).lower(): str(h.get("value", ""))
        for h in payload.get("headers", [])
    }
    body = _body_bytes(payload)
    if not body:
        return None

    stamp = _iso_from_internal_date(raw.get("internalDate"))
    if stamp is None:
        # Stamping "now" would drag the cursor forward to the present and
        # filter out every genuinely older message forever.
        return None

    return Message(
        external_id=str(raw.get("id", "")),
        thread_id=str(raw.get("threadId", "")),
        sender=headers.get("from", ""),
        subject=headers.get("subject", ""),
        body=body,
        t=stamp,
        headers=headers,
    )


def _decode_b64(data: str) -> bytes:
    """Pad to a multiple of four and validate.

    Without ``validate=True`` the decoder silently drops characters outside
    the alphabet, so malformed data yields plausible-looking bytes rather than
    an error — and a corrupt part would be scanned as if it were text.
    """
    # urlsafe_b64decode has no validate flag, so translate the alphabet and
    # use the strict decoder.
    standard = data.translate(str.maketrans("-_", "+/"))
    return base64.b64decode(standard + "=" * (-len(standard) % 4), validate=True)


def _query_for(since: str | None, before: str | None = None) -> str:
    """A window, bounded at either end or both. Gmail takes YYYY/MM/DD.

    Half-open by Gmail's own reading — ``after:`` includes the day it names and
    ``before:`` excludes it — which is what lets windows tile without a gap and
    without an overlap: the day one window ends on is the day the next begins.

    A malformed cursor must not silently widen or narrow the window, so it is
    refused rather than passed through. The date is parsed and not merely
    shaped: ``2026-13-45`` has the shape and names no day, and a query built
    from it is a window whose bounds are the provider's guess.
    """
    terms = []
    if since:
        terms.append(f"after:{_day_of(since).replace('-', '/')}")
    if before:
        terms.append(f"before:{_day_of(before).replace('-', '/')}")
    return " ".join(terms)


def _day_of(value: str | None) -> str | None:
    """The ``YYYY-MM-DD`` a cursor names, or None for no cursor."""
    if not value:
        return None
    head = str(value)[:10]
    try:
        return _date(head).isoformat()
    except ValueError:
        raise ChannelError(f"cursor is not an ISO-8601 date: {value!r}") from None


def _date(day: str) -> _dt.date:
    return _dt.date.fromisoformat(day)


def _plus_days(day: str, days: int) -> str:
    return (_date(day) + _dt.timedelta(days=days)).isoformat()


def _start_of(day: str) -> str:
    """A day as the instant it begins, in the shape every stored stamp has."""
    return f"{day}T00:00:00Z"


def _ids(page: dict[str, Any]) -> list[str]:
    """The message ids of one page, in the provider's own order."""
    return [
        str(stub["id"])
        for stub in (page.get("messages") or [])
        if stub and stub.get("id")
    ]


def _horizon_of(ascending: list[str]) -> str | None:
    """The ``HORIZON_SAMPLES``-th newest of some stamps, or the oldest of few.

    With fewer stamps than samples there is nothing to corroborate with, so the
    oldest is taken: it is the most conservative claim the evidence supports,
    and being conservative here costs a repeat rather than a mailbox.
    """
    if not ascending:
        return None
    return ascending[-min(HORIZON_SAMPLES, len(ascending))]


def _forward(since: str | None, value: str | None) -> str | None:
    """A watermark only ever moves forward, and never off the end of nothing.

    ``after:`` is day-granular, so a walk resumed from a cursor can be handed a
    message stamped earlier in the cursor's own day. Taking it would move the
    cursor backwards and re-read ground already behind us for ever.
    """
    if value is None:
        return since
    if since is None or value > since:
        return value
    return since


def _body_bytes(payload: dict[str, Any], depth: int = 0) -> bytes:
    """The first readable text part, walking multipart recursively.

    Returns raw bytes rather than text: whether it decodes is the scrubber's
    question, and a part that will not decode must be treated as a finding
    rather than dropped here.
    """
    if depth > MAX_PART_DEPTH:
        return b""
    mime = str(payload.get("mimeType", ""))
    data = (payload.get("body") or {}).get("data")
    if data and mime.startswith("text/"):
        try:
            return _decode_b64(str(data))
        except (binascii.Error, ValueError):
            # Malformed base64 is one bad message, not a reason to abort the
            # whole run.
            return b""
    for part in payload.get("parts") or []:
        found = _body_bytes(part or {}, depth + 1)
        if found:
            return found
    return b""


def _iso_from_internal_date(value: Any) -> str | None:
    """Gmail's internalDate is epoch milliseconds as a string, or None.

    Returns None rather than falling back to the clock: the caller advances a
    cursor from these timestamps, so a fabricated "now" permanently skips
    every older message. It would also break the port's stated invariant that
    nothing downstream reads a clock.
    """
    try:
        stamp = _dt.datetime.fromtimestamp(int(value) / 1000, _dt.UTC)
    except (TypeError, ValueError, OverflowError, OSError):
        return None
    return stamp.replace(microsecond=0).isoformat().replace("+00:00", "Z")
