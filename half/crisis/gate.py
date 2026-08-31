"""The inbound entrypoint (AD-10).

Crisis owns the door and delegates inward. The normal pipeline is something
this module calls, and it has exactly one caller — enforced by
``tests/test_entrypoint.py``.

The inversion matters more than it looks. A crisis *check* that the pipeline
calls is an ordinary function call, and function calls get refactored around
at 2am by someone chasing an unrelated bug. Making crisis the entrypoint means
there is no route into the pipeline that skips it.

**The assessment is a stub until story 6.** Only the position is load-bearing
now. Building the inbound path without this shape would leave story 6
performing exactly the inversion AD-10 says gets skipped — which is why an
empty gate is worth its file.

Python cannot structurally forbid importing the pipeline directly. This is the
strongest available guarantee, not a proof, and the spine says so.
"""

from __future__ import annotations

from typing import Awaitable, Callable

from half.channel.port import Inbound
from half.retrieval.rank import RetrievalSwitch

#: What the gate delegates to once a turn is judged ordinary.
Pipeline = Callable[[Inbound], Awaitable[str | None]]

#: Resolves one main's retrieval switch. A function rather than a switch,
#: because crisis is a state of one person and not of the worker process.
SwitchFor = Callable[[str], RetrievalSwitch]


class CrisisGate:
    """Every inbound message crosses this before anything else sees it."""

    def __init__(self, pipeline: Pipeline, retrieval: SwitchFor | None = None) -> None:
        self._pipeline = pipeline
        # CAP-12 requires ledger retrieval to be hard-disabled in crisis mode,
        # and the gate is the only place that knows the mode has been entered.
        # It is resolved per main: the runtime passes the actor registry's
        # resolver, so the switch this turns off is the one that main's own
        # retriever reads. A gate built without one keeps its own per-main
        # switches rather than a single shared flag, so even the standalone
        # case cannot silence a bystander.
        self._own: dict[str, RetrievalSwitch] = {}
        self._retrieval = retrieval if retrieval is not None else self._mine

    def _mine(self, main_id: str) -> RetrievalSwitch:
        return self._own.setdefault(main_id, RetrievalSwitch())

    async def handle(self, inbound: Inbound) -> str | None:
        """Assess, then either respond directly or delegate inward.

        Returns the reply text, or ``None`` for silence — which is a first-class
        outcome, not a failure (AD-27).
        """
        if self._is_crisis(inbound):
            # Disabled here rather than inside the response, so it stays on the
            # path even when story 6 rewrites the response entirely. A disabled
            # retriever raises when queried; it never returns an empty set that
            # a caller could mistake for "this main has nothing" (CAP-12).
            self._retrieval(inbound.main_id).disable()
            return await self._respond_to_crisis(inbound)
        return await self._pipeline(inbound)

    # -- story 6 fills these in ---------------------------------------------

    def _is_crisis(self, inbound: Inbound) -> bool:
        """Always False until story 6.

        Deliberately not a keyword scan: a partial implementation here would
        read as coverage and discourage building the real thing, and the
        crisis-protocol companion specifies detection precisely. An honest
        stub is safer than a plausible one.
        """
        return False

    async def _respond_to_crisis(self, inbound: Inbound) -> str | None:
        """Unimplemented on purpose until story 6.

        Deliberately raising rather than returning a placeholder: a plausible
        response here would read as coverage and discourage building the real
        one, which the crisis-protocol companion specifies precisely. The
        runtime isolates the failure to this message, so an unimplemented
        branch cannot stop the worker.
        """
        raise NotImplementedError(
            "crisis response is story 6; implement it from the crisis-protocol "
            "companion verbatim, never paraphrased"
        )
