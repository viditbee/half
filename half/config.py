"""Which mains exist and how to reach them.

Credentials are read from the environment and never written into a store tree
(AD-11): the store is exportable and replayable, so a token inside it would be
handed to the main in an archive and resurrected on every replay.

A main's channel address is *registry* data, not belief data. It lives here so
that an address is never confused with something Half knows about a person.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from half.actor.registry import validate_main_id

#: ``HALF_MAINS`` maps addresses to main ids: "123456:vidit,789:asha".
MAINS_ENV = "HALF_MAINS"
ROOT_ENV = "HALF_ROOT"
TELEGRAM_TOKEN_ENV = "TELEGRAM_BOT_TOKEN"


@dataclass(frozen=True, slots=True)
class Config:
    root: Path
    #: platform address -> main_id
    mains: dict[str, str]

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
    return Config(root=root, mains=mains)
