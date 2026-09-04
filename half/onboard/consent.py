"""What the main is told, and when — before a source is connected (CAP-2).

**The launch blocker's own moment.** Half reads somebody's mail and sends the
bodies to a model provider. The sentence that says so has to be delivered
before the connection happens and as its own message, not folded into a footer
under something more interesting — which is the whole content of this module:
``told`` is a predicate the flow asks *before* it touches a mailbox, and a
deployment that cannot answer it connects nothing.

**This module ships no wording, in any language, and that is the design.** The
notice is a *machine name* here — ``leaves_the_machine`` — and the sentence
that carries it is supplied by the deployment, in the main's own language.
Half ships worldwide; a privacy notice written in one language and shown to
everybody is the same failure ``half.voice.compose`` refuses for generated
prose, arriving one rung earlier and with more at stake, because a notice
nobody can read is a notice nobody was given. ``tests/test_onboard.py`` walks
this file's syntax tree and fails the build if a module-level string constant
here ever contains a space, which is the shape a sentence has and a machine
word does not.

**Fail closed, and the failure is visible.** No wording means no notice, and no
notice means no source is connected and no demonstration happens — not a
demonstration that quietly skipped the sentence. That direction is the only one
available: the alternative is connecting a mailbox on behalf of somebody who
was told nothing, which is the harm the sentence exists to prevent.

**A closed set with one member, and it is a set on purpose.** ``NOTICES``
enumerates what must be said, so adding a second thing the main must be told is
one edit in one place and is picked up by ``missing``, ``told`` and every case
that sweeps the set — rather than a second ``if`` somewhere in the flow that
the next surface forgets. One member today is what story 7 funds; the rule for
adding is that a notice belongs here only if it must be said *before* Half has
anything of the main's to say.

Pure and stdlib-only. No clock, no network, no model, no store: telling
somebody something is the caller's act, and this module only ever answers
whether there is anything to tell them and what it is.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import Any, Final

from half.context.channels import sanitize
from half.errors import OnboardError

#: The one thing the main must be told before a source is connected: that their
#: messages leave the machine.
#:
#: **A machine name and never a sentence.** The wording is the deployment's, in
#: the main's own language; what this constant is, is the *key* the deployment
#: supplies that wording under. See the module docstring, and the structural
#: case that keeps it true.
LEAVES_THE_MACHINE: Final[str] = "leaves_the_machine"

#: Everything that must be said before a source is connected, in the order it
#: is said. Closed.
NOTICES: Final[tuple[str, ...]] = (LEAVES_THE_MACHINE,)

#: What separates one notice from the next when several are delivered together.
#:
#: A blank line, so that two notices read as two sentences rather than one run
#: — and **not** a bullet, a number or a label, which would make a notice into a
#: form and put CAP-4's own refusal on the first screen the main ever sees.
JOIN: Final[str] = "\n\n"


@dataclass(frozen=True, slots=True)
class Consent:
    """The wording a deployment has for each notice. A value; it tells nobody.

    ``wording`` maps a name from ``NOTICES`` to the sentence that carries it,
    in the main's own language. Anything that is not a non-empty string under a
    name this build knows is dropped at construction rather than carried: a
    notice whose "wording" is ``None``, a number or a blank line is a notice
    the main would not have been given, and the honest reading of that is that
    the deployment has none.

    Sanitized with ``half.context.channels.sanitize``, the same function every
    other body on the wire goes through, so a notice cannot forge a line break
    into whatever it is sent beside.

    **Frozen and normalised, so ``told`` cannot be made true after the fact.**
    A consent object that could gain a notice after the flow read it is a
    consent check that answers about a different value than the one that was
    used.
    """

    wording: Mapping[str, str] = MappingProxyType({})

    def __post_init__(self) -> None:
        given: Any = self.wording
        if given is None:
            given = {}
        if not isinstance(given, Mapping):
            raise OnboardError(
                f"consent wording must be a mapping of notice to sentence, "
                f"got {type(given).__name__}. A deployment that cannot say "
                "which notice a sentence carries has not written the notice"
            )
        kept = {}
        for name in NOTICES:
            value = given.get(name)
            if not isinstance(value, str):
                continue
            said = sanitize(value)
            if said:
                kept[name] = said
        object.__setattr__(self, "wording", MappingProxyType(kept))


#: The absence of any consent at all. A deployment that has written nothing.
NOTHING_TOLD: Final[Consent] = Consent()


def missing(consent: Consent | None) -> tuple[str, ...]:
    """Which required notices this deployment has no wording for.

    In ``NOTICES``' own order, so an operator reading the answer is reading the
    order the notices would have been said in. Empty means everything required
    can be said.

    ``None`` is every notice missing, which is the same answer as an empty
    ``Consent`` and deliberately so: *nobody built one* and *somebody built an
    empty one* are the same fact about what the main would hear.
    """
    have = consent.wording if isinstance(consent, Consent) else {}
    return tuple(name for name in NOTICES if name not in have)


def told(consent: Consent | None) -> bool:
    """Whether every required notice has wording to deliver.

    **The predicate the flow reads before it connects a source, and the one the
    suite reads.** One function rather than a condition written out in each —
    this project has twice shipped a guard the tests approximated with a scan
    for a spelling, and a predicate can be swept exhaustively against an
    independently written expectation while a scan can only be as clever as
    whoever wrote it.

    False is not an error. It is a deployment that has not written its notice,
    and the honest consequence is that no mailbox is connected for that main.
    """
    return not missing(consent)


def notice(consent: Consent | None) -> str:
    """The notice to deliver, as one message, or ``""``.

    Every required notice, in ``NOTICES`` order, joined by ``JOIN``. ``""``
    when anything required is missing — **all or nothing**, because a partial
    notice is a main who was told some of it and connected anyway, which is
    worse than a deployment that is visibly unconfigured.

    This is a whole message and is sent on its own. It is never appended to the
    demonstration: the sentence about mail leaving the machine arriving under a
    claim about the main is exactly the footer this story exists to refuse, and
    ``half.onboard.flow`` sends it before it has read a single message.
    """
    if not isinstance(consent, Consent) or not told(consent):
        return ""
    return JOIN.join(consent.wording[name] for name in NOTICES)


def _check_constants() -> None:
    """Import-time invariants, as raises rather than bare ``assert``.

    A guarantee ``python -O`` removes is not a guarantee, and *the notice set is
    closed and carries no wording* is exactly the kind an optimisation flag
    would take away while the module still imported cleanly.
    """
    if not NOTICES:
        raise OnboardError(
            "the notice set is empty, so `told` is true for a deployment that "
            "says nothing and every mailbox connects with the main told "
            "nothing at all"
        )
    if len(set(NOTICES)) != len(NOTICES):
        raise OnboardError(f"a notice is named twice: {NOTICES}")
    for name in NOTICES:
        if not isinstance(name, str) or not name or any(c.isspace() for c in name):
            raise OnboardError(
                f"{name!r} is not a notice name. A name is a machine word; the "
                "sentence that carries it belongs to the deployment, in the "
                "main's own language, and never to this file"
            )


_check_constants()

__all__ = [
    "JOIN",
    "LEAVES_THE_MACHINE",
    "NOTHING_TOLD",
    "NOTICES",
    "Consent",
    "missing",
    "notice",
    "told",
]
