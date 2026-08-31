"""Salience: how much a belief is worth surfacing, computed from folded state.

**Derived, never counted (AD-30).** The tempting implementation bumps a counter
each time a belief is retrieved. That makes materialized state a function of
read traffic rather than of the log, so replaying one log twice — once on a
box that answered a hundred queries and once on a fresh restore — produces two
different states. AD-4's byte-identical guarantee would then be false, and the
first symptom would be an export that does not reconstruct. Nothing in this
module writes anything; every input is a field the log already carries.

**No clock.** ``now`` is injected by the caller. A salience that read the clock
would make retrieval untestable and non-reproducible for exactly the reason
above.

Three components, combined as a weighted mean rather than a product so that one
zero cannot annihilate a belief (AD-24 — weight, never exclude):

* **independence** — how many genuinely separate supports the claim has. Ten
  mentions in one thread are one support, which ``half.ingest.independence``
  already collapsed before the number was written.
* **corroboration freshness** — how long since anything confirmed it. A claim
  last seen two years ago is still true and still reachable; it just stops
  outranking one confirmed last week.
* **loop state** — the open-loop ledger is the ranking function for everything
  Half does, so a belief attached to an advancing loop outranks an equally
  matched belief attached to nothing.
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime, timezone
from typing import Any, Final

#: Salience never reaches zero. A belief nothing has corroborated in a decade,
#: on no loop, with one support, must still be retrievable.
FLOOR: Final[float] = 0.2

#: Supports needed for a claim to sit halfway up the independence curve.
INDEPENDENCE_MIDPOINT: Final[float] = 2.0

#: Days after which un-recorroborated evidence counts for half as much.
CORROBORATION_HALF_LIFE_DAYS: Final[float] = 90.0

#: Relative pull of each component. Independence and freshness are the
#: evidential half; the loop is the wanting half.
WEIGHTS: Final[Mapping[str, float]] = {
    "independence": 0.35,
    "corroboration": 0.35,
    "loop": 0.30,
}

#: What a loop's state says about the beliefs sitting on it. A loop is never
#: refuted, only transitioned (AD-26), so every state has a weight and none is
#: zero — an achieved loop's beliefs are still part of the person.
LOOP_STATES: Final[Mapping[str, float]] = {
    "advancing": 1.0,
    "stalled": 0.6,
    "abandoned-but-unadmitted": 0.5,
    "achieved": 0.2,
}

#: A belief on a loop whose state this build does not recognise. Above
#: ``NO_LOOP`` because being on a loop at all is information.
UNKNOWN_LOOP_STATE: Final[float] = 0.4

#: A belief attached to no loop. Deliberately not zero.
NO_LOOP: Final[float] = 0.3


def salience(
    belief: Mapping[str, Any],
    *,
    now: datetime,
    loops: Mapping[str, Mapping[str, Any]],
) -> float:
    """Salience of ``belief`` in ``[FLOOR, 1.0]``. Higher surfaces sooner."""
    components = {
        "independence": independence_weight(belief.get("independent")),
        "corroboration": corroboration_weight(belief.get("last_corroborated"), now),
        "loop": loop_weight(belief.get("loop"), loops),
    }
    total = sum(WEIGHTS.values())
    raw = sum(WEIGHTS[name] * value for name, value in components.items()) / total
    return FLOOR + (1.0 - FLOOR) * raw


def independence_weight(independent: object) -> float:
    """Independent supports, saturating: 0 -> 0.0, 2 -> 0.5, 10 -> 0.83.

    Saturating rather than linear because the difference between one support
    and three is a different kind of claim, while the difference between eleven
    and thirteen is noise.

    Any real number is accepted, not just ``int``. This build writes an int and
    ``db.rebuild`` refuses anything else, so a float can only reach here from a
    log another build wrote — and scoring that belief as having *no* support at
    all is a worse answer than reading the number it actually carries.
    """
    if isinstance(independent, bool) or not isinstance(independent, (int, float)):
        return 0.0
    count = max(0.0, float(independent))
    return count / (count + INDEPENDENCE_MIDPOINT)


def corroboration_weight(last_corroborated: object, now: datetime) -> float:
    """Half-life decay since ``last_corroborated``.

    A belief that was never corroborated, or whose stamp this build cannot
    read, scores 0 for this component — not for salience overall, which has a
    floor. Nothing is excluded; it simply stops winning ties.
    """
    stamp = parse_time(last_corroborated)
    if stamp is None:
        return 0.0
    age = days_between(now, stamp)
    return 0.5 ** (age / CORROBORATION_HALF_LIFE_DAYS)


def loop_weight(loop: object, loops: Mapping[str, Mapping[str, Any]]) -> float:
    """What the loop this belief sits on is doing right now."""
    if not isinstance(loop, str) or not loop:
        return NO_LOOP
    entry = loops.get(loop)
    if entry is None:
        # The belief names a loop the ledger has no transition for yet. It is
        # on a loop; the ledger just has not heard from it.
        return UNKNOWN_LOOP_STATE
    state = entry.get("state")
    if not isinstance(state, str):
        return UNKNOWN_LOOP_STATE
    return LOOP_STATES.get(state, UNKNOWN_LOOP_STATE)


def parse_time(value: object) -> datetime | None:
    """An ISO-8601 stamp from the log as an aware UTC datetime, or ``None``.

    Tolerant on the way in and strict on the way out: log records carry
    ``2026-08-01T00:00Z`` for beliefs and bare ``2026-03-12`` dates for loop
    movement, and a naive stamp is read as UTC because that is what the
    conventions say every stored timestamp is.

    Returns ``None`` rather than raising. A single unreadable stamp must cost
    that belief a tie-break, not take retrieval down for the whole main.
    """
    if not isinstance(value, str) or not value.strip():
        return None
    text = value.strip()
    if text.endswith(("Z", "z")):
        text = f"{text[:-1]}+00:00"
    try:
        moment = datetime.fromisoformat(text)
    except ValueError:
        return None
    if moment.tzinfo is None:
        return moment.replace(tzinfo=timezone.utc)
    return moment.astimezone(timezone.utc)


def days_between(later: datetime, earlier: datetime) -> float:
    """Days from ``earlier`` to ``later``, clamped at zero.

    A stamp in the future is treated as now rather than as negative age, so a
    clock-skewed source cannot buy a belief unbounded salience.
    """
    return max(0.0, (later - earlier).total_seconds() / 86400.0)
