"""What a window width costs, measured over mailboxes of four densities.

``half.ingest.gmail.WINDOW_DAYS`` is a trade with two ends and the story that
introduced it refused to guess the number:

* too **wide** and a window will not drain inside a caller's deadline, so
  ``drained_through`` never moves and the walk repeats the same window for
  ever. What sets that is the number of messages the widest window holds,
  because every one of them is a request.
* too **narrow** and a sparse mailbox spends its requests on empty weeks. The
  list call for a window with nothing in it is paid whether or not anything
  comes back, so a dormant mailbox pays for the whole calendar.

So the measurement is *requests per message ingested*, plus the size of the
busiest window, over the shipped walk's own request pattern: one list call per
page of each window, one message read per message, and a first walk's extra
probes — the horizon and the halving search for the mailbox's oldest day.

Deterministic: the arrivals come from a seeded generator, so two runs of this
file report the same table and a change in the numbers is a change in the code.
"""
from __future__ import annotations

import math
import random
import sys
from dataclasses import dataclass

sys.path.insert(0, ".")

from half.ingest.gmail import (  # noqa: E402
    HORIZON_SAMPLES,
    MAILBOX_FLOOR,
    WINDOW_DAYS,
)

#: What Gmail returns in one page of a list call.
PAGE_SIZE = 100

#: How long a mailbox has existed, in days. Five years.
SPAN_DAYS = 5 * 365

#: The widths worth putting side by side: a day, the shipped week, a fortnight,
#: a month, a quarter.
WIDTHS = (1, 7, 14, 30, 90)


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


def arrivals(per_day: float, *, seed: int) -> list[int]:
    """Which day each message landed on, over ``SPAN_DAYS``.

    Bursty rather than uniform, because a real mailbox is: weekdays carry more
    than weekends, and a fortnight of quiet turns up in every mailbox that
    belongs to somebody who went away. A uniform arrival would make every width
    look better than it is, by never leaving a window empty and never filling
    one.
    """
    rng = random.Random(seed)
    weights = []
    for day in range(SPAN_DAYS):
        weekday = day % 7 < 5
        away = (day // 180) % 2 == 1 and day % 180 < 14
        weights.append(0.0 if away else (1.0 if weekday else 0.2))
    total = round(per_day * SPAN_DAYS)
    return sorted(rng.choices(range(SPAN_DAYS), weights=weights, k=total))


def requests(days: list[int], *, width: int) -> tuple[int, int, int]:
    """(requests, messages, the busiest window's size) for one full walk.

    The shipped pattern, counted as the walk makes it:

    * one list call to see whether anything is after the cursor at all;
    * on a first walk, the horizon probe and the halving search for the oldest
      day — the search is bounded by the interval above the floor;
    * per window, one list call per page — at least one, empty or not;
    * per message, one read.
    """
    if not days:
        return 1, 0, 0

    first, last = min(days), max(days)
    windows = math.ceil((last - first + 1) / width)
    counts = [0] * (windows + 1)
    for day in days:
        counts[(day - first) // width] += 1

    probes = math.ceil(math.log2(max(SPAN_DAYS, _floor_span()) or 1))
    made = 1 + HORIZON_SAMPLES + probes
    for held in counts:
        made += max(1, math.ceil(held / PAGE_SIZE))  # the window's pages
        made += held                                 # its messages
    return made, len(days), max(counts)


def _floor_span() -> int:
    """The days the oldest-day search halves over, near enough to date it."""
    return (2026 - int(MAILBOX_FLOOR[:4])) * 365


def main() -> None:
    print(f"\n  five years of mailbox, walked whole. page size {PAGE_SIZE}, "
          f"{HORIZON_SAMPLES} horizon probes.\n")
    header = f"  {'width':>7}" + "".join(f"{d.name:>12}" for d in DENSITIES)
    print(header)
    print("  " + "─" * (len(header) - 2))
    for width in WIDTHS:
        cells = []
        for index, density in enumerate(DENSITIES):
            made, count, _ = requests(arrivals(density.per_day, seed=index),
                                      width=width)
            cells.append(f"{made / max(count, 1):>12.2f}")
        mark = "  ← shipped" if width == WINDOW_DAYS else ""
        print(f"  {width:>5}d " + "".join(cells) + mark)
    print("\n  requests per message ingested. lower is cheaper.\n")

    print(f"  {'width':>7}" + "".join(f"{d.name:>12}" for d in DENSITIES))
    print("  " + "─" * (len(header) - 2))
    for width in WIDTHS:
        cells = []
        for index, density in enumerate(DENSITIES):
            _, _, widest = requests(arrivals(density.per_day, seed=index),
                                    width=width)
            cells.append(f"{widest:>12,}")
        mark = "  ← shipped" if width == WINDOW_DAYS else ""
        print(f"  {width:>5}d " + "".join(cells) + mark)
    print("\n  messages in the busiest window — what has to drain inside a")
    print("  caller's deadline before the cursor may move at all.\n")


if __name__ == "__main__":
    main()
