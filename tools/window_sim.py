"""What a window width costs, measured by running the walk that ships.

``half.ingest.gmail.WINDOW_DAYS`` is a trade with two ends and the story that
introduced it refused to guess the number:

* too **wide** and a window will not drain inside a caller's deadline, so
  ``drained_through`` never moves and the walk repeats the same window for
  ever. What sets that is the number of messages the widest window holds,
  because every one of them is a request.
* too **narrow** and a sparse mailbox spends its requests on empty weeks. The
  list call for a window with nothing in it is paid whether or not anything
  comes back.

**It drives the real ``GmailSource``.** The first version of this tool modelled
the walk instead — one list call per window, one read per message — and the
model had stopped being the walk: it knew nothing of the halving search that
crosses a gap, so it reported 1.77 requests per message on a dormant mailbox
where the shipped code spent 2.97. A number that justifies a constant has to
come from the thing the constant is in. So this counts what a real walk over a
real mailbox double actually asks for, searches, pages, horizon probes and all.

Deterministic: the arrivals come from a seeded generator, so two runs of this
file report the same table and a change in the numbers is a change in the walk.
"""
from __future__ import annotations

import asyncio
import math
import random
import sys
from dataclasses import dataclass

sys.path.insert(0, ".")

from tests.mailshapes import Mailbox, Transport  # noqa: E402

from half.ingest.gmail import WINDOW_DAYS, GmailSource  # noqa: E402

#: What Gmail returns in one page of a list call.
PAGE_SIZE = 100

#: How long a mailbox has existed, in days. Five years.
SPAN_DAYS = 5 * 365

#: The most messages any one synthetic mailbox holds.
#:
#: The tool drives the real walk, so every message in a mailbox is a real
#: request and a real ``normalize``; five years of firehose is a third of a
#: million of them and several minutes of waiting. The dense rows are shortened
#: to fit instead — which costs nothing they are read for: at those densities
#: the cost per message is flat across every width, and the number a width is
#: judged on there is the size of the busiest window, which density and width
#: decide between them and a span does not.
MAX_MESSAGES = 40_000

#: The day the synthetic mailboxes start on.
FIRST_DAY = "2021-01-01"

#: The widths worth putting side by side: a day, the shipped week, a fortnight,
#: a month.
WIDTHS = (1, 7, 14, 30)


@dataclass(frozen=True)
class Density:
    name: str
    per_day: float
    why: str


DENSITIES = (
    Density("dormant", 0.2, "a mailbox that gets a receipt a week"),
    Density("ordinary", 5.0, "a person with a life and some newsletters"),
    Density("busy", 40.0, "work mail, threads, alerts"),
    Density("firehose", 200.0, "every list they ever signed up to"),
)


def span_for(per_day: float) -> int:
    """How long this density's mailbox runs for, capped by ``MAX_MESSAGES``."""
    return min(SPAN_DAYS, max(1, math.ceil(MAX_MESSAGES / max(per_day, 1e-9))))


def arrivals(per_day: float, *, seed: int) -> list[int]:
    """Which day each message landed on, over ``SPAN_DAYS``.

    Bursty rather than uniform, because a real mailbox is: weekdays carry more
    than weekends, and a fortnight of quiet turns up in every mailbox that
    belongs to somebody who went away. A uniform arrival would make every width
    look better than it is, by never leaving a window empty and never filling
    one.
    """
    rng = random.Random(seed)
    span = span_for(per_day)
    weights = []
    for day in range(span):
        weekday = day % 7 < 5
        away = (day // 180) % 2 == 1 and day % 180 < 14
        weights.append(0.0 if away else (1.0 if weekday else 0.2))
    total = round(per_day * span)
    return sorted(rng.choices(range(span), weights=weights, k=total))


def a_mailbox(days: list[int]) -> dict[str, str]:
    """The arrivals as ``{id: instant}``, an hour apart within each day."""
    import datetime as dt

    first = dt.date.fromisoformat(FIRST_DAY)
    when: dict[str, str] = {}
    seen: dict[int, int] = {}
    for index, day in enumerate(days):
        within = seen.get(day, 0)
        seen[day] = within + 1
        at = dt.datetime.combine(
            first + dt.timedelta(days=day), dt.time(hour=0), dt.UTC
        ) + dt.timedelta(minutes=(within * 1439) // max(seen[day], 1))
        when[f"m{index:07d}"] = at.isoformat().replace("+00:00", "Z")
    return when


def walked(when: dict[str, str], *, width: int) -> tuple[int, int]:
    """(requests, messages handed over) for one full walk of the real source."""
    transport = Transport(Mailbox(when, page_size=PAGE_SIZE))
    source = GmailSource(transport, window_days=width)

    async def drain() -> int:
        handed = 0
        async for _ in source.fetch():
            handed += 1
        return handed

    handed = asyncio.run(drain())
    return transport.requests, handed


def busiest(days: list[int], *, width: int) -> int:
    """Messages in the fullest window — what has to drain before a cursor moves."""
    if not days:
        return 0
    first, last = min(days), max(days)
    counts = [0] * (math.ceil((last - first + 1) / width) + 1)
    for day in days:
        counts[(day - first) // width] += 1
    return max(counts)


def main() -> None:
    print(f"\n  mailboxes walked whole by the shipped GmailSource, page "
          f"size {PAGE_SIZE}.")
    for density in DENSITIES:
        years = span_for(density.per_day) / 365
        print(f"    {density.name:<10} {density.per_day:>6} a day over "
              f"{years:>4.1f} years — {density.why}")
    print()
    header = f"  {'width':>7}" + "".join(f"{d.name:>12}" for d in DENSITIES)
    mailboxes = {
        density.name: (days := arrivals(density.per_day, seed=index),
                       a_mailbox(days))
        for index, density in enumerate(DENSITIES)
    }

    rows: dict[int, dict[str, tuple[float, int]]] = {}
    for width in WIDTHS:
        rows[width] = {}
        for density in DENSITIES:
            days, when = mailboxes[density.name]
            requests, handed = walked(when, width=width)
            rows[width][density.name] = (
                requests / max(handed, 1), busiest(days, width=width),
            )

    print(header)
    print("  " + "─" * (len(header) - 2))
    for width in WIDTHS:
        cells = "".join(f"{rows[width][d.name][0]:>12.2f}" for d in DENSITIES)
        print(f"  {width:>5}d " + cells
              + ("  ← shipped" if width == WINDOW_DAYS else ""))
    print("\n  requests per message ingested. lower is cheaper.\n")

    print(header)
    print("  " + "─" * (len(header) - 2))
    for width in WIDTHS:
        cells = "".join(f"{rows[width][d.name][1]:>12,}" for d in DENSITIES)
        print(f"  {width:>5}d " + cells
              + ("  ← shipped" if width == WINDOW_DAYS else ""))
    print("\n  messages in the busiest window — what has to drain inside a")
    print("  caller's deadline before the cursor may move at all.\n")

    print("  WINDOW_MEASUREMENT, to paste into half/ingest/gmail.py:\n")
    for width in WIDTHS:
        cells = ", ".join(
            f'"{d.name}": ({rows[width][d.name][0]:.2f}, '
            f"{rows[width][d.name][1]})" for d in DENSITIES
        )
        print(f"    {width}: {{{cells}}},")
    print()


if __name__ == "__main__":
    main()
