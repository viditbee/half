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

**A listing that did not finish is not a window that drained.** A page bound
reached, or a provider echoing one page token for ever, leaves the *oldest*
ids of that window unnamed — Gmail lists newest-first, so the page that goes
missing is the one furthest back. Moving the watermark over that is this
story's own defect at window granularity, so it is not expressible: the
listing raises rather than returning what it has (story 3's vocabulary, and
the receipts written before it stay written).

**Every bound is a time, not a count of requests.** ``after:`` and ``before:``
are given as epoch seconds rather than as ``YYYY/MM/DD``, because Gmail's date
form is evaluated in *the mailbox's own timezone* while every stamp this module
reasons about — ``internalDate``, the cursor, the horizon — is UTC. A window
computed in UTC and evaluated thirteen hours away excludes messages the walk
then steps past, and the watermark would move over them regardless. The epoch
form is the same instant everywhere.

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

#: A page count no window's listing exceeds. A provider echoing the same
#: nextPageToken would otherwise spin forever. Reaching it is a fault and is
#: raised, never quietly treated as the end of the window.
MAX_PAGES: Final[int] = 10_000

#: How wide one window of the forward walk is, in days.
#:
#: **Measured, not guessed** — ``tools/window_sim.py`` runs the *shipped*
#: ``GmailSource`` over five years of synthetic mailbox at four densities and
#: counts the requests it actually makes, searches included. The trade has two
#: ends and a week sits between them:
#:
#: * too wide and a window will not drain inside a caller's deadline, so
#:   ``drained_through`` never moves and the walk repeats for ever. A window
#:   holds ``density × width`` messages, and every one of them is a request.
#: * too narrow and a sparse mailbox spends its requests on empty weeks: the
#:   list call for a window with nothing in it is paid whether or not anything
#:   comes back.
#:
#: The numbers are in ``tools/window_sim.py``'s own output and reproduced in
#: ``WINDOW_MEASUREMENT`` below, so that a change to the walk which moves them
#: is visible rather than folded into prose that stopped being true.
WINDOW_DAYS: Final[int] = 7

#: The measurement ``WINDOW_DAYS`` was chosen from, as data rather than prose.
#:
#: ``{width in days: {density: (requests per message, busiest window)}}`` from
#: ``tools/window_sim.py``, which drives **this walk** over a mailbox double and
#: counts what it actually asks for — searches, steps, pages and horizon probes
#: included. Densities are a dormant account at 0.2 messages a day, an ordinary
#: one at 5, a busy one at 40 and a firehose at 200; regenerate the table with
#: ``uv run python tools/window_sim.py``.
#:
#: **Read it at the two ends.** A month is the cheapest per message on the
#: sparse row (1.22 against a week's 1.72) and asks a firehose to drain six and
#: a half thousand messages before the cursor may move once — a window no
#: ninety-second budget and few five-minute ones will ever finish, which is the
#: failure that stops a walk making progress at all. A single day never holds
#: more than a few hundred and charges the dormant mailbox four and a half
#: requests for every message it has, which is the mailbox least able to afford
#: them. A week costs within a rounding of the best at three densities out of
#: four and holds a few hundred messages at the fourth. It is also the unit a
#: person's mail arrives in.
#:
#: What would move the answer: a batch seam that let a window drain in fewer
#: than one request per message (the busiest-window column stops mattering, and
#: wider wins), or a provider that answered oldest-first (windows stop being
#: needed at all).
WINDOW_MEASUREMENT: Final[dict[int, dict[str, tuple[float, int]]]] = {
    1: {"dormant": (4.51, 3), "ordinary": (1.17, 21),
        "busy": (1.02, 77), "firehose": (1.01, 317)},
    7: {"dormant": (1.72, 5), "ordinary": (1.03, 59),
        "busy": (1.01, 327), "firehose": (1.01, 1568)},
    14: {"dormant": (1.38, 8), "ordinary": (1.02, 103),
         "busy": (1.01, 628), "firehose": (1.01, 3104)},
    30: {"dormant": (1.22, 11), "ordinary": (1.01, 182),
         "busy": (1.01, 1340), "firehose": (1.01, 6661)},
}

#: A window count no real walk exceeds, for the same reason as ``MAX_PAGES``:
#: a bound that a correct run never reaches, so that an incorrect one stops.
#:
#: It is a count of *windows* and therefore a reach in time that moves with
#: ``window_days`` — seventy thousand days at the shipped width, and a tenth of
#: that at a width of one. A walk that reaches it says so and stops; it does
#: not move the watermark past ground it did not cover, so the next run
#: continues where this one left off.
MAX_WINDOWS: Final[int] = 10_000

#: The floor of the search that finds where a mailbox begins on a first walk.
#:
#: The Unix epoch, which is also the earliest instant Gmail's own timestamp
#: operators can name: they take epoch **seconds** and a negative one is not a
#: query. Mail stamped before 1970 is therefore out of this walk's reach — it
#: is also older than electronic mail, so the floor is a limit of the provider's
#: vocabulary rather than of this design.
MAILBOX_FLOOR: Final[str] = "1970-01-01T00:00:00Z"

#: How many probes the halving search may spend. It halves the interval each
#: time and the interval is decades, so a real answer costs about fifteen; a
#: search that leaves without converging says so.
MAX_PROBES: Final[int] = 24

#: How many consecutive empty windows before the walk stops stepping and
#: searches instead.
#:
#: **Measured, and the first spelling had it at one**, which made a dormant
#: mailbox *more* expensive rather than less: a halving search costs about
#: fifteen list calls and stepping one empty week costs one, so searching at
#: the first empty window charges fifteen requests to skip seven days. A gap of
#: years is where the search pays, and a month of silence is the cheapest
#: evidence that a gap is that kind.
EMPTY_BEFORE_SEARCH: Final[int] = 4

#: How many of the newest stamps the walk's horizon is corroborated against.
#:
#: **The horizon is a claim about the present, and one stamp is a claim nobody
#: checked.** Nothing here reads a clock (AD-30), so the only evidence that a
#: date is not in the future is that other mail sits near it. A single message
#: stamped 2099 — clock skew, a broken sender, a forged header — must not
#: become the end of the walk and drag the cursor past every real message
#: behind it, which is the loss this story exists to remove.
HORIZON_SAMPLES: Final[int] = 3

#: How far ahead of the next stamp down a stamp may sit and still be believed.
#:
#: The rule the samples feed: a stamp more than a year newer than the one below
#: it is an outlier and the horizon steps down to that one. **A lag, not a
#: rank** — an earlier spelling took the third-newest stamp outright, which
#: made a mailbox of three messages re-read all three for ever because the
#: horizon was always its oldest. Mail arrives in clusters; a year of daylight
#: between two of a mailbox's newest messages is a broken clock, not a habit.
SKEW_GAP_DAYS: Final[int] = 366

#: How many messages the horizon probe may read to find those stamps.
#:
#: A message with no ``internalDate`` yields no stamp, so the probe walks on —
#: **through pages, not only the first one**. It read six ids of one page
#: before, and a mailbox whose six newest messages were undated was never read
#: at all: not a loss, but a total outage repeated every run. The bound is
#: generous because it is only reached by a mailbox that is already strange,
#: and a bound there must be or a dateless mailbox is read whole.
HORIZON_PROBES: Final[int] = 50

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
    It is not on the ``MailSource`` Protocol, which promises an order and
    nothing about provenance; it is ``half.ingest.port.Draining``, a protocol
    of its own that the pipeline checks by ``isinstance`` — so a rename here
    fails a case instead of silently restoring the ``max()`` cursor this story
    removed.

    ``fetch`` resets the watermark **when it is called**, not when the walk it
    returns is first driven: a generator that is built and abandoned would
    otherwise leave a watermark naming ground the next pull has not covered.
    One instance walks one mailbox at a time; two overlapping walks over one
    source share the watermark and neither one's is meaningful.
    """

    name = "gmail"

    def __init__(
        self, transport: GmailTransport, *, window_days: int = WINDOW_DAYS
    ) -> None:
        self.transport = transport
        try:
            self.window_days = int(window_days)
        except (TypeError, ValueError):
            raise ChannelError(
                f"a window of {window_days!r} days is not a number of days"
            ) from None
        if self.window_days <= 0:
            # A window of no days never advances, so the walk would repeat one
            # instant for ever while looking like progress.
            raise ChannelError(
                f"a window of {window_days!r} days walks nothing forward"
            )
        #: The end of the last drained window, or None while none is drained.
        self.drained_through: str | None = None

    def fetch(self, *, since: str | None = None) -> AsyncIterator[Message]:
        """Every message after ``since``, oldest first (the port's promise).

        A plain function returning the walk rather than the walk itself, so
        that a malformed cursor is refused at the call and the watermark is
        cleared there too — an async generator body does not run until the
        first message is asked for, and a pull that is built and dropped would
        leave the last pull's watermark standing.
        """
        cursor = _instant(since)
        self.drained_through = None
        return self._walk(cursor)

    async def _walk(self, cursor: _dt.datetime | None) -> AsyncIterator[Message]:
        """Three shapes, and the first two are the cheap ones.

        1. **Nothing after the cursor.** One list call answers it, and the walk
           is over. This is the ordinary case for a mailbox already caught up.
        2. **One page after the cursor.** Then that page *is* the remainder,
           complete by the provider's own account, and there is nothing to
           window: it is walked backwards and drained in one go.
        3. **More than a page.** Only then is the mailbox large enough that a
           bounded walk is worth its requests, and the windows begin.
        """
        floor = _stamp(cursor) if cursor else None
        query = _query_for(cursor)
        first = await self._list(query=query)
        ids = _ids(first)
        if not ids:
            return

        if not first.get("nextPageToken"):
            seen: list[str] = []
            async for message, last_of in self._handed(ids):
                seen.append(message.t)
                if last_of:
                    self.drained_through = _forward(floor, _horizon_of(sorted(seen)))
                yield message
            # Drained: every message the provider holds after the cursor has
            # been handed over, so the whole of that ground is behind us.
            #
            # **The horizon comes from every stamp here and from a probe of the
            # newest few below**, which is one rule over two inputs rather than
            # two rules: this path has read the whole remainder, so it knows
            # every stamp; the windowed path has read only the newest page and
            # cannot afford to read more before it starts.
            self.drained_through = _forward(floor, _horizon_of(sorted(seen)))
            return

        stamps = await self._stamps(query=query, first=first)
        if not stamps:
            # More than a page of mail and not one readable date in the first
            # fifty of it. Nothing here can place a window in time, and
            # guessing would be the fabricated "now" ``_iso_from_internal_date``
            # already refuses. The counts only (AD-22).
            logger.warning(
                "a mailbox answered with %d messages on its first page and no "
                "readable date within %d reads; the walk cannot bound a window "
                "and nothing is read", len(ids), HORIZON_PROBES,
            )
            return

        # **How far the walk goes and how far the cursor may follow it are two
        # different numbers**, and collapsing them stalls the walk. ``last`` is
        # the newest stamp there is, because a walk that stopped short of it
        # would leave the newest messages unread *and* leave the cursor at the
        # same place next time — reading them never. ``horizon`` is the
        # corroborated stamp the cursor is clamped to, because one message
        # dated in 2099 must not take the cursor with it.
        last = _instant(stamps[-1])
        horizon = _horizon_of(stamps)

        start = cursor or await self._next_mail(after=_instant(MAILBOX_FLOOR), last=last)
        if start is None:
            return

        empty = 0
        for _ in range(MAX_WINDOWS):
            end = _plus(start, self.window_days)
            # Clamped to the horizon, because a window's end is arithmetic and
            # the horizon is evidence. The last window of any walk reaches past
            # the newest message there is, and a cursor left in the future
            # would skip every message that arrives before it catches up.
            boundary = _forward(floor, min(_stamp(end), horizon))
            window = await self._window_ids(after=start, before=end)
            async for message, last_of in self._handed(window):
                if last_of:
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
                empty, start = 0, end
                continue
            empty += 1
            if empty < EMPTY_BEFORE_SEARCH:
                start = end
                continue
            # **A gap of years is searched, a gap of weeks is stepped.** The
            # halving search below crosses any distance for about fifteen
            # requests, and stepping crosses one week for one — so searching at
            # the first empty window makes a dormant mailbox dearer, not
            # cheaper, and a month of silence is the cheapest evidence that
            # this gap is the other kind.
            found = await self._next_mail(after=end, last=last)
            if found is None:
                return
            empty, start = 0, max(found, end)
        else:
            logger.warning(
                "a walk stopped after %d windows of %d days without reaching "
                "the end of the mailbox; the cursor stands where it drained "
                "and the next pull continues from there",
                MAX_WINDOWS, self.window_days,
            )

    async def _handed(
        self, ids: Iterable[str]
    ) -> AsyncIterator[tuple[Message, bool]]:
        """The provider's own order walked backwards, and which one is last.

        Gmail lists newest-first and offers no sort control, so the oldest
        message of a bounded set is the last id of its last page. Reversing is
        the whole of the ordering: no dates are compared, nothing is buffered
        but the ids, and a message that will not normalise is skipped as it
        always was.

        The flag is what lets a caller move a watermark **before** handing over
        the message that completes a window rather than after it. It is the
        last *id*, not the last message: if that id will not normalise the flag
        never comes, which is why every caller also marks after the loop.
        """
        ordered = list(reversed(list(ids)))
        for position, message_id in enumerate(ordered):
            message = await self._one(message_id)
            if message is None:
                continue
            yield message, position == len(ordered) - 1

    async def _window_ids(
        self, *, after: _dt.datetime, before: _dt.datetime
    ) -> list[str]:
        """One window's message ids, listed to exhaustion — or an error.

        Ids first and messages second, which is what keeps the buffer bounded:
        what is held before the first yield is a window's worth of identifiers,
        never a window's worth of bodies. The bodies are fetched one at a time
        and each is out of scope before the next arrives, exactly as before.

        **A listing that did not finish raises**, and that is the point of this
        function existing at all. Returning the ids it had would hand back the
        *newest* part of the window with the oldest page missing, and the caller
        would then mark the window drained — the cursor stepping over messages
        no later query can name, which is this story's own defect rebuilt one
        level down. Raised as a domain error, so the receipts already written
        stay written and the run is resumable (story 3's vocabulary, unchanged).
        """
        query = _query_for(after, before)
        ids: list[str] = []
        page_token: str | None = None
        seen_tokens: set[str] = set()

        for _ in range(MAX_PAGES):
            page = await self._list(query=query, page_token=page_token)
            ids.extend(_ids(page))
            page_token = page.get("nextPageToken")
            if not page_token:
                return ids
            if page_token in seen_tokens:
                raise ChannelError(
                    "gmail repeated one page token while listing a window, so "
                    "the oldest part of it was never named"
                )
            seen_tokens.add(page_token)
        raise ChannelError(
            f"gmail did not finish listing a window within {MAX_PAGES} pages, "
            "so the oldest part of it was never named"
        )

    async def _stamps(self, *, query: str, first: dict) -> list[str]:
        """The newest few stamps the provider holds, oldest of them first.

        Read from the newest ids offered, and **through pages rather than the
        first one only**: a mailbox whose newest messages have no
        ``internalDate`` has no readable date on page one, and reading only
        that page left every mailbox behind such a run unread for ever. The
        walk pays for those reads again on its way past them — the digest makes
        the repeat free — and a horizon a single stamp can move is not free at
        all.
        """
        stamps: list[str] = []
        reads = 0
        page = first
        seen_tokens: set[str] = set()

        for _ in range(MAX_PAGES):
            for message_id in _ids(page):
                if len(stamps) >= HORIZON_SAMPLES or reads >= HORIZON_PROBES:
                    return sorted(stamps)
                message = await self._one(message_id)
                reads += 1
                if message is not None:
                    stamps.append(message.t)
            token = page.get("nextPageToken")
            if not token or token in seen_tokens:
                # A best-effort probe, so a repeated token ends it rather than
                # raising: nothing here claims to have listed anything
                # completely, and what it hands back is a horizon, not a window.
                break
            seen_tokens.add(token)
            page = await self._list(query=query, page_token=token)
        return sorted(stamps)

    async def _next_mail(
        self, *, after: _dt.datetime, last: _dt.datetime
    ) -> _dt.datetime | None:
        """The day the earliest message in ``[after, last]`` lands on, or None.

        **One search, used at both ends of the same problem.** A first walk has
        no cursor and needs to know where the mailbox begins; a walk that has
        crossed a month of nothing needs to know where its mail resumes.
        Stepping answers both, and charges a list call for every empty week
        crossed — while these gaps are measured in years. A first walk stepping
        up from ``MAILBOX_FLOOR`` would spend thousands of requests before
        reading anything at all, which under a caller's deadline is a first
        pull that reads nothing, every time it runs.

        Halving answers either in about fifteen, however wide the gap, and it
        is sound because the question is monotone: a range holding a message
        still holds one when its far end moves later.
        """
        low, high = after, _plus(_floor_day(last), 1)
        if high <= low or not await self._any_between(after, high):
            return None

        # The invariant both ends carry: nothing lies in ``(after, low]`` and
        # something lies in ``(after, high]``. **``low`` is what is returned**,
        # never ``high`` stepped back a day: a bound arrived at by halving is
        # not day-aligned, so *a day before the first range known to hold mail*
        # can land after the message itself — measured, and it skipped one.
        # ``low`` is the last point proven to have nothing behind it, so a walk
        # resuming there is early at worst and never late.
        probes = 0
        while probes < MAX_PROBES:
            middle = _floor_day(low + (high - low) / 2)
            if middle <= low or middle >= high:
                break
            probes += 1
            if await self._any_between(after, middle):
                high = middle
            else:
                low = middle
        if probes >= MAX_PROBES:
            logger.warning(
                "a search for the next mail in a mailbox spent its %d probes "
                "without converging; the walk resumes up to %d days early, "
                "which costs requests and loses nothing",
                MAX_PROBES, (high - low).days,
            )
        return low

    async def _any_between(self, after: _dt.datetime, before: _dt.datetime) -> bool:
        return bool(_ids(await self._list(query=_query_for(after, before))))

    async def _list(self, *, query: str, page_token: str | None = None) -> dict:
        page = await self._call(
            self.transport.list_messages(query=query, page_token=page_token)
        )
        return page or {}

    async def _one(self, message_id: str) -> Message | None:
        raw = await self._call(self.transport.get_message(message_id))
        return normalize(raw or {})

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

    So ``drained_through`` is ``None``, from a property with no setter: the
    pipeline reads it, sees that no ground was drained, and leaves the history
    cursor exactly where it found it. What this read reached is reported
    instead as ``Ingested.read_through``, which is its own position and nothing
    else's.

    Oldest-first inside the window all the same. The window is bounded, so the
    order costs nothing here, and one ordering rule in this module is one rule
    to keep true.

    It drives a ``GmailSource``'s own listing, paging and ordering rather than
    holding a second copy of them — two spellings of *how Gmail is walked* is
    how the two reads would come to disagree about what a window contains.
    """

    name = "gmail"

    def __init__(
        self, transport: GmailTransport, *, window_days: int = WINDOW_DAYS
    ) -> None:
        self.source = GmailSource(transport, window_days=window_days)

    @property
    def drained_through(self) -> None:
        """Never anything else. A property, so that no assignment can make it."""
        return None

    def fetch(self, *, since: str | None = None) -> AsyncIterator[Message]:
        return self._read(_instant(since))

    async def _read(self, cursor: _dt.datetime | None) -> AsyncIterator[Message]:
        source = self.source
        query = _query_for(cursor)
        first = await source._list(query=query)
        if not _ids(first):
            return

        # **Bounded even when the mailbox is small**, which is not the obvious
        # choice and is the one that matters. One page holds a hundred
        # messages, and reading a hundred oldest-first under a ninety-second
        # cut spends the whole demonstration on the *oldest* mail a new main
        # has — the wrong week, read carefully. The history walk may take a
        # page as its window because nothing cuts it; this read may not.
        stamps = await source._stamps(query=query, first=first)
        if not stamps:
            logger.warning(
                "a mailbox answered with no readable date among its newest "
                "messages; there is no recent window to read"
            )
            return

        # **Both ends come from stamps, and from different ones.** It reaches
        # up to the newest message there is, because a demonstration that
        # omitted the most recent thing a person did would be demonstrating the
        # wrong week. It reaches back from the *corroborated* stamp, so that a
        # message dated in 2099 widens the window rather than moving it
        # somewhere there is no mail — a wide window costs a bounded read some
        # requests it was going to spend anyway, and a misplaced one costs the
        # whole demonstration.
        end = _plus(_instant(stamps[-1]), 1)
        start = _plus(_instant(_horizon_of(stamps)), 1 - source.window_days)
        if cursor and cursor > start:
            start = cursor
        if start >= end:
            # A cursor past everything the mailbox holds. There is no recent
            # window left to read, and inventing one would query backwards.
            return
        async for message, _ in source._handed(
            await source._window_ids(after=start, before=end)
        ):
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


def _query_for(
    after: _dt.datetime | None = None, before: _dt.datetime | None = None
) -> str:
    """A window, bounded at either end or both, as **epoch seconds**.

    Gmail takes a timestamp as well as a ``YYYY/MM/DD``, and the date form is
    the one that cannot be used here: it is evaluated in the mailbox's own
    timezone, while ``internalDate`` — and therefore the cursor, the horizon
    and every bound computed from them — is UTC. Thirteen hours of daylight
    between the two is a message excluded from the window that contains it and
    a watermark that steps over it anyway. The epoch form is one instant
    everywhere.

    **A second of cushion at each end**, because the provider's own inclusivity
    at a bound is not documented either way. An overlap costs a digest the
    pipeline already deduplicates; a gap costs a message no later query names.

    Clamped at zero: a negative timestamp is not a query, and 1970 is the floor
    the search starts from for that reason.
    """
    terms = []
    if after is not None:
        terms.append(f"after:{max(_epoch(after) - 1, 0)}")
    if before is not None:
        terms.append(f"before:{max(_epoch(before) + 1, 0)}")
    return " ".join(terms)


def _instant(value: str | None) -> _dt.datetime | None:
    """A cursor as an instant in UTC, or None for no cursor.

    **Shape first, then parse.** ``datetime.fromisoformat`` accepts compact
    spellings — ``20260304`` is a date to it — so a cursor is checked for the
    shape the whole tree writes stamps in before it is read as one. A malformed
    cursor must not silently widen or narrow the window, and a cursor in a
    different notation must not silently misorder against stamps that are
    compared as strings.
    """
    if not value:
        return None
    text = str(value)
    head = text[:10]
    if len(head) != 10 or head[4] != "-" or head[7] != "-":
        raise ChannelError(f"cursor is not an ISO-8601 date: {value!r}")
    try:
        parsed = _dt.datetime.fromisoformat(text)
    except ValueError:
        raise ChannelError(f"cursor is not an ISO-8601 date: {value!r}") from None
    if parsed.tzinfo is None:
        # Every stamp in this tree is UTC and carries ``Z``; a cursor without a
        # zone is one of ours with the marker lost, never a local time.
        parsed = parsed.replace(tzinfo=_dt.UTC)
    return parsed.astimezone(_dt.UTC)


def _stamp(instant: _dt.datetime) -> str:
    """An instant in the one shape every stored timestamp has (AD-3).

    The whole of the ordering in this module is a string comparison, and that
    is only sound while every string is this shape.
    """
    return instant.astimezone(_dt.UTC).replace(microsecond=0).isoformat().replace(
        "+00:00", "Z"
    )


def _epoch(instant: _dt.datetime) -> int:
    return int(instant.timestamp())


def _floor_day(instant: _dt.datetime) -> _dt.datetime:
    return instant.astimezone(_dt.UTC).replace(
        hour=0, minute=0, second=0, microsecond=0
    )


def _plus(instant: _dt.datetime, days: int) -> _dt.datetime:
    """Move an instant by whole days, in this module's error vocabulary.

    A stamp near the end of what a date can express — a provider answering with
    an absurd ``internalDate`` — would otherwise raise ``OverflowError`` from
    inside a walk, which is neither a ``ChannelError`` nor anything a caller of
    this port is told to expect.
    """
    try:
        return instant + _dt.timedelta(days=days)
    except (OverflowError, ValueError):
        raise ChannelError(
            "a mailbox stamp lies outside any window this walk can express"
        ) from None


def _ids(page: dict[str, Any]) -> list[str]:
    """The message ids of one page, in the provider's own order."""
    return [
        str(stub["id"])
        for stub in (page.get("messages") or [])
        if stub and stub.get("id")
    ]


def _horizon_of(ascending: list[str]) -> str | None:
    """The newest of some stamps that another stamp stands near.

    **A lag, not a rank.** Taking the ``HORIZON_SAMPLES``-th newest outright
    was the first spelling and it punished small mailboxes for being small: a
    mailbox of three messages has its oldest as its third-newest, so the cursor
    sat at the oldest for ever and every run re-read all three. This walks down
    from the newest instead and stops at the first stamp that has company
    within ``SKEW_GAP_DAYS`` — so ordinary mail, which arrives in clusters,
    keeps its newest stamp, and a message a year clear of everything else is
    stepped over rather than believed.

    With one stamp there is nothing to corroborate against and it is taken as
    it is; a mailbox holding a single message dated 2099 is a mailbox with no
    evidence in it, and the walk still drains what it has.
    """
    if not ascending:
        return None
    horizon = ascending[-1]
    for older in reversed(ascending[:-1]):
        if _days_between(older, horizon) <= SKEW_GAP_DAYS:
            return horizon
        horizon = older
    return horizon


def _days_between(older: str, newer: str) -> float:
    return (_instant(newer) - _instant(older)).total_seconds() / 86_400.0


def _forward(since: str | None, value: str | None) -> str | None:
    """A watermark only ever moves forward, and never off the end of nothing.

    A walk resumed from a cursor can be handed a message stamped just before
    it — the query's own second of cushion, or a provider's inclusivity at a
    bound. Taking it would move the cursor backwards and re-read ground already
    behind us, for ever.
    """
    if value is None:
        return since
    if since is None or value > since:
        return value
    return since
