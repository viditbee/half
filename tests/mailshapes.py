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
#: a footer carried only by senders at one domain is that company's furniture,
#: and the same footer carried across domains is a block being passed on. So the
#: senders a case gives its messages are as much the fixture as the body is, and
#: a case that leaves them at one domain is asserting *one origin* whether or not
#: it meant to.
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
