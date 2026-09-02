"""One question per belief, with an id derived from the belief's (CAP-4).

Pure, total, clockless, and deliberately the smallest module in the package: it
turns a belief id into the ``Unasked`` value ``half.trust`` weighs, and it
decides nothing else.

**The id is derived, never minted fresh, and that is the whole point.** A
question whose id came from a counter, a stamp or a random draw would be a
*different* question every time Half considered asking it — so a question the
main ignored last week would arrive as a brand-new one this week, the log would
hold two unrelated ``asked`` records for one uncertainty, and no fold over that
log could ever say *"this was already put to them"*. Re-asking would then be
bounded by nothing but the balance, which is exactly the nag this story exists
to prevent. Deriving the id makes a re-ask **recognizable**: ask the same thing
twice and the second record names the first one's question.

The derivation is a prefix and the belief id, in that order and nothing else. It
is reversible (``about_of``), which is what lets ``half.questions.answered`` fold
an ``asked`` record back onto the wanting whose period bounds it, and it carries
no text, no locale and no wording (AD-22).

**Whether a belief may be raised at all is not decided here.** That is the
ladder's answer under this main's ceiling, and ``half.trust.unasked.considered``
asks it through ``may_be_raised`` — the one predicate the runtime and the tests
both read. A second rung check here would be a second opinion about one
question, and the two would disagree the first time a ceiling moved. So this
module mints for whatever it is handed and every gate still runs afterwards:
what reaches the main is *one question per `ask`-rung belief*, and it is the
gates rather than the mint that make the rung part of that sentence true.
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Final

from half.trust.unasked import Unasked

__all__ = ["QUESTION_PREFIX", "about_of", "mint", "minted", "question_id"]

#: What a derived question id begins with.
#:
#: A prefix rather than a hash or a stamp, because the derivation has to be
#: reversible: ``half.questions.answered`` folds ``asked`` records out of the
#: log and has to place each one against the belief — and therefore against the
#: wanting whose period bounds re-asking. A one-way id would leave the log
#: holding question ids nothing could ever attribute.
#:
#: ``q_`` follows the identity convention in the spine's table: belief ids are
#: ``b_<hex>``, tension ids ``x_<hex>``, source ids ``s_<hex>``. A question id is
#: not in that table because a question is not a stored object — it is one
#: field of an ``asked`` record — so the prefix is named here, once, beside the
#: only function that writes it.
QUESTION_PREFIX: Final[str] = "q_"


def question_id(belief_id: object) -> str:
    """The id of the one question about ``belief_id``, or ``""``.

    Total: anything that is not a usable belief id yields the empty string,
    which ``Unasked.nameable`` reads as *not a question*, so a malformed value
    is refused at the first gate rather than raising on a turn's own path.

    Stripped before it is prefixed, for the reason ``Unasked`` strips both of
    its fields: the id that is weighed has to be the id that is written, and an
    id built from an unstripped value would be looked up one way and recorded
    another.
    """
    if not isinstance(belief_id, str):
        return ""
    trimmed = belief_id.strip()
    return f"{QUESTION_PREFIX}{trimmed}" if trimmed else ""


def about_of(question: object) -> str:
    """The belief ``question`` is about, or ``""``. The inverse of ``question_id``.

    Read by ``half.questions.answered`` to place an ``asked`` record from the
    log against the wanting whose period bounds the next ask. It reads the
    *derivation* rather than the record's own ``about`` field where it can,
    because the two must agree and only one of them is computed here — but a
    caller that has the record has both, and ``tests/test_questions.py`` pins
    them to one answer.
    """
    if not isinstance(question, str):
        return ""
    trimmed = question.strip()
    if not trimmed.startswith(QUESTION_PREFIX):
        return ""
    return trimmed[len(QUESTION_PREFIX):]


def mint(belief_id: object) -> Unasked | None:
    """The one question about ``belief_id``, or ``None``.

    ``None`` for anything that cannot name a belief. There is no second question
    about the same belief and no way to ask for one: the id is a function of the
    belief id, so two calls give one value and a re-ask is the same question.
    """
    ident = question_id(belief_id)
    if not ident:
        return None
    minted_one = Unasked(id=ident, about=str(belief_id).strip())
    return minted_one if minted_one.nameable else None


def minted(belief_ids: Iterable[object] | None) -> tuple[Unasked, ...]:
    """One question per belief in ``belief_ids``, in order, deduplicated.

    Order is the caller's — the ranking above this module decided it, and
    nothing here re-sorts, so no collation and therefore no locale is involved.
    Ranking by what a mistake would cost is ``half.trust.unasked.Ask.order``'s
    job and happens after every gate has run.

    Deduplicated on the derived id, which is the same thing as deduplicating on
    the belief: a candidate set naming one belief twice must not look like two
    questions competing for one favour.
    """
    found: list[Unasked] = []
    seen: set[str] = set()
    for belief_id in belief_ids or ():
        one = mint(belief_id)
        if one is None or one.id in seen:
            continue
        seen.add(one.id)
        found.append(one)
    return tuple(found)
