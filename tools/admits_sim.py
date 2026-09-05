"""What Half actually concludes about a realistic mailbox.

Runs the shipped reader and run over receipts shaped like a real inbox, with
the model stubbed so every body reads as evidence for one doing and every
source confirms the written sentence. That stub is deliberately generous: it
answers yes to everything, so whatever is refused here is refused by the
*structural* rules — the gates' shape, independence, the admission floor —
and not by a model declining.
"""
from __future__ import annotations

import asyncio
import sys

sys.path.insert(0, ".")
sys.path.insert(0, "tests")

from tests.mailshapes import forwarded

from half.ingest.pipeline import Receipt
from half.ingest.independence import independent_groups
from half.derive.revealed import DOINGS, Run


def receipt(ident: str, *, thread: str, sender: str, digest: str, day: int) -> Receipt:
    return Receipt(digest=digest, external_id=ident, thread_id=thread,
                   sender=sender, subject="s",
                   t=f"2026-08-{day:02d}T09:00:00Z")


#: The separator a mail client puts in front of a forwarded original is
#: ``tests/mailshapes.py``'s, imported rather than spelled a third way. Nothing
#: strips it — ``scrub`` removes secrets and ``normalize`` decodes, and neither
#: touches quoted blocks — so the original arrives inside the forward intact,
#: which is what the containment rule reads. This file, ``tests/test_echo.py``
#: and ``tests/test_revealed.py`` each carried a *different* spelling of it, and
#: what a forward looks like is the thing being measured here.

#: The one notice, and the mail that carries it onward.
NOTICE = ("Your subscription to the reading service renews on 1 October for "
          "499 rupees. The card ending 4242 will be charged on that date.")

#: **Every receipt carries its own body, and that is not decoration.** This file
#: used to hand the same six-word string to every receipt in every shape, which
#: made the forward shape indistinguishable from the airline-and-hotel one:
#: identical bodies, identical everything the body decides. Story 18 put a rule
#: on the body, so a simulation that stubs the body measures the stub.
SHAPES = {
    "newsletter — one shop, eight mailings": [
        (receipt(f"n{k}", thread=f"t_news_{k}", sender="deals@shop.example",
                 digest=f"d_n{k}", day=1 + k),
         f"This week: {k} new routes to Delhi from 12,000 rupees. Book by "
         f"Friday and travel any time before the end of the month.")
        for k in range(8)
    ],
    "airline + hotel — two businesses": [
        (receipt("air", thread="t_air", sender="booking@airline.example",
                 digest="d_air", day=10),
         "Your flight to Delhi is confirmed. Confirmation ABC123. Departure "
         "14 September at 06:20 from Terminal 2."),
        (receipt("hotel", thread="t_hotel", sender="stay@hotel.example",
                 digest="d_hotel", day=10),
         "Reservation confirmed at the Taj Palace, New Delhi. Two nights, "
         "14 to 16 September. Booking XYZ789."),
    ],
    "one thread — ten replies": [
        (receipt(f"c{k}", thread="t_convo", sender=f"person{k}@work.example",
                 digest=f"d_c{k}", day=12),
         f"Reply number {k} about the offsite: I can get to Goa on the "
         f"Thursday if we book the {k} o'clock train.")
        for k in range(10)
    ],
    "a forward — one notice, wrapped": [
        (receipt("sub", thread="t_sub", sender="billing@service.example",
                 digest="d_sub", day=15), NOTICE),
        (receipt("fwd", thread="t_fwd", sender="assistant@work.example",
                 digest="d_fwd", day=16), forwarded(NOTICE)),
    ],
}

TRUTH = {
    "newsletter — one shop, eight mailings": 1,
    "airline + hotel — two businesses": 2,
    "one thread — ten replies": 1,
    "a forward — one notice, wrapped": 1,
}


async def run_one(name: str, mail: list[tuple[Receipt, str]]) -> tuple[int, int]:
    """Returns (independent groups Half counted, claims admitted).

    **The count is read off the candidates, not off the claims.** It used to be
    ``max(c.independent for c in claims)``, which is zero whenever nothing was
    admitted — so every shape that admits nothing printed the same ``0`` and the
    column could not tell *"correctly collapsed to one voice"* from *"counted
    two and refused for some other reason"*. That is precisely the distinction
    story 18 is about: the forward row admits nothing either way, and what has
    to be visible is whether it admitted nothing because the two messages became
    one voice or because something else declined.

    ``independent_groups`` over the run's own supports is the same function
    ``Run.ready`` asks, so the number here is the one the admission decision was
    made on. Every shape in this file is one label, which is what makes a single
    number the right shape for the column.
    """
    import test_revealed as T

    from half.ingest.scrub import scrub

    reader, _, _, _ = T.a_reader()
    with Run() as run:
        for r, body in mail:
            await reader.observe(r, scrub(body), main_id=T.MAIN, into=run)
        claims = list(run.admitted())
        supports = [candidate
                    for doing in DOINGS
                    for candidate in run.supports(doing.label)]
        groups = independent_groups(c.identity() for c in supports)
    return groups, len(claims)


async def main() -> None:
    print(f"\n  {'shape':<40}{'truth':>6}{'counted':>9}{'admitted':>10}  verdict")
    print("  " + "─" * 80)
    for name, mail in SHAPES.items():
        try:
            groups, admitted = await run_one(name, mail)
        except Exception as exc:  # noqa: BLE001 - a simulation, not a product
            print(f"  {name:<40}{'':>6}{'':>9}{'':>10}  harness: {type(exc).__name__}: {exc}")
            continue
        truth = TRUTH[name]
        honest = (truth >= 2)
        got = (admitted > 0)
        verdict = "ok" if honest == got else ("ADMITTED ON THIN EVIDENCE"
                                              if got else "missed")
        print(f"  {name:<40}{truth:>6}{groups:>9}{admitted:>10}  {verdict}")
    print("  " + "─" * 80)
    print("  truth = independent sources a person would say there are")
    print("  counted = what the union-find returned; admitted = claims written\n")


if __name__ == "__main__":
    asyncio.run(main())
