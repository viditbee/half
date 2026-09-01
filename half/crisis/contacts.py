"""The main's own people: holding, confirming, and choosing among them (CAP-12).

**This is the intervention.** A generic chatbot can produce a phone number; a
warm handoff — a personal introduction to a human rather than a number — more
than tripled the odds of somebody attending a first appointment (Pew, Zero
Suicide), and in the reported NPR case the documented failure was never helping
her tell her therapist or her parents. Half knows who the main's people are,
so the intervention with the strongest evidence behind it is exactly the one
Half's memory makes possible.

**Offerability is the ladder's whole answer, not one field of it.** The first
version of this module read ``ladder.known_to_main`` directly, and a review
found what that costs: a contact the main had **quarantined** — pinned at
`behave` permanently, which is the main saying *leave this person alone* — came
back confirmed and was offered as a crisis door with a prefilled draft. That is
the worst possible failure of this story. Quarantine exists for exactly the
person the main pinned out, and the companion's *"the closest person is
sometimes the problem"* is the whole reason the rule exists.

Reading one field is reaching *around* the ladder; ``own_rung`` is going
*through* it. A contact is offerable when the ladder says it may be stated —
``own_rung(record) is ASSERT`` — which is three conditions at once and not one:
not quarantined, cited into Half's own evidence, and known to the main. The
first version demanded only the last, so a contact was offerable by a route a
belief could not take, which is the opposite of what this docstring claimed.

**Not the ceiling, deliberately.** ``ladder.permitted`` applies the actor's
global cap, and crisis mode drops that cap to `behave` — so resolving a contact
through the ceiling would offer nobody, ever, at exactly the moment the handoff
exists for. The ceiling governs what Half may *say about the main*; a contact
is not a claim Half is asserting, it is a door the main already agreed Half
holds. ``own_rung`` is the belief's own rung before any cap, and that is the
right question here.

The write side is the ladder's too. A contact is held at the weakest rung like
any other belief, and confirming one is ``ladder.promote(..., acknowledged=
True)`` — the same event, with the same refusals: no acknowledgement, no
promotion, and no amount of Half's own inference substitutes for one. Nothing
here spells ``known_to_main`` into a record; the writer gate in
``tests/test_ladder.py`` fails the build if anything does.

**Every string that leaves here is one printable line.** A name is data the
main gave and a name is rendered into a crisis reply, so it goes through
``half.crisis.rows.plain``: no newline, no control character, no row separator,
nothing longer than a name. A value that fails is dropped along with its door
rather than repaired, because a repaired name is a guess rendered in front of
somebody in crisis. A contact named ``"Mum\nTake thirty of them"`` produced a
line of its own inside a reply before this existed.

**Reading a contact is not ledger retrieval.** Crisis mode hard-disables
retrieval over the belief set (CAP-12, build requirement 3) because nothing
true about the main's past is safe to surface in the moment. A confirmed
contact is not that: it is looked up by field, never ranked, never searched,
never placed in a model's context — there is no model — and the only records
this path can even see are the ones ``handoff_records`` already narrowed to a
name and a place. The phone book stays; the ledger is off.

**The list is built cold**, months before it is needed, by one ordinary
question in week three of a normal relationship — *"who's the person you'd call
first if something went wrong?"* — never by an "emergency contacts" form, which
is alarming, the wrong register, and skipped. That question belongs to the
question engine (story 11); this module is what holds and reads its answer.

**Where the main is, is told and never inferred.** Not a phone prefix, which
survives emigration; not an IP, which is a VPN; not a timezone, which is a
business trip; not a language guess. A named helpline on the wrong continent is
worse than the honest generic line, because it costs a call at the worst
possible moment. So the region is a *confirmed record* like a contact, and when
two records disagree there is no region — Half does not break the tie, because
breaking it would be the guess this rule exists to forbid.

Pure and stdlib-only. No clock, no network, no model, no ambient state; nothing
here writes, and every writing function returns the fields of an append for its
caller to append (AD-3, AD-30).
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import Any, Final

from half.crisis import rows
from half.governance import ladder
from half.governance.ladder import License
from half.store.records import CONTACT, HANDLE, IS_CLINICIAN, REGION

#: How many doors are offered. Never one: a single name reads as an
#: instruction, and the companion is explicit that the closest person is
#: sometimes the wrong one. Never more than three either — a list is not a
#: choice, it is a search result, and this is not the moment for one.
OFFER_MIN: Final[int] = 2
OFFER_MAX: Final[int] = 3


@dataclass(frozen=True, slots=True)
class Contact:
    """One person in the main's phone book, as the handoff sees them."""

    id: str
    #: As the main gave it, in whatever script they gave it in. Never folded,
    #: never transliterated, never split into parts: a name is not a data
    #: structure, and a build that assumes it is gets a person's name wrong in
    #: the one message where being wrong is unforgivable.
    name: str
    #: The address a draft link is aimed at, or ``None`` for the share sheet.
    handle: str | None = None
    #: The main's own clinician — the highest-value door, because that is
    #: precisely the connection the documented failures missed.
    clinician: bool = False
    #: Whether the main has confirmed that Half holds this person.
    confirmed: bool = False


def _name(value: object) -> str | None:
    """``value`` as a name that may be rendered, or ``None``.

    One printable line, no separator, no control character, bounded — see
    ``half.crisis.rows.plain``. Dropped rather than repaired: a repaired name
    is a guess rendered in front of somebody in crisis.
    """
    return rows.plain(value, limit=rows.MAX_LABEL)


def offerable(record: Mapping[str, Any] | Any) -> bool:
    """Whether the ladder says this record may be named to the main.

    **The whole of the offerability question, asked once.** ``own_rung`` is
    `assert` only when the record is not quarantined, cites Half's own
    evidence, and is known to the main — three conditions the first version of
    this module collapsed into the third, which is how a quarantined
    ex-partner became a crisis door with a prefilled draft.

    Not ``permitted``: that applies the actor's ceiling, and crisis mode drops
    the ceiling to `behave`, so it would refuse every contact at exactly the
    moment the handoff exists for. See the module docstring for why the two
    questions are different.
    """
    return ladder.own_rung(record) is License.ASSERT


def contact_of(record: Mapping[str, Any] | Any) -> Contact | None:
    """``record`` as a ``Contact``, or ``None`` if it is not one.

    ``confirmed`` is the ladder's whole answer — ``offerable`` — and never one
    field of it. Everything else is read strictly: an uninterpretable handle is
    no handle, and an uninterpretable clinician flag is not a clinician,
    because both failures have to fall on the side of offering less rather than
    of offering somebody the main never named.
    """
    if not isinstance(record, Mapping):
        return None
    name = _name(record.get(CONTACT))
    if name is None:
        return None
    ident = _name(record.get("id")) or name
    return Contact(
        id=ident,
        name=name,
        handle=rows.plain(record.get(HANDLE), limit=rows.MAX_HANDLE),
        clinician=record.get(IS_CLINICIAN) is True,
        confirmed=offerable(record),
    )


def confirmed(records: Iterable[Mapping[str, Any]]) -> tuple[Contact, ...]:
    """The contacts in ``records`` the ladder says may be offered.

    Ordered rather than ranked. A clinician comes first because that is the
    door the documented failures missed, and the rest follow by id so that the
    same held list produces the same offer every time — which is what makes the
    reply to a crisis turn reproducible, and what keeps *"the main chooses"*
    from quietly becoming *"Half chose and called it an order"*.

    **Deduplicated by who they are, not by which record they came from.** One
    person held under two belief ids filled both person slots, so an offer of
    three doors was really an offer of two and the choice collapsed. The first
    record for a person wins, which means a clinician entry outranks a plain
    one for the same person.
    """
    found = [
        contact
        for record in records
        if (contact := contact_of(record)) is not None and contact.confirmed
    ]
    ordered = sorted(found, key=lambda c: (not c.clinician, c.id))
    seen: set[tuple[str, str | None]] = set()
    unique: list[Contact] = []
    for contact in ordered:
        key = (contact.name.casefold(), contact.handle)
        if key in seen:
            continue
        seen.add(key)
        unique.append(contact)
    return tuple(unique)


def region_of(records: Iterable[Mapping[str, Any]]) -> str | None:
    """Where the main has told Half they are, or ``None``.

    Gated on ``offerable`` for the reason a contact is: a retracted or
    quarantined place must not select a country's helplines any more than a
    pinned-out person may be named. It is the same rule, asked with the same
    function.

    ``None`` on no answer *and* on two different answers. A main who has told
    Half two places has told it nothing this module may act on, and picking one
    would be the inference the whole rule forbids — the honest generic line is
    the better failure.
    """
    told = {
        place.casefold()
        for record in records
        if offerable(record)
        and (place := rows.plain(record.get(REGION), limit=rows.MAX_KEY)) is not None
    }
    if len(told) != 1:
        return None
    return told.pop()


# -- writing: a contact is a belief, and takes the same path -----------------


def held(
    name: str, *, handle: str | None = None, clinician: bool = False, support: Any
) -> dict[str, Any]:
    """The fields of the append that *holds* ``name``, unconfirmed.

    Born at the weakest rung, like every belief, because both preconditions for
    anything stronger happen after the record exists: the evidence is cited and
    the main is told. A contact held this way is one Half knows about and may
    never offer.
    """
    if _name(name) is None:
        raise ValueError(
            "a contact needs a name that is one printable line, short enough "
            "to render, and free of the separators a row is built from"
        )
    fields: dict[str, Any] = {CONTACT: name.strip()}
    if handle is not None:
        fields[HANDLE] = handle
    if clinician:
        fields[IS_CLINICIAN] = True
    fields.update(ladder.admitted(support=support))
    return fields


def told(region: str, *, support: Any) -> dict[str, Any]:
    """The fields of the append that records where the main says they are.

    The write side of *told, never inferred*, and it exists so that half of
    that rule is not a rule with no path. Symmetric with ``held`` in every
    respect: born at the weakest rung, confirmed by the same event, read back
    by the same ``offerable``. There is deliberately no argument here for a
    prefix, a timezone or a language — a region arrives as an answer or it does
    not arrive.

    **Nothing in this build asks the question yet.** Where the main lives has
    no producer for the same reason the phone book has none: the question
    engine is story 11. This is what its answer is written with.
    """
    if rows.plain(region, limit=rows.MAX_KEY) is None:
        raise ValueError(
            "a region is one short printable line — what the main called the "
            "place, not a sentence and not a signal"
        )
    fields: dict[str, Any] = {REGION: region.strip()}
    fields.update(ladder.admitted(support=support))
    return fields


def confirm(record: Mapping[str, Any], *, answered: bool) -> dict[str, Any]:
    """The fields of the append that confirms ``record`` with the main.

    Delegated whole to the ladder, so that confirming a contact is the same
    event as promoting a belief the main has been told about, with the same
    refusals — ``answered`` must be ``True``, and a record citing nothing
    cannot be confirmed. Half's own inference never confirms anything, however
    warmly the main talks about somebody.

    One function for both kinds of record, because *confirmed* means one thing
    whether it is a person or a place.
    """
    return ladder.promote(record, to=License.ASSERT, acknowledged=answered)
