"""The trust currency and the unasked queue (CAP-4, CAP-10).

`half.governance` answers *which rung a belief may occupy*. This package
answers the question standing on top of it: **may Half spend the relationship
on a question right now**, and is that question worth spending it on.

Three modules, and the split is the story:

* ``balance`` — the currency, **computed from the log and never counted into a
  field**. Delivered favours minus questions asked, folded out of the records
  themselves, so there is nowhere for a stale number to live (AD-30).
* ``stakes`` — whether acting on a wrong belief would cost more than the
  interruption. Both sides measured in days, and neither number chosen: the
  cost is the wanting's own period and the interruption is the main's own day.
* ``unasked`` — the queue, the two gates in order, what is held, and the spend.

**The two gates run stakes first, favour second**, and that is enforced by the
shape rather than by a comment: ``stakes`` is not given a balance and cannot
consult one. Reversed, a large balance buys a worthless question — which the
glossary names outright when it calls an unspent balance a defect rather than
something to spend for its own sake.

**Nothing in this package asks anything.** It decides whether a question *may*
be asked and records that one *was*; composing the sentence and delivering it
is story 11, and CAP-4 forbids an onboarding interview outright. There is no
text on any value here, no channel reachable from any of these modules, and
nothing durable that carries a word of what a question said (AD-22).

**The package straddles two layers, exactly as ``half.surface`` does.**
``balance``, ``stakes`` and the pure half of ``unasked`` are *domain*: they
depend on ``half.store``, ``half.loops``, ``half.governance`` and
``half.retrieval`` and on nothing above them, and ``tests/test_purity.py`` holds
them to it. ``UnaskedQueue`` is the *composition*: it reads the registry's
narrowed doors, so it sits above them and nothing in the domain imports it.
"""

# **The two folding functions are deliberately not re-exported here.**
# ``half.trust.balance`` and ``half.trust.stakes`` are modules, and a package
# attribute of the same name would shadow each of them — so ``from half.trust
# import balance`` would hand back a function while ``import
# half.trust.balance`` handed back a module, and which one a reader got would
# depend on import order. Callers take them from their own modules; only the
# types and the vocabulary are re-exported.
from half.trust.balance import Balance, delivered, spent, tombstoned
from half.trust.stakes import (
    BELOW_THE_BAR,
    FINISHED,
    INTERRUPTION_DAYS,
    NO_PERIOD,
    NO_SUBJECT,
    NO_WANTING,
    Stakes,
)
from half.trust.unasked import (
    ASK_CRISIS,
    ASK_NOT_PERMITTED,
    ASK_OUTCOMES,
    ASK_RECORDED,
    ASK_REFUSED,
    ASK_UNAFFORDABLE,
    ASKS_AT,
    HELD,
    NO_FAVOUR,
    NOT_PERMITTED,
    ON_TOPIC_FLOOR,
    REASONS,
    TOPIC_UNRAISED,
    VISIBLE,
    Ask,
    TrustLedger,
    TrustView,
    Unasked,
    UnaskedQueue,
    Verdict,
    asks_at,
    considered,
    may_be_raised,
    narrowed_for_trust,
    on_topic,
    queue,
    verdicts,
)

#: **Every name a caller reads a verdict or an outcome against.** The reason
#: constants are here rather than left in their own modules because
#: ``Verdict.reason`` and the spend outcomes are documented as closed sets, and
#: a closed set whose members are not importable beside the type is one every
#: consumer re-spells.
__all__ = [
    "ASKS_AT",
    "ASK_CRISIS",
    "ASK_NOT_PERMITTED",
    "ASK_OUTCOMES",
    "ASK_RECORDED",
    "ASK_REFUSED",
    "ASK_UNAFFORDABLE",
    "Ask",
    "BELOW_THE_BAR",
    "Balance",
    "FINISHED",
    "HELD",
    "INTERRUPTION_DAYS",
    "NOT_PERMITTED",
    "NO_FAVOUR",
    "NO_PERIOD",
    "NO_SUBJECT",
    "NO_WANTING",
    "ON_TOPIC_FLOOR",
    "REASONS",
    "Stakes",
    "TOPIC_UNRAISED",
    "TrustLedger",
    "TrustView",
    "Unasked",
    "UnaskedQueue",
    "VISIBLE",
    "Verdict",
    "asks_at",
    "considered",
    "delivered",
    "may_be_raised",
    "narrowed_for_trust",
    "on_topic",
    "queue",
    "spent",
    "tombstoned",
    "verdicts",
]
