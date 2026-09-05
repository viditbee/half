"""The mail shapes story 18's rule is measured against, in one place.

**Not a test module** — pytest collects ``test_*.py`` and this is imported by
name. It exists because the same three literals were written out four times: the
forwarded-message separator in ``tests/test_echo.py``, ``tests/test_revealed.py``
and ``tools/admits_sim.py`` in three *different* spellings, and the legal footer
verbatim in ``tests/test_echo.py`` and ``tools/percolation_sim.py``.

That is not a tidiness complaint. The footer is the confound the containment rule
was chosen over, and the separator is what makes a forward a forward: an edit to
one copy that did not reach the others would leave a suite and a sweep measuring
two different mailboxes and agreeing with each other about the answer. The
duplication was the drift risk, so there is one copy and everything reads it.

Nothing here imports ``half``. A fixture module that reached into the tree it is
used to measure could be made to agree with it.
"""
from __future__ import annotations

#: What a mail client staples in front of a forwarded original. Nothing on the
#: ingestion path strips it: ``scrub`` removes secrets and ``normalize`` decodes
#: transfer encoding, charset and markup, and neither touches a quoted block, a
#: ``>`` prefix, a separator, a signature or a legal footer. That is what makes
#: containment work at all, and what makes the disclaimer confound real.
SEPARATOR = ("\n\n---------- Forwarded message ----------\n"
             "From: Billing <billing@service.example>\n"
             "Date: 1 September 2026\n\n")

#: A long legal footer of the kind a company staples to every message it sends.
#:
#: **The confound**, and the reason the floor is total containment rather than a
#: fraction: two unrelated notes under this footer share almost all of their
#: vocabulary, and a rule that scored the fraction would call them one voice.
#: Long on purpose — the longer the shared block, the higher the score between
#: two messages that share nothing else.
#:
#: **Since story 19 it is also the furniture fixture**, and the two roles are the
#: same text on purpose. What decides which it is is not in this string at all:
#: a footer carried only by senders at one *organisation* is that company's
#: furniture, and the same footer carried across organisations is a block being
#: passed on. So the senders a case gives its messages are as much the fixture as
#: the body is, and a case that leaves them at one domain is asserting *one
#: origin* whether or not it meant to.
#:
#: **And a domain is not automatically an organisation**, which review measured
#: the hard way: `gmail.com`, an ISP and a university host many unrelated people,
#: so a fixture that puts two senders there is asserting *strangers* rather than
#: *one company*. A sender with no dot in it — `p0@x`, which every fixture in
#: this tree used before story 19 — is not an address at all and declines.
DISCLAIMER = (
    "This electronic mail message and any attachments transmitted with it are "
    "confidential and privileged information intended solely for the use of "
    "the individual or entity to whom they are addressed. If the reader of "
    "this message is not the intended recipient, or the employee or agent "
    "responsible for delivering it to the intended recipient, you are hereby "
    "notified that any dissemination, distribution, forwarding, printing or "
    "copying of this communication is strictly prohibited. If you have "
    "received this communication in error, please notify us immediately by "
    "telephone and return the original message to us at the address below by "
    "postal service. Please note that neither the sender nor the company "
    "accepts any liability whatsoever for any loss, damage, corruption or "
    "interruption arising from viruses, interception, amendment or "
    "unauthorised access to this message or its attachments."
)

#: The *short* shared block, and it is the one that matters most. Eight distinct
#: terms — one over ``echo.MIN_TERMS`` — so it is long enough to declare a
#: handle and short enough that raising the floor to exclude it would exclude
#: real transactional mail as well. Everything the disclaimer does to a mailbox,
#: this line does with a fifteenth of the words.
FOOTER_LINE = "Please consider the environment before printing this email"

#: The rejected fractional floor, in one place: it is quoted in
#: ``half/ingest/echo.py``'s docstring, asserted in ``tests/test_echo.py`` and
#: swept in ``tools/percolation_sim.py``, and three copies of a number that is
#: the whole argument for the shipped rule is three places for it to drift.
REJECTED_FLOOR = 0.98


def forwarded(original: str) -> str:
    """``original``, as it arrives when somebody forwards it on."""
    return "FYI" + SEPARATOR + original


def quoted(original: str) -> str:
    """``original``, as it arrives quoted in full underneath a reply."""
    return "Thanks, noted.\n\n" + "\n".join(
        "> " + line for line in original.split("\n")
    )


def under_a_footer(index: int, day: int, footer: str = DISCLAIMER) -> str:
    """One ordinary note with a shared block stapled to the end of it."""
    return (f"Note {index}: please look at item {index} before the review on "
            f"day {day}.\n\n{footer}")


# ── a mailbox that answers questions, for story 20's walk ────────────────────

#: **A double that answers by *query* rather than by position.** Story 20's walk
#: asks real questions — a window is a bound at each end and the answer has to
#: respect both — and a fake answering a scripted queue cannot fail when the
#: question is wrong: whatever was asked, the third response is still the third
#: one handed back. Three modules needed one, so there is one.
#:
#: Newest-first, because that is what Gmail does and what the walk exists to
#: reverse. A double that answered oldest-first would let every ordering case
#: pass against a build that reorders nothing at all.
#:
#: ``zone_hours`` is the sharp one. Gmail's ``after:``/``before:`` in their
#: ``YYYY/MM/DD`` form are evaluated in **the mailbox's own timezone** while
#: every stamp the walk computes from is UTC, so a double that evaluated dates
#: in UTC could not express the bug that costs a boundary message. This one
#: evaluates a date form at whatever offset it is given — and the shipped walk
#: sends epoch seconds, which are the same instant at every offset.

import base64 as _base64
import datetime as _dt
import json as _json

#: What a bare ``YYYY-MM-DD`` in a mailbox means: mid-morning, UTC.
DEFAULT_HOUR = 8


def instant_of(when: str) -> _dt.datetime:
    """``2026-08-01`` or ``2026-08-01T22:30:00Z`` as an aware UTC instant."""
    if len(when) == 10:
        when = f"{when}T{DEFAULT_HOUR:02d}:00:00Z"
    return _dt.datetime.fromisoformat(when.replace("Z", "+00:00"))


def internal_date(when: str) -> str:
    """Gmail's own ``internalDate``: epoch milliseconds, as a string."""
    return str(int(instant_of(when).timestamp() * 1000))


def raw_message(mid: str, *, when: str, body: str | None = None,
                sender: str = "a@x", subject: str = "the plot") -> dict:
    """One message as the Gmail API returns it.

    The body is distinct per message by default, because the receipt's address
    is a digest **of the body**: a double handing every message the same text
    gives every receipt the same address, and *twenty of twenty ingested*
    becomes one receipt and nineteen already-seens against a build that works.
    """
    text = body if body is not None else f"the plot at {mid} has not been walked"
    return {
        "id": mid, "threadId": "t1", "internalDate": internal_date(when),
        "payload": {
            "mimeType": "multipart/alternative",
            "headers": [{"name": "From", "value": sender},
                        {"name": "Subject", "value": subject}],
            "parts": [{"mimeType": "text/plain", "body": {"data": _base64.urlsafe_b64encode(
                text.encode("utf-8")).decode("ascii")}}],
        },
    }


class Mailbox:
    """A Gmail-shaped mailbox: ``{id: day}``, paged, newest-first.

    ``breaks_on`` names the message whose read fails, and every read after it.
    Named rather than counted, because the walk reads a few of the newest
    messages first to find its horizon and a count would land somewhere
    different each time that number changed.
    """

    def __init__(self, when: dict[str, str], *, page_size: int = 100,
                 breaks_on: str | None = None, zone_hours: float = 0.0,
                 undated: tuple[str, ...] = (), loops: bool = False) -> None:
        self.when = dict(when)
        self.page_size = page_size
        self.breaks_on = breaks_on
        self.zone_hours = zone_hours
        self.undated = set(undated)
        self.loops = loops
        self.broken = False

    # -- the query ------------------------------------------------------------

    def bound(self, term: str) -> _dt.datetime:
        """One ``after:``/``before:`` value as the instant the provider means."""
        value = term.split(":", 1)[1]
        if value.lstrip("-").isdigit():
            # Epoch seconds: one instant, the same at every offset on earth.
            return _dt.datetime.fromtimestamp(int(value), _dt.UTC)
        # A date, evaluated at midnight in the mailbox's own timezone — which
        # is the whole reason the walk does not send this form.
        zone = _dt.timezone(_dt.timedelta(hours=self.zone_hours))
        naive = _dt.datetime.strptime(value, "%Y/%m/%d")
        return naive.replace(tzinfo=zone).astimezone(_dt.UTC)

    def matching(self, query: str) -> list[str]:
        after = before = None
        for term in query.split():
            if term.startswith("after:"):
                after = self.bound(term)
            elif term.startswith("before:"):
                before = self.bound(term)
        chosen = [
            mid for mid, when in self.when.items()
            # Strictly outside both bounds — the harshest reading of an
            # undocumented inclusivity, so that a walk relying on the friendly
            # one fails here rather than in somebody's mailbox.
            if (after is None or instant_of(when) > after)
            and (before is None or instant_of(when) < before)
        ]
        return sorted(chosen, key=lambda mid: (instant_of(self.when[mid]), mid),
                      reverse=True)

    # -- the API --------------------------------------------------------------

    def page(self, query: str, page_token: str | None) -> dict:
        ids = self.matching(query)
        # A looping provider hands back a token that means nothing, and a
        # double that crashed on it would make the guard's case pass for the
        # wrong reason: the walk would fail on a ``ValueError`` from the
        # fixture rather than on the repeated token it is there to catch.
        start = int(page_token) if (page_token or "").isdigit() else 0
        answer: dict = {"messages": [{"id": i} for i in ids[start:start + self.page_size]]}
        if self.loops:
            answer["nextPageToken"] = "the-same-token"
        elif start + self.page_size < len(ids):
            answer["nextPageToken"] = str(start + self.page_size)
        return answer

    def message(self, mid: str) -> dict:
        if mid == self.breaks_on:
            self.broken = True
        if self.broken:
            raise RuntimeError("the provider stopped answering mid-window")
        raw = raw_message(mid, when=self.when[mid])
        if mid in self.undated:
            raw = raw | {"internalDate": None}
        return raw

    def payload(self, query: str, page_token: str | None) -> bytes:
        return _json.dumps(self.page(query, page_token)).encode("utf-8")


class Transport:
    """``Mailbox`` at the ``GmailTransport`` door, recording what it was asked."""

    name = "gmail"

    def __init__(self, mailbox: Mailbox) -> None:
        self.mailbox = mailbox
        self.lists: list[str] = []
        self.gets: list[str] = []

    @property
    def requests(self) -> int:
        return len(self.lists) + len(self.gets)

    async def list_messages(self, *, query: str, page_token: str | None) -> dict:
        self.lists.append(query)
        return self.mailbox.page(query, page_token)

    async def get_message(self, message_id: str) -> dict:
        self.gets.append(message_id)
        return self.mailbox.message(message_id)


class Cut:
    """A source that stops yielding after ``after`` messages.

    ``half.__main__.Bounded`` in miniature — the same shape, cutting on a count
    rather than on a clock, so that *what a cut costs* is a property of the walk
    rather than of how fast the suite happens to run. It forwards
    ``drained_through`` for the reason ``Bounded`` does: a wrapper that
    swallowed the watermark would send the pipeline back to the ``max()`` cursor
    story 20 removed, and every case would pass for the wrong reason.
    """

    def __init__(self, source, *, after: int) -> None:
        self.source = source
        self.name = getattr(source, "name", "cut")
        self.after = after
        self.stopped_early = False

    #: A property and not a ``__getattr__``, for the reason
    #: ``half.__main__.DrainingBounded`` is one: ``isinstance`` against a
    #: runtime-checkable protocol resolves attributes statically, so a
    #: ``__getattr__`` forwards the value and is invisible to the check. Only
    #: ever wrapped around a source that has one; anything else is a mistake
    #: worth the ``AttributeError``.
    @property
    def drained_through(self):
        return self.source.drained_through

    async def fetch(self, *, since=None):
        handed = 0
        async for message in self.source.fetch(since=since):
            yield message
            handed += 1
            if handed >= self.after:
                self.stopped_early = True
                return
