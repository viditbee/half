"""The crisis-line directory: data, versioned, and refreshable (CAP-12).

Build requirement 5 of the companion is one sentence — *the referral directory
is data, versioned and refreshable without a release* — and every clause of it
is load-bearing:

*Data.* A curated set of crisis lines is a maintainable dataset; the thing
that is **not** maintainable, and is a spec non-goal outright, is a live global
directory of available clinicians. That distinction is why this module reads a
file and nothing more: no lookup, no query, no network, and no notion of who is
free right now.

*Versioned.* Whatever version was used is carried on the offer that used it, so
the question a reviewer will ask — *which set of lines was this person handed?*
— is answerable after the fact. The version is a string in the file, not a
hash of it: an operator who corrects a number wants to say so.

*Reviewed, or it names nothing.* The file carries its own review state, and
``reviewed`` defaults to false. An unreviewed directory parses, reports its
version, and offers **no lines at all** — because a helpline number that is
right in shape and wrong in fact is the most dangerous artefact this repository
can produce, and the alternative is a set of numbers written from memory
shipping silently as the default. The companion's build requirement 6 is a
qualified reviewer before launch, and it covers this file as much as the code
that reads it.

*Refreshable without a release.* The file is read at the moment an offer is
assembled, so replacing it takes effect on the next crisis turn — no restart,
no deploy, no code change. It is deliberately not cached: a cache is a window
in which a number somebody just corrected is still being handed out, and the
cost is one small read on a path that happens rarely and matters enormously.

**It degrades, and degrading is the whole design.** Missing, unreadable,
malformed, too large, wrong shape, half wrong — every one of them produces a
directory with no entries rather than an exception, because the alternative is
a main in crisis receiving nothing while a traceback is written to a log
nobody is reading. With no entries, no line is named and 6a's generic
wording stands, unchanged and still true: *"a crisis line where you live can
stay with you too."* Silence is never the fallback and a guess never is either.

**Bad rows are dropped, not tolerated.** A region whose payload is not a list,
an entry missing a name or something to dial, an entry that is not an object:
each is dropped on its own, so one malformed row costs one row rather than a
continent. What is *not* tolerated is a broken root or a missing version —
those mean this file is not the thing this module was asked to read, and
guessing at its shape is how a number ends up beside the wrong country.

**Nothing here decides where the main is.** ``listings_for`` takes a region it
is given; the region comes from a record the main confirmed
(``half.crisis.contacts``), never from a prefix, an address, a clock or a
language. This module cannot infer one — it has no signal to infer from.

Pure of everything but the read: no clock, no network, no model, no process
environment. The path is a constructor argument or the packaged default, never
an environment variable, so two runs of the same code over the same file agree.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Final, Mapping

from half.crisis import rows

logger = logging.getLogger(__name__)

#: What a directory reports when it could not be read. Recorded on the offer
#: like any other version, because *"we could not read the file"* is an answer
#: to the reviewer's question and a blank is not.
UNKNOWN_VERSION: Final[str] = "unavailable"

#: The file, relative to whatever directory holds a ``data`` folder above this
#: module. Resolved by walking up rather than by a fixed number of parents, so
#: the same code finds it in the repository and inside an installed wheel,
#: where the packaging puts it at ``half/data/``.
DATA_DIR: Final[str] = "data"
FILE_NAME: Final[str] = "crisis-lines.json"

#: How far up the walk goes. Bounded, because an unbounded one climbs to the
#: filesystem root and will happily adopt a stranger's
#: ``data/crisis-lines.json`` from any ancestor directory — a home directory, a
#: shared volume, ``/``. Three levels covers both real layouts and nothing
#: else: ``half/crisis`` -> ``half`` -> the project root in a source tree, and
#: ``half/crisis`` -> ``half`` inside an installed package.
SEARCH_DEPTH: Final[int] = 3

#: A ceiling on what will be read, so a file that is enormous by accident or on
#: purpose costs a degraded offer rather than a stalled crisis turn. Enforced
#: on the bytes actually read rather than on a prior ``stat``: a file that grew
#: between the two walked straight past the check.
MAX_BYTES: Final[int] = 1 << 20

_VERSION_KEY: Final[str] = "version"
_REVIEWED_KEY: Final[str] = "reviewed"
_ENTRIES_KEY: Final[str] = "regions"
_ALIASES_KEY: Final[str] = "aliases"
_ID_KEY: Final[str] = "id"
_NAME_KEY: Final[str] = "name"
_REACH_KEY: Final[str] = "reach"
_NOTE_KEY: Final[str] = "note"


@dataclass(frozen=True, slots=True)
class Listing:
    """One crisis line, exactly as the file states it.

    ``reach`` is whatever the main does to get there — a short code, a number,
    an instruction to text a word somewhere. It is a single opaque string on
    purpose: the shapes differ by country and by service, and a schema that
    modelled them would be a schema that dropped the ones it had not met.
    """

    id: str
    name: str
    reach: str
    note: str | None = None


@dataclass(frozen=True, slots=True)
class Directory:
    """A loaded directory, or the empty one that stands in for a broken file."""

    version: str = UNKNOWN_VERSION
    entries: Mapping[str, tuple[Listing, ...]] = field(default_factory=dict)
    #: Other names for a region key, so that what a person calls where they
    #: live reaches the table. Data, not code: the vocabulary of place names is
    #: endless and belongs beside the places.
    aliases: Mapping[str, str] = field(default_factory=dict)
    #: Whether a qualified reviewer has signed this file off (companion build
    #: requirement 6). **False is the default and false offers nothing.** The
    #: shipped file was written from memory, and a helpline number that is
    #: right in shape and wrong in fact is the worst artefact in this
    #: repository — so an unreviewed directory degrades to the generic line
    #: rather than shipping silently as the default. Flipping this is a
    #: deliberate, signed-off act.
    reviewed: bool = False

    def key_for(self, region: str | None) -> str | None:
        """``region`` as a table key, following an alias, or ``None``.

        Separate from the lookup so a caller can tell *"nothing was told"* from
        *"something was told and this file has nothing for it"* — which are the
        same absence of lines and very different things to say to a person.
        """
        if not isinstance(region, str):
            return None
        key = region.strip().casefold()
        if not key:
            return None
        return self.aliases.get(key, key)

    def listings_for(self, region: str | None) -> tuple[Listing, ...]:
        """The lines held for ``region``, or none.

        ``None``, unknown, unreviewed and unreadable are one answer — no lines
        — because naming a line on the wrong continent is worse than naming
        none, and naming one nobody has checked is worse than both.
        """
        if not self.reviewed:
            return ()
        key = self.key_for(region)
        return self.entries.get(key, ()) if key is not None else ()

    @property
    def usable(self) -> bool:
        return self.reviewed and bool(self.entries)


#: What a caller gets for a file that is missing, unreadable or not a
#: directory. Never ``None``: a caller that has to check for one is a caller
#: that can forget to, on the path where forgetting is a main in crisis
#: receiving an exception instead of a reply.
EMPTY: Final[Directory] = Directory()


def search_from(module: Path) -> Path:
    """Where a directory beside ``module`` would live.

    Found by walking up a **bounded** number of levels until a
    ``data/crisis-lines.json`` appears — the repository has it at the project
    root, an installed wheel has it inside the package, and the same search
    finds both. A fixed ``parents[n]`` would work in exactly one of the two and
    fail silently in the other, which for this file means every deployment
    quietly losing the whole directory while every test passes.

    Bounded, because an unbounded walk climbs to the filesystem root: it would
    adopt any ancestor's ``data/crisis-lines.json`` — a home directory, a
    shared volume — and hand a main whatever a stranger put there.

    Taken as an argument rather than read from ``__file__`` so the installed
    layout is *tested* rather than assumed: the packaging that puts the file
    inside the wheel is a line in ``pyproject.toml``, and deleting it is a
    silent, total loss of this feature.
    """
    here = module.resolve()
    for parent in here.parents[:SEARCH_DEPTH]:
        candidate = parent / DATA_DIR / FILE_NAME
        if candidate.is_file():
            return candidate
    # Nothing found: name the place it was looked for, so the log line says
    # something actionable rather than "not found".
    depth = min(SEARCH_DEPTH - 1, len(here.parents) - 1)
    return here.parents[depth] / DATA_DIR / FILE_NAME


def default_path() -> Path:
    """Where the packaged directory lives."""
    return search_from(Path(__file__))


def load(path: Path | str | None = None) -> Directory:
    """The directory at ``path``, or ``EMPTY``. Never raises.

    Broad by intention, and the intention is the same one the crisis gate's
    broad ``except`` has: on this path the set of exceptions worth losing a
    main's reply over is empty. A permission error, a partial write, a
    directory where a file belongs, a file that is UTF-16, a JSON document that
    is a list — all of them are *no lines*, logged without content, and the
    turn continues.
    """
    target = Path(path) if path is not None else default_path()
    try:
        if not target.is_file():
            logger.warning("crisis directory missing at %s; the generic line "
                           "stands", target)
            return EMPTY
        # Read a bounded prefix and then check, rather than ``stat`` and then
        # read: a file that grew between the two walked straight past a check
        # made against its old size. One byte over the ceiling is enough to
        # know, and the read never exceeds it.
        with target.open("rb") as handle:
            blob = handle.read(MAX_BYTES + 1)
        if len(blob) > MAX_BYTES:
            logger.warning("crisis directory at %s is larger than this build "
                           "will read; the generic line stands", target)
            return EMPTY
        # ``utf-8-sig`` because an editor that writes a byte-order mark would
        # otherwise cost the whole file: the BOM lands in front of the opening
        # brace and JSON refuses it. Plain UTF-8 decodes identically.
        raw = blob.decode("utf-8-sig")
    except Exception as exc:
        # The class and the path, never the exception's own text: a parse
        # failure quotes the document it failed on (story 6d, AD-22).
        logger.warning("crisis directory at %s could not be read (%s); the "
                       "generic line stands", target, type(exc).__name__)
        return EMPTY
    return parse(raw, origin=str(target))


def parse(raw: str, *, origin: str = "<memory>") -> Directory:
    """``raw`` as a directory, or ``EMPTY``. Never raises.

    Split from ``load`` so the validation is testable without a filesystem, and
    so a caller holding the bytes already does not have to write them down to
    have them checked.
    """
    try:
        document = json.loads(raw)
    except Exception:
        logger.warning("crisis directory at %s is not readable JSON; the "
                       "generic line stands", origin)
        return EMPTY

    if not isinstance(document, dict):
        logger.warning("crisis directory at %s is not an object; the generic "
                       "line stands", origin)
        return EMPTY

    version = document.get(_VERSION_KEY)
    if not isinstance(version, str) or not version.strip():
        logger.warning("crisis directory at %s states no version; refusing to "
                       "hand out lines this build cannot name", origin)
        return EMPTY

    payload = document.get(_ENTRIES_KEY)
    if not isinstance(payload, dict):
        logger.warning("crisis directory at %s holds no region table; the "
                       "generic line stands", origin)
        return EMPTY

    entries: dict[str, tuple[Listing, ...]] = {}
    for key, listed in payload.items():
        place = rows.plain(key, limit=rows.MAX_KEY)
        if place is None or not isinstance(listed, list):
            logger.warning("crisis directory at %s has an unreadable region "
                           "row; dropping it", origin)
            continue
        listings = _listings(listed, origin=origin)
        if listings:
            entries[place.casefold()] = listings

    if not entries:
        logger.warning("crisis directory at %s parsed to no usable lines; the "
                       "generic line stands", origin)
        return EMPTY

    # Signed off, or not. Read strictly for the reason ``known_to_main`` is:
    # this field grants a permission — to put an unverified phone number in
    # front of somebody in crisis — so anything that is not an explicit
    # ``True`` is not a review. The version and the entries are still carried,
    # so a caller can say *which* unreviewed file it declined to use.
    reviewed = document.get(_REVIEWED_KEY) is True
    if not reviewed:
        logger.warning(
            "crisis directory at %s is not marked reviewed; no line will be "
            "named and the generic wording stands. A qualified reviewer signs "
            "this file off before it names anything to anyone (companion "
            "build requirement 6)", origin,
        )
    return Directory(
        version=version.strip(),
        entries=entries,
        aliases=_aliases(document.get(_ALIASES_KEY), entries, origin=origin),
        reviewed=reviewed,
    )


def _aliases(
    payload: object, entries: Mapping[str, tuple[Listing, ...]], *, origin: str
) -> dict[str, str]:
    """The alias table, keeping only aliases that reach a region that exists.

    Data rather than code, because the vocabulary of place names has no end —
    *uk*, *england*, *united kingdom*, *usa*, *states* — and a build that
    hard-codes a handful gets the sixth one wrong. An alias pointing at a
    region this file does not hold is dropped rather than kept: it would turn
    *"I have nothing listed for there"* into *"I have nothing listed for
    there"* by a longer route, and hide a typo in the file while doing it.
    """
    if not isinstance(payload, dict):
        return {}
    found: dict[str, str] = {}
    for name, target in payload.items():
        alias = rows.plain(name, limit=rows.MAX_KEY)
        place = rows.plain(target, limit=rows.MAX_KEY)
        if alias is None or place is None:
            continue
        alias, place = alias.casefold(), place.casefold()
        if place not in entries or alias in entries:
            logger.warning("crisis directory at %s has an alias that names no "
                           "region it holds; dropping it", origin)
            continue
        found[alias] = place
    return found


def _listings(listed: list[Any], *, origin: str) -> tuple[Listing, ...]:
    """The valid entries of one region, in file order, ids unique.

    File order is kept rather than sorted: the order in the file is the
    curator's judgement about which line to put in front of somebody, and this
    module has no better one — and reordering would make an offer depend on a
    property of a string rather than on a decision a person made.
    """
    found: list[Listing] = []
    seen: set[str] = set()
    for entry in listed:
        if not isinstance(entry, dict):
            continue
        ident = _string(entry.get(_ID_KEY), limit=rows.MAX_KEY)
        name = _string(entry.get(_NAME_KEY), limit=rows.MAX_LABEL)
        reach = _string(entry.get(_REACH_KEY), limit=rows.MAX_REACH)
        if ident is None or name is None or reach is None:
            logger.warning("crisis directory at %s has an entry this build "
                           "will not render; dropping it", origin)
            continue
        if ident in seen:
            continue
        seen.add(ident)
        found.append(Listing(
            id=ident, name=name, reach=reach,
            note=_string(entry.get(_NOTE_KEY), limit=rows.MAX_NOTE),
        ))
    return tuple(found)


def _string(value: object, *, limit: int) -> str | None:
    """``value`` as a string this build will put in front of a main, or ``None``.

    Never coerced: a number where a name belongs is a row this build does not
    understand, and a stringified ``None`` beside a place is worse than one
    fewer line. And never *raw*: a directory is a file an operator edits, so a
    name carrying a newline, a control character or one of the separators a row
    is joined from would become its own line inside a crisis reply — the same
    hole a contact's name had. ``rows.plain`` is the one definition of what may
    be rendered, and a value that fails it costs its entry, not the region.
    """
    return rows.plain(value, limit=limit)
