"""Context construction: where licenses are enforced (AD-18, CAP-10).

A layer *above* retrieval. `half.retrieval` answers *which beliefs matter to
this main right now* and knows nothing about what Half may say; this package
answers *which of them Half may state, act on, or ask about*, and it is the
only place that answer is computed.

Three rules hold it together:

**Enforcement is construction, never filtering.** Material a rung does not
permit is never assembled into a quotable field, so there is no generated text
to inspect afterwards. A post-generation filter is AD-18 inverted: paying for
the tokens and then trusting a classifier to suppress them.

**The weakest rung is the default and the failure mode.** Every uncertainty
resolves downward — including a directive whose topic echoes its claim, which
is dropped rather than degraded.

**The rung rules belong to the ladder, and the ceiling is applied here.**
``half.governance.ladder`` decides what a rung requires and is the one account
of it; ``resolve`` is the single place that answer becomes a decision, which is
why the actor's global ceiling is applied inside it and nowhere else (AD-28).

**No model, no clock, no network (AD-19, AD-30).** A context is a data
structure this package builds and asserts over, not something sent anywhere.
``now`` is injected, so the same ranked set builds the same bytes twice.
"""

from half.context.build import build, resolve
from half.context.channels import (
    Content,
    Context,
    Directive,
    Item,
    License,
    Question,
    Topic,
    render_line,
    sanitize,
)

__all__ = [
    "Content",
    "Context",
    "Directive",
    "Item",
    "License",
    "Question",
    "Topic",
    "build",
    "render_line",
    "resolve",
    "sanitize",
]
