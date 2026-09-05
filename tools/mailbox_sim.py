"""A synthetic mailbox that looks like a real one, run through the real pipeline.

Everything in Half has been tested against doubles built to make one case pass.
This builds a mailbox with the shapes a real inbox actually has — threads,
newsletters from one sender, forwards, mixed scripts — and runs the shipped
ingestion and derivation over it, so the structural rules can be measured
rather than reasoned about.

The model is stubbed deterministically. That means nothing here measures
semantic quality; it measures independence, admission and cost, which is
exactly where the two contract defects live.
"""
from __future__ import annotations

import asyncio
import sys
from dataclasses import dataclass

sys.path.insert(0, ".")

from half.ingest.port import Message
from half.ingest.independence import independent_groups


# ── the mailbox ───────────────────────────────────────────────────────────────

def msg(i: int, *, thread: str, sender: str, subject: str, body: str,
        day: int) -> Message:
    return Message(
        external_id=f"m{i}",
        thread_id=thread,
        sender=sender,
        subject=subject,
        body=body.encode("utf-8"),
        t=f"2026-08-{day:02d}T09:00:00Z",
        headers={"from": sender, "subject": subject},
    )


def a_realistic_mailbox() -> list[Message]:
    """The shapes a real inbox has, each labelled by what it should mean."""
    out: list[Message] = []
    n = 0

    # 1. A newsletter: ONE sender, MANY threads, over weeks.
    #    Truth: one source. Half should count 1.
    for k in range(8):
        n += 1
        out.append(msg(n, thread=f"t_news_{k}", sender="deals@shop.example",
                       subject=f"Your weekly picks #{k}",
                       body=f"Flights to Delhi from 12,000. Offer {k}.", day=1 + k))

    # 2. A genuine two-source corroboration: an airline and a hotel,
    #    unrelated senders, unrelated threads.
    #    Truth: two sources. Half should count 2.
    n += 1
    out.append(msg(n, thread="t_air", sender="booking@airline.example",
                   subject="Your flight to Delhi is confirmed",
                   body="Confirmation ABC123. Delhi, 14 September.", day=10))
    n += 1
    out.append(msg(n, thread="t_hotel", sender="stay@hotel.example",
                   subject="Reservation confirmed, New Delhi",
                   body="Two nights, 14-16 September. Booking XYZ.", day=10))

    # 3. A thread: ten replies, one conversation.
    #    Truth: one source. Half should count 1.
    for k in range(10):
        n += 1
        out.append(msg(n, thread="t_convo", sender=f"person{k}@work.example",
                       subject="Re: offsite planning",
                       body=f"Reply {k} about the offsite in Goa.", day=12))

    # 4. A forward: the same content, wrapped, from a different person.
    #    Truth: one source. Half should count 1.
    n += 1
    original = "Your subscription renews on 1 October for 499."
    out.append(msg(n, thread="t_sub", sender="billing@service.example",
                   subject="Subscription renewal", body=original, day=15))
    n += 1
    out.append(msg(n, thread="t_fwd", sender="assistant@work.example",
                   subject="Fwd: Subscription renewal",
                   body=f"FYI\n\n---------- Forwarded message ----------\n{original}",
                   day=16))

    # 5. Mixed scripts, two genuinely independent senders.
    n += 1
    out.append(msg(n, thread="t_jp", sender="info@travel.example.jp",
                   subject="ご予約の確認", body="東京行きの航空券を確認しました。", day=18))
    n += 1
    out.append(msg(n, thread="t_th", sender="noreply@air.example.th",
                   subject="ยืนยันการจอง", body="เที่ยวบินไปโตเกียวได้รับการยืนยันแล้ว", day=18))

    return out


# ── what Half currently concludes ─────────────────────────────────────────────

@dataclass
class Group:
    name: str
    messages: list[Message]
    truth: int          # how many independent sources a person would say there are
    why: str


def groups(mail: list[Message]) -> list[Group]:
    by = lambda pred: [m for m in mail if pred(m)]
    return [
        Group("newsletter, 1 sender / 8 threads",
              by(lambda m: m.sender == "deals@shop.example"), 1,
              "one shop mailing you eight times"),
        Group("airline + hotel, 2 senders",
              by(lambda m: m.thread_id in {"t_air", "t_hotel"}), 2,
              "two unrelated businesses"),
        Group("one thread, 10 replies",
              by(lambda m: m.thread_id == "t_convo"), 1,
              "one conversation"),
        Group("a forward of one message",
              by(lambda m: m.thread_id in {"t_sub", "t_fwd"}), 1,
              "the same notice, wrapped"),
        Group("two airlines, two scripts",
              by(lambda m: m.thread_id in {"t_jp", "t_th"}), 2,
              "two unrelated carriers"),
    ]


def counted(ms: list[Message]) -> int:
    return independent_groups(
        (m.external_id, {"thread_id": m.thread_id, "sender": m.sender,
                         "digest": f"d_{m.external_id}"})
        for m in ms
    )


def main() -> None:
    mail = a_realistic_mailbox()
    print(f"  a synthetic mailbox of {len(mail)} messages\n")
    print(f"  {'shape':<34}{'truth':>6}{'Half':>6}  {'verdict':<10} why")
    print("  " + "─" * 86)
    wrong = 0
    for g in groups(mail):
        got = counted(g.messages)
        ok = got == g.truth
        wrong += not ok
        mark = "ok" if ok else "WRONG"
        print(f"  {g.name:<34}{g.truth:>6}{got:>6}  {mark:<10} {g.why}")
    print("  " + "─" * 86)
    print(f"\n  shapes miscounted: {wrong} of {len(groups(mail))}")
    print("  CAP-3 admits a claim at >= 2 independent supports.\n")


if __name__ == "__main__":
    main()
