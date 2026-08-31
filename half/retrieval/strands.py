"""Strand match: what the conversation is about, as a weight (CAP-1, AD-24).

A **strand** is a thing a conversation can be about — a loop, a person, a
topic, a subject. Every message is scored against the strands the main's own
store already contains, and the scores move: a topic switch shifts weight from
one strand to another rather than firing an event or opening a workspace.

**The load-bearing property is the floor.** ``strand_weight`` returns
``STRAND_FLOOR`` for a belief on no live strand, never zero. A multiplier that
could reach zero would let a topic switch empty the candidate set, and an empty
candidate set is what makes Half say *"I don't have access to that"* — the one
sentence the spec rejects outright (AD-24). This module reorders. It has no
code path that removes a candidate, and ``test_strands.py`` asserts that
behaviourally rather than trusting the comment.

**One tokenizer.** Splitting is ``half.text``'s job, shared with the prefix
builder and the store's query builder. This module used to split on
``[a-z0-9]+``, so a person or loop named in any non-Latin script could never
become a live strand — the matcher found no tokens on either side. Comparison
uses the folded form, so ``Café`` and ``cafe`` are one strand and not two, and
it runs over ``half.text.tokens``, which n-grams a scriptio-continua run: a
strand named ``転職`` sits unspaced inside ``転職を考えている`` and a matcher
comparing whole words finds no overlap there at all.

**Exact tokens, never fuzzy.** HippoRAG maps a generated fact back onto its
candidates with ``difflib.get_close_matches(..., cutoff=0.0)``, and a cutoff of
zero always returns *something* — the nearest string, however unrelated. That
is a mis-mapping waiting for its first unusual input. Matching here is exact
token overlap: a strand that shares no token with the message scores zero and
falls back to the floor, which is the honest answer.

**Volatile (AD-26).** Weights live with the actor and die with it. They are
never written to the log, never projected, and never restored — they are how
the main is *right now*, and how the main is right now is not a belief.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from typing import Any, Final

from half.text import tokens

#: Weight of a belief matching no live strand. Strictly positive, by decision.
STRAND_FLOOR: Final[float] = 0.5

#: How much of the previous turn's attention survives this one. A topic switch
#: should move weight in a couple of turns, not in one and not in twenty.
DECAY: Final[float] = 0.5

#: Below this a strand is forgotten rather than kept as a rounding artefact.
EPSILON: Final[float] = 1e-3

#: Fields a belief can carry that name a strand, and the namespace each gets.
#: Namespaced so a person called "Farmland" and the loop ``buy-farmland`` stay
#: two different strands.
_SINGULAR: Final[Mapping[str, str]] = {"loop": "loop", "subject": "subject"}
_PLURAL: Final[Mapping[str, str]] = {"people": "person", "topics": "topic"}

def strands_of(belief: Mapping[str, Any]) -> frozenset[str]:
    """Every strand ``belief`` sits on, as namespaced keys."""
    keys: set[str] = set()
    for field_name, namespace in _SINGULAR.items():
        value = belief.get(field_name)
        if isinstance(value, str) and value.strip():
            keys.add(f"{namespace}:{value.strip().lower()}")
    for field_name, namespace in _PLURAL.items():
        values = belief.get(field_name)
        if isinstance(values, (list, tuple)):
            for value in values:
                if isinstance(value, str) and value.strip():
                    keys.add(f"{namespace}:{value.strip().lower()}")
    return frozenset(keys)


def known_strands(
    beliefs: Iterable[Mapping[str, Any]],
    loops: Mapping[str, Mapping[str, Any]] | None = None,
) -> frozenset[str]:
    """Every strand this main's store knows about.

    Loops are included even when no belief references them yet: a loop the main
    raised once and Half has recorded nothing against is exactly the strand a
    message is most likely to be reopening.
    """
    keys: set[str] = set()
    for belief in beliefs:
        keys |= strands_of(belief)
    for loop_id in loops or {}:
        if isinstance(loop_id, str) and loop_id.strip():
            keys.add(f"loop:{loop_id.strip().lower()}")
    return frozenset(keys)


@dataclass(slots=True)
class Strands:
    """The live strand weights for one main's conversation.

    Volatile per AD-26: overwritten, expiring, never logged, gone on restart.
    """

    weights: dict[str, float] = field(default_factory=dict)

    def observe(self, text: str, known: Iterable[str]) -> None:
        """Move the weights to account for one message.

        Decay first, then raise whatever this message touched. The order
        matters: raising first would let a strand mentioned every turn drift
        below one mentioned once, which is backwards.
        """
        for key in list(self.weights):
            faded = self.weights[key] * DECAY
            if faded < EPSILON:
                del self.weights[key]
            else:
                self.weights[key] = faded

        message = tokens(text)
        if not message:
            return
        for key in sorted(known):
            overlap = _overlap(key, message)
            if overlap > 0.0:
                self.weights[key] = max(self.weights.get(key, 0.0), overlap)

    def match(self, strands: Iterable[str]) -> float:
        """How live ``strands`` are right now, in ``[0, 1]``.

        The strongest strand wins rather than the average: a belief on the loop
        the main just raised is on-topic even if it also carries four topics
        nobody has mentioned in a month.
        """
        best = max((self.weights.get(key, 0.0) for key in strands), default=0.0)
        return min(1.0, max(0.0, best))

    def copy(self) -> "Strands":
        return Strands(weights=dict(self.weights))


def strand_weight(strands: Iterable[str], live: Strands | None) -> float:
    """The retrieval multiplier for a belief on ``strands``.

    In ``[STRAND_FLOOR, 1.0]`` — never zero, never negative, never absent. This
    is the function AD-24 rests on: there is no argument for which it returns a
    value that removes a belief from consideration.
    """
    if live is None:
        return STRAND_FLOOR
    return STRAND_FLOOR + (1.0 - STRAND_FLOOR) * live.match(strands)


def _overlap(key: str, message: frozenset[str]) -> float:
    """Fraction of a strand's own tokens the message used.

    ``loop:buy-farmland`` against "still thinking about the farmland" is 0.5 —
    a partial, graded match. Nothing here consults a similarity metric that
    always returns a nearest neighbour.
    """
    _, _, label = key.partition(":")
    parts = tokens(label)
    if not parts:
        return 0.0
    return len(parts & message) / len(parts)
