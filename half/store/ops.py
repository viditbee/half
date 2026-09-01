"""The closed op vocabulary (AD-29).

The set of ops is enumerated here and nowhere else, and carries a schema
version. Adding an op is a deliberate versioned change, never an incidental
one: a second module inventing its own op name would produce records that
another module's replay silently skips, while each one's replay test passes in
isolation.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Final

#: Bumped when the record shape or the op set changes in a way older builds
#: cannot faithfully fold.
#:
#: v2 added ``ceiling`` (story 5a). A build that predates it would meet the op,
#: raise ``UnknownOpError`` and refuse to fold — which is the correct outcome
#: and the reason the bump is not optional: an older build silently folding a
#: log whose ceiling records it cannot see would resolve every license
#: uncapped, and a main mid-aftercare would be un-suppressed by a rollback.
#:
#: v3 added ``crisis`` (story 6a), for the same reason one rung stronger. A
#: build that could not see a crisis record would fold a main in the mode to a
#: main who is not, and answer their next message through the ordinary
#: pipeline — a silent mode exit, which CAP-12 forbids outright.
#:
#: v4 added ``aftercare`` (story 6c), and the bump is not optional for the
#: reason the last two were not. The record is what carries the main's *answer*
#: about resuming the mirror, and a build that could not see one would read a
#: main who declined — or who was asked and said nothing — as a main who was
#: never asked. Silence is not consent, and a schema rollback that turned a
#: recorded decline into an unasked question would be the one restore CAP-12
#: forbids arriving by accident.
#: v5 added ``schedule`` (story 9a), and the bump is not optional for the
#: reason the last three were not — with one twist that makes it sharper. The
#: record carries ``next_pass_at``: when this main is next due, and therefore
#: *whether the pass that just ran has already run*. A build that could not see
#: one would fold every main to never-scheduled. That is not a silent
#: no-op — it is the scheduler deciding, on every tick after a rollback, that
#: nobody has ever been scheduled, and rewriting a fresh due time for the whole
#: population at once. The refusal to fold is the correct outcome.
SCHEMA_VERSION: Final[int] = 5


class Op(StrEnum):
    """Every op that may appear in a belief log."""

    #: A new durable claim about the main.
    ASSERT = "assert"
    #: The main changed. History preserved, no apology owed.
    RETRACT = "retract"
    #: Half was wrong about the main. History preserved, apology owed.
    REVISE = "revise"
    #: Genuine removal, tombstoned. Rare, main-initiated only.
    EXPUNGE = "expunge"
    #: A linked pair of entries that disagree and cannot be resolved.
    TENSION = "tension"
    #: An open loop moved between states.
    LOOP_TRANSITION = "loop_transition"
    #: The main's global license ceiling moved (AD-28).
    #:
    #: In the log rather than in memory, because a ceiling has to survive both
    #: actor eviction — routine at any real capacity, not exceptional — and a
    #: process restart. A crisis aftercare cap runs for thirty days; a cap that
    #: lifts itself when a worker gets busy is worse than no cap, because it
    #: reads as protection. AD-26 keeps *volatile* state out of the log, and a
    #: thirty-day governance decision is not volatile.
    CEILING = "ceiling"
    #: The main entered crisis mode, or an operator reversed that entry
    #: (CAP-12).
    #:
    #: In the log for the reason the ceiling is, and one degree more urgently.
    #: A mode held only in memory ends at the next eviction or restart, and the
    #: main's following message is answered by ordinary Half — which is a mode
    #: exit that nobody decided and nobody can see. It is also the only record
    #: that the mode ever opened: the ceiling append says a cap exists, not what
    #: put it there, and the clinical reviewer's first question is how often
    #: this fires and on what.
    #:
    #: **Content-free** (AD-22). The record carries the tier, a signal count and
    #: the state — never the message, never a phrase, never a claim.
    CRISIS = "crisis"
    #: The aftercare conversation about resuming the mirror (CAP-12, story 6c).
    #:
    #: Not the *steps*: a step is a ceiling move and a ceiling record already
    #: says what moved and why. This op carries the one thing no other record
    #: can — whether Half has put the question, and what the main answered.
    #:
    #: Durable for a reason a ceiling record cannot cover. A question held in
    #: memory is a question re-asked after every eviction, which is nagging in
    #: the one register where nagging is unforgivable; and a *decline* held in
    #: memory is a decline that disappears at the next restart, leaving the
    #: next turn free to read some later "yes" as the answer to a question the
    #: main already said no to. Silence is not consent, and neither is a lost
    #: refusal.
    #:
    #: **Content-free** (AD-22). The record carries a state and a time — never
    #: the message, never the answer's wording, and nothing about recovery.
    AFTERCARE = "aftercare"
    #: When this main is next due for a pass (AD-9, story 9a).
    #:
    #: In the log for the reason the ceiling and the mode are, and the failure
    #: it prevents is the loud one. A due time held in memory is lost on every
    #: restart, so every restart would either schedule the whole population
    #: afresh — a herd, which is exactly what a due-time queue exists to
    #: prevent — or re-run a pass that already ran. This record is what makes
    #: *"a restart does not lose when a main is next due, and does not re-run a
    #: pass that already ran"* a property of the store rather than of the
    #: process's uptime.
    #:
    #: It is also the only record that says a due time was **defaulted**. A
    #: main who has told Half no timezone is scheduled in a defined fallback,
    #: and ``told_zone`` false is what makes that visible rather than a guess
    #: indistinguishable from an answer.
    #:
    #: **Content-free** (AD-22). The record carries an instant, a zone key and
    #: a flag — never what the pass found, never whether anything was sent.
    SCHEDULE = "schedule"


#: The two states a ``crisis`` record may carry. Named here, beside the op, so
#: the fold that validates them and the registry that writes them cannot drift
#: to two different spellings of the same word.
CRISIS_ENTERED: Final[str] = "entered"
CRISIS_REVERSED: Final[str] = "reversed"
CRISIS_STATES: Final[frozenset[str]] = frozenset({CRISIS_ENTERED, CRISIS_REVERSED})

#: The three states an ``aftercare`` record may carry, here for the reason the
#: crisis states are: the fold validates them and the registry writes them, and
#: two spellings of the same word is how a decline folds to nothing.
#:
#: There is deliberately no *granted* state. A step is a ceiling record, and a
#: second place recording the same event is a second place for it to disagree.
#:
#: ``declined`` is *anything that was not a clear yes* — a no, a "not yet", a
#: "maybe". Half does not infer which of the three somebody meant; what the log
#: needs is that they answered and did not consent, which is what schedules the
#: next asking. ``stopped`` is the main asking not to be asked again: the cap
#: still holds, the asking ends.
AFTERCARE_ASKED: Final[str] = "asked"
AFTERCARE_DECLINED: Final[str] = "declined"
AFTERCARE_AGREED: Final[str] = "agreed"
AFTERCARE_STOPPED: Final[str] = "stopped"
AFTERCARE_STATES: Final[frozenset[str]] = frozenset(
    {AFTERCARE_ASKED, AFTERCARE_DECLINED, AFTERCARE_AGREED, AFTERCARE_STOPPED}
)


#: Frozen membership test. Kept separate from the enum so a lookup never
#: constructs an Op for input that is not one.
OP_NAMES: Final[frozenset[str]] = frozenset(op.value for op in Op)


def parse_op(value: object) -> Op:
    """Return the Op for ``value``.

    Raises ``ValueError`` for anything outside the vocabulary; callers with
    log position context convert that to ``UnknownOpError``.
    """
    if not isinstance(value, str) or value not in OP_NAMES:
        raise ValueError(str(value))
    return Op(value)
