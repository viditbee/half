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

#: What the gate delegates to once a turn is judged ordinary.
Pipeline = Callable[[Inbound], Awaitable[str | None]]


class CrisisGate:
    """Every inbound message crosses this before anything else sees it."""

    def __init__(self, pipeline: Pipeline) -> None:
        self._pipeline = pipeline

    async def handle(self, inbound: Inbound) -> str | None:
        """Assess, then either respond directly or delegate inward.

        Returns the reply text, or ``None`` for silence — which is a first-class
        outcome, not a failure (AD-27).
        """
        if self._is_crisis(inbound):
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
