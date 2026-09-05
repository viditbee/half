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

from half.ingest.pipeline import Receipt
from half.derive.revealed import Run


def receipt(ident: str, *, thread: str, sender: str, digest: str, day: int) -> Receipt:
    return Receipt(digest=digest, external_id=ident, thread_id=thread,
                   sender=sender, subject="s",
                   t=f"2026-08-{day:02d}T09:00:00Z")


SHAPES = {
    "newsletter — one shop, eight mailings": [
        receipt(f"n{k}", thread=f"t_news_{k}", sender="deals@shop.example",
                digest=f"d_n{k}", day=1 + k) for k in range(8)
    ],
    "airline + hotel — two businesses": [
        receipt("air", thread="t_air", sender="booking@airline.example",
                digest="d_air", day=10),
        receipt("hotel", thread="t_hotel", sender="stay@hotel.example",
                digest="d_hotel", day=10),
    ],
    "one thread — ten replies": [
        receipt(f"c{k}", thread="t_convo", sender=f"person{k}@work.example",
                digest=f"d_c{k}", day=12) for k in range(10)
    ],
    "a forward — one notice, wrapped": [
        receipt("sub", thread="t_sub", sender="billing@service.example",
                digest="d_sub", day=15),
        receipt("fwd", thread="t_fwd", sender="assistant@work.example",
                digest="d_fwd", day=16),
    ],
}

TRUTH = {
    "newsletter — one shop, eight mailings": 1,
    "airline + hotel — two businesses": 2,
    "one thread — ten replies": 1,
    "a forward — one notice, wrapped": 1,
}


async def run_one(name: str, receipts: list[Receipt]) -> tuple[int, int]:
    """Returns (independent groups Half counted, claims admitted)."""
    import test_revealed as T

    from half.ingest.scrub import scrub

    reader, _, _, _ = T.a_reader()
    with Run() as run:
        for r in receipts:
            await reader.observe(r, scrub("a booking to Delhi in September"),
                                 main_id=T.MAIN, into=run)
        claims = run.admitted()
    claims = list(claims)
    groups = max((getattr(c, "independent", 0) for c in claims), default=0)
    return groups, len(claims)


async def main() -> None:
    print(f"\n  {'shape':<40}{'truth':>6}{'counted':>9}{'admitted':>10}  verdict")
    print("  " + "─" * 80)
    for name, receipts in SHAPES.items():
        try:
            groups, admitted = await run_one(name, receipts)
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
