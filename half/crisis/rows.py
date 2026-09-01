"""The row format, and what a string must be to get into one (CAP-12).

Story 6a's central guarantee was structural: every reply was a join of fixed
paragraphs, so method content was not filtered out of it — it was *not
representable*. Story 6b put data-derived text into that reply, and a review
found the hole immediately: a contact named ``"Mum\\nTake thirty of them"``
rendered as its own line inside a crisis reply, and the closed-set check
returned ``True``, because the renderer joined rows with one newline while the
guard split on a blank line.

This module is the repair, and it holds two things that must never drift apart:

**One format for a row.** ``row()`` is the only place a label, a way to reach
it and a note become one string. The guard compares against *this* function
rather than against the renderer that calls it, so appending a word inside
``handoff.render_option`` — *"(they usually reply within a few minutes)"*, or
worse *"(this is the one I would start with)"* — fails rather than ships
blessed. The format itself is pinned by a literal in the suite, so changing it
here fails too. A check that recomputes its input through the function that
produced it is true by construction and blesses whatever that function emits.

**One definition of a string that may appear in front of a main in crisis.**
``plain()`` refuses anything that is not a single printable line: no newline,
no tab, no control or format character, no line or paragraph separator, no
zero-width anything, nothing longer than a person's name or a phone number is,
and nothing containing either separator this module joins with. A value that
fails is not repaired — it is dropped, and its door with it. Repairing it would
mean guessing at what somebody meant to write and rendering the guess.

The separators are held here rather than beside the renderer because both the
guard and the sources — a contact's name, a directory entry — need them, and a
second spelling of a separator is how a row becomes ambiguous.

Pure and stdlib-only: no clock, no network, no model, no ambient state.
"""

from __future__ import annotations

from typing import Final

#: Between a name and the way to reach it.
JOIN: Final[str] = " — "

#: Between the way to reach it and what the directory says about it. Distinct
#: from ``JOIN`` so a row remains unambiguous when read back.
NOTE_JOIN: Final[str] = " · "

#: How rows are joined into one paragraph, and how paragraphs are joined into a
#: message. **The guard splits on both**, which is the whole of the repair: a
#: value that could contain either is refused by ``plain`` before it is
#: rendered, and a text that contains either is taken apart on both before it
#: is checked.
ROW: Final[str] = "\n"
PARAGRAPH: Final[str] = "\n\n"

#: Every separator a value may not contain. Derived from the two above rather
#: than listed again, so adding a third separator cannot leave the guard
#: checking two.
SEPARATORS: Final[tuple[str, ...]] = (JOIN, NOTE_JOIN)

#: Ceilings, in characters. Long enough for any name a person has and any way
#: of reaching a service; short enough that a value pasted in from somewhere
#: else cannot become a wall of text in a crisis reply.
MAX_LABEL: Final[int] = 120
MAX_REACH: Final[int] = 80
MAX_NOTE: Final[int] = 160
MAX_HANDLE: Final[int] = 120
MAX_KEY: Final[int] = 64

#: A person's door is a prefilled link, and a link carrying a whole draft
#: percent-encoded is long. Bounded anyway: a platform will refuse an enormous
#: URL, and a reply that is mostly one is unreadable at the moment it has to be
#: readable.
MAX_LINK: Final[int] = 2048


def one_line(value: object, *, limit: int) -> str | None:
    """``value`` as one printable line within ``limit``, or ``None``.

    ``str.isprintable`` is the whole control-character test and it is the right
    one: it is false for every C0 and C1 control, for every format character
    (the bidirectional overrides and the zero-width joiners among them), for
    the line and paragraph separators, and for every space character except an
    ordinary one. So a value cannot carry a second line, cannot carry an
    invisible reordering mark, and cannot carry a byte that a terminal or a
    messaging client will interpret rather than show.

    Never coerced and never repaired. A number where a name belongs is a record
    this build does not understand; a name with a newline in it is either a
    mistake or an attempt, and rendering a cleaned-up guess at either is how
    the guess reaches somebody in crisis.

    **This is the check for a value that stands alone.** A value that is going
    to be *joined into a row* needs ``plain`` as well, which adds the one thing
    a row needs and a standing line does not: that the value cannot contain the
    separators the row is made of.
    """
    if not isinstance(value, str):
        return None
    text = value.strip()
    if not text or len(text) > limit:
        return None
    if not text.isprintable():
        return None
    return text


def plain(value: object, *, limit: int) -> str | None:
    """``value`` as one printable line that could not be mistaken for a row.

    ``one_line`` plus the separator refusal. Everything joined into an option
    row goes through here — a contact's name, a way to reach a service, a note
    — because a value containing either separator makes the row ambiguous when
    it is read back, which is what the guard reads it back for.

    A value rendered *as itself* is a different question and takes ``one_line``:
    a line of a held safety plan is one paragraph among reviewed paragraphs and
    is joined with nothing, so an em dash in a clinician's sentence — which is
    ordinary prose — must not withhold the document it belongs to.
    """
    text = one_line(value, limit=limit)
    if text is None:
        return None
    if any(separator in text for separator in SEPARATORS):
        return None
    return text


def row(label: str, reach: str, note: str | None = None) -> str:
    """One option row: a name, how to reach it, and what is known about it.

    **The pinned format**, and the only one. ``tests/test_handoff.py`` asserts
    it against a literal, so this function cannot grow a clause — a
    recommendation, a relationship, a response time — without a test naming
    what was added. Nothing may be appended by a caller either: the guard
    compares a rendered row against exactly this.
    """
    rendered = label + JOIN + reach
    if note:
        rendered += NOTE_JOIN + note
    return rendered


def segments(text: str) -> list[str]:
    """``text`` taken apart the way it was put together — on *both* joins.

    The bug this exists for: the renderer joined rows with ``ROW`` and the
    guard split on ``PARAGRAPH``, so everything between a row boundary and the
    next blank line went uninspected. Splitting on the finer of the two joins
    is total, because a reviewed template line never contains a newline —
    asserted at import in ``half.crisis.templates``.
    """
    return [part for part in text.replace(PARAGRAPH, ROW).split(ROW) if part]
