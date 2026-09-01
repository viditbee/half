"""Which mains exist and how to reach them.

Credentials are read from the environment and never written into a store tree
(AD-11): the store is exportable and replayable, so a token inside it would be
handed to the main in an archive and resurrected on every replay.

A main's channel address is *registry* data, not belief data. It lives here so
that an address is never confused with something Half knows about a person.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from half.actor.registry import validate_main_id

#: ``HALF_MAINS`` maps addresses to main ids: "123456:vidit,789:asha".
MAINS_ENV = "HALF_MAINS"
ROOT_ENV = "HALF_ROOT"
TELEGRAM_TOKEN_ENV = "TELEGRAM_BOT_TOKEN"
#: ``HALF_MODEL_TIERS`` maps main ids to tiers: "vidit:cheap,asha:frontier".
#: A main's tier is registry data for the same reason their address is — it is
#: something an operator configures, never something Half believes about them
#: (AD-20). The *values* are parsed by ``half.model.tier``, which owns what a
#: tier is; this module owns only the shape of the string.
TIERS_ENV = "HALF_MODEL_TIERS"


def parse_pairs(raw: str, *, what: str, validate: bool = True) -> dict[str, str]:
    """``"a:b,c:d"`` to a mapping, refusing every ambiguous shape.

    **One parser, two callers.** ``half.model.tier`` had a copy of this that had
    lost ``validate_main_id`` and the duplicate-value check, so a tier table
    accepted main ids this module refuses — which is the drift a second copy
    always is. The key is a ``main_id`` in both callers, so it is validated
    here, once, before anything downstream can put it in a path.

    A malformed entry and a repeated key are errors rather than
    last-one-wins, because the quiet alternative is a main silently configured
    by whichever half of the string was parsed last.
    """
    out: dict[str, str] = {}
    for entry in filter(None, (e.strip() for e in raw.split(","))):
        key, _, value = entry.partition(":")
        key, value = key.strip(), value.strip()
        if not key or not value:
            raise ValueError(f"malformed {what} entry: {entry!r}")
        if key in out:
            raise ValueError(f"duplicate key in {what}: {key!r}")
        if validate:
            validate_main_id(key)
        out[key] = value
    return out


@dataclass(frozen=True, slots=True)
class Config:
    root: Path
    #: platform address -> main_id
    mains: dict[str, str]
    #: main_id -> tier name, unparsed. ``half.model.tier`` turns these into
    #: tiers and refuses a name this build does not know; a main absent from
    #: this mapping has no tier, which that module refuses rather than
    #: defaulting (AD-20).
    tiers: dict[str, str] = field(default_factory=dict)

    def tier_for(self, main_id: str) -> str | None:
        return self.tiers.get(main_id)

    def main_for(self, address: str) -> str | None:
        return self.mains.get(address)

    def address_for(self, main_id: str) -> str | None:
        for address, mid in self.mains.items():
            if mid == main_id:
                return address
        return None


def load(env: dict[str, str] | None = None) -> Config:
    """Build a Config from the environment.

    ``env`` is injectable so tests never touch the real process environment —
    and so nothing in the import path reads ambient state.
    """
    source = os.environ if env is None else env
    root = Path(source.get(ROOT_ENV, "~/.half")).expanduser()

    mains: dict[str, str] = {}
    raw = source.get(MAINS_ENV, "").strip()
    for entry in filter(None, (e.strip() for e in raw.split(","))):
        address, _, main_id = entry.partition(":")
        address, main_id = address.strip(), main_id.strip()
        if not address or not main_id:
            raise ValueError(f"malformed {MAINS_ENV} entry: {entry!r}")
        if address in mains:
            raise ValueError(f"duplicate address in {MAINS_ENV}: {address!r}")
        if main_id in mains.values():
            raise ValueError(f"duplicate main in {MAINS_ENV}: {main_id!r}")
        # A main_id becomes a directory name; validated before it can reach
        # the filesystem, since this is operator input.
        validate_main_id(main_id)
        mains[address] = main_id

    # Keyed by main_id rather than by address, so a main who changes platform
    # keeps their tier. Validated through the same parser, so a tier table
    # cannot name a main the rest of the config would refuse.
    tiers = parse_pairs(source.get(TIERS_ENV, "").strip(), what=TIERS_ENV)
    unknown = sorted(set(tiers) - set(mains.values()))
    if unknown:
        raise ValueError(
            f"{TIERS_ENV} assigns a tier to {unknown}, who are not mains in "
            f"{MAINS_ENV}. A tier for nobody is a typo, and the quiet version "
            f"of it is the real main still having no tier at all"
        )
    return Config(root=root, mains=mains, tiers=tiers)
