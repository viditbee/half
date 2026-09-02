"""The bought question: minting, the answer state, and the composition (CAP-4).

`half.trust` answers *may Half spend the relationship on a question right now*.
This package is what finally spends it. Story 5b built the currency, the gates
and the spend and **nothing called them**: an `ask`-rung belief became a
``Question`` inside the context builder, the morning surface put that line on
the wire, and no favour was ever spent. CAP-4's central rule — *"no question is
asked that was not preceded by a delivered favor"* — was enforced in a package
with no production caller.

**The caller is ``half.actor.runtime``, and only that.** *"The favour buys the
question"* says when; *"attach the question to the next conversation that already
touches the topic, never ping to ask"* says where. 5b's topic gate reads the
actor's live strands, which exist on a conversation turn and nowhere else, so
the question rides on a reply the main was owed anyway. The morning surface does
not ask and cannot: nothing under ``half/surface`` can resolve an import into
this package, which ``tests/test_bought.py`` asserts.

Three modules, and the split is the story:

* ``mint`` — one ``Unasked`` per belief, its id **derived** from the belief id,
  so that asking the same thing twice is recognizable as a re-ask rather than
  arriving as a new question every time. Pure, and it decides nothing.
* ``answered`` — whether a question that was put has been *responded to*, folded
  out of the log and never stored (AD-3, AD-30). Read its docstring for the
  limit it carries: it recognizes responsiveness, not answering.
* ``engine`` — the composition. Mint, drop what is inside its own wanting's
  period, gate through 5b's own door, spend, and hand the bought belief to the
  context builder.

**The bound on re-asking is the wanting's own period**, read from
``half.loops.timescale.PERIOD_DAYS`` through the stakes value the gates already
compute — the same table ``timescale.silence`` and ``choose.touchable`` read.
Not a global cooldown: gbrain's ``NUDGE_COOLDOWN_DAYS = 14`` nags a workout
routine and never once reaches a farmland loop, which is why story 10 refused it
for ``touchable`` and why it is refused again here.

**Nothing here composes a sentence.** There is no text on any value in this
package, no template in any language, and no channel reachable from any of these
modules — Half ships worldwide and a hand-written English question is the
objection ``half.context.channels`` already records. What a question *says* is
the wire-text blocker, which affects the content channel equally and is not a
question problem.

**Nothing here writes.** ``mint`` and ``answered`` are pure functions; the
engine reaches a main's log only through the narrow, injected doors 5b
established, because a second path to a main's store is a second writer and the
single writer is what lets the store skip a journal (AD-1).
"""

from half.questions.answered import (
    ANSWERED,
    ANSWERS_WITHIN_DAYS,
    NEVER_ASKED,
    NO_PERIOD,
    REASONS,
    TOO_SOON,
    UNREADABLE_ASK,
    UNREADABLE_NOW,
    Answer,
    Reask,
    history,
    reaskable,
    responsive,
    spend_of,
)
from half.questions.engine import (
    ASK_OUTCOMES,
    NOTHING_OFFERED,
    Purchase,
    QuestionEngine,
    QuestionLedger,
    QuestionView,
    offered,
)
from half.questions.mint import QUESTION_PREFIX, about_of, mint, minted, question_id

#: **Every name a caller reads an outcome against**, for the reason
#: ``half.trust.__all__`` carries its reason constants: ``Reask.reason`` is
#: documented as a closed set, and a closed set whose members are not importable
#: beside the type is one every consumer re-spells.
__all__ = [
    "ANSWERED",
    "ANSWERS_WITHIN_DAYS",
    "ASK_OUTCOMES",
    "Answer",
    "NEVER_ASKED",
    "NOTHING_OFFERED",
    "NO_PERIOD",
    "Purchase",
    "QUESTION_PREFIX",
    "QuestionEngine",
    "QuestionLedger",
    "QuestionView",
    "REASONS",
    "Reask",
    "TOO_SOON",
    "UNREADABLE_ASK",
    "UNREADABLE_NOW",
    "about_of",
    "history",
    "mint",
    "minted",
    "offered",
    "question_id",
    "reaskable",
    "responsive",
    "spend_of",
]
