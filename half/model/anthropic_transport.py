"""The concrete model transport — the only module here that touches a network.

Kept apart from ``anthropic.py`` on purpose, and the precedent is
``half/channel/telegram_transport.py``: the module above holds every rule that
matters (where the breakpoint lands, what the budget refuses, which of the four
a fault becomes, how a partial batch is reported) and is exercised offline
against a fake; this file is the thin edge that turns a rendered payload into
HTTP, and has no logic worth testing without a live key.

**Being a separate module is what makes the offline property assertable.** While
this lived at the bottom of ``anthropic.py``, the *"no SDK import"* scan could
cover the port, the tier table and the budget but not the implementation, so
hermeticity there rested on a lazy import plus one AST check. Now every module
in ``half/model`` except this one is provably SDK-free, and this one is
constructed by nobody unless a deployment asks for it.

**The key never comes from a store tree** (AD-11). It comes from a
``SecretStore``, which lives beside the main's directory rather than inside it,
so a key cannot reach an export or a replay. ``from_secrets`` is that path, and
it is a code path rather than a sentence in a docstring.

**No message from a provider crosses this boundary.** A provider's error text
can quote the request that caused it, so ``_translate`` carries the *class* of a
fault across and nothing else (AD-22).
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Mapping, Sequence
from typing import Any

from half.errors import (
    ModelBatchNotFound,
    ModelMisconfigured,
    ModelNotAuthorised,
    ModelRequestInvalid,
    ModelUnavailable,
)
from half.secrets import SecretStore

#: Where a main's model key lives in their ``SecretStore``. One name, here, so
#: that the consumer stories that will read it cannot each invent a different
#: one — which is the whole reason this constant is in the tree before its
#: first caller is.
MODEL_KEY = "model_api_key"


class SDKTransport:
    """``Transport`` over the official Anthropic SDK.

    **The SDK is imported inside ``__init__``, not at module scope**, so that
    importing this module builds no client, reads no key and touches nothing.

    ``max_retries`` covers connection faults, rate limits and server errors
    only — the SDK does not retry a 4xx — so no retry here can turn a refusal
    into a second spend, which the port forbids outright.
    """

    def __init__(
        self, api_key: str, *, base_url: str | None = None, max_retries: int = 2
    ) -> None:
        if not isinstance(api_key, str) or not api_key:
            raise ModelMisconfigured(
                "no model API key. Supply one from the SecretStore, which "
                "lives beside a main's directory and never inside it (AD-11). "
                "This is misconfiguration and deliberately not a refusal: "
                "nothing was asked of a provider and nothing declined"
            )
        try:
            from anthropic import AsyncAnthropic
        except ModuleNotFoundError as exc:  # pragma: no cover - packaging fault
            raise ModelMisconfigured(
                "the anthropic SDK is not installed; run `uv sync`"
            ) from exc
        self._client = AsyncAnthropic(
            api_key=api_key, base_url=base_url, max_retries=max_retries
        )

    @classmethod
    def from_secrets(
        cls, secrets: SecretStore, main_id: str, **kwargs: Any
    ) -> "SDKTransport":
        """Build from the store where a key is allowed to live (AD-11).

        The one sanctioned way to get a key into this port. A missing key is
        ``ModelMisconfigured`` rather than a refusal, for the reason
        ``__init__`` gives — and the store is asked for it per main, because
        that is how ``SecretStore`` is keyed and how a self-hoster's own key
        reaches their own actor.
        """
        key = secrets.get(main_id, MODEL_KEY)
        if not key:
            raise ModelMisconfigured(
                f"main {main_id!r} has no {MODEL_KEY} in the secret store"
            )
        return cls(key, **kwargs)

    async def message(self, payload: Mapping[str, Any]) -> Mapping[str, Any]:
        try:
            reply = await self._client.messages.create(**dict(payload))
        except Exception as exc:  # noqa: BLE001 - translated at the boundary
            raise _translate(exc) from None
        return reply.to_dict()

    async def batch_create(
        self, requests: Sequence[Mapping[str, Any]]
    ) -> Mapping[str, Any]:
        try:
            batch = await self._client.messages.batches.create(
                requests=[dict(request) for request in requests]
            )
        except Exception as exc:  # noqa: BLE001
            raise _translate(exc) from None
        return batch.to_dict()

    async def batch_status(self, batch_id: str) -> Mapping[str, Any]:
        try:
            batch = await self._client.messages.batches.retrieve(batch_id)
        except Exception as exc:  # noqa: BLE001
            raise _translate(exc, batch=True) from None
        return batch.to_dict()

    async def batch_results(self, batch_id: str) -> AsyncIterator[Mapping[str, Any]]:
        try:
            results = await self._client.messages.batches.results(batch_id)
            async for entry in results:
                yield entry.to_dict()
        except Exception as exc:  # noqa: BLE001
            raise _translate(exc, batch=True) from None


def _translate(exc: Exception, *, batch: bool = False) -> Exception:
    """A provider exception, as one of Half's own.

    The conventions forbid a provider type crossing the port boundary. The
    split is finer than it was, because review round 1 found the coarse version
    wrong in the expensive direction twice over:

    * A **rejected credential** used to arrive as a content refusal. The crisis
      caller fails toward *entering* on a content refusal and must not on a key
      that expired at three in the morning, and the two also differ on whether
      anything was billed.
    * A **broken request shape** used to become a transient outage. A wrong
      payload key raises a ``TypeError`` from the SDK, and the fallback mapped
      anything unrecognised to ``ModelUnavailable`` — so a permanently invalid
      request was retried for ever. It is now ``ModelRequestInvalid``, a build
      mistake, which the port raises rather than swallowing.

    **No message from the provider is carried across.** A provider's error text
    can quote the request that caused it (AD-22).
    """
    import anthropic

    if isinstance(exc, (anthropic.AuthenticationError, anthropic.PermissionDeniedError)):
        return ModelNotAuthorised("the provider rejected the credentials")
    if isinstance(exc, anthropic.NotFoundError):
        # On a batch route this is a batch that will never become ready; on a
        # message route it is a model this deployment cannot address, which is
        # configuration rather than weather.
        return (
            ModelBatchNotFound("the provider has no such batch")
            if batch
            else ModelRequestInvalid("the provider has no such model or route")
        )
    if isinstance(exc, anthropic.BadRequestError):
        return ModelRequestInvalid("the provider will not accept this request shape")
    if isinstance(exc, (anthropic.APIStatusError, anthropic.APIError)):
        return ModelUnavailable("the provider could not be reached")
    if isinstance(exc, (TypeError, ValueError, AttributeError)):
        # The SDK rejecting a payload key or a value's type. A fault in this
        # build, not in the network, and the one the old fallback hid.
        return ModelRequestInvalid("the request could not be built for the SDK")
    return ModelUnavailable("the model transport failed")
