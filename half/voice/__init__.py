"""The voice: the morning, in words (CAP-8, AD-18, AD-19, AD-27).

Three modules, and the split is this story's three rules made structural:

``compose``
    The prompt. A ``Context`` and a language sample in, a ``Prompt`` out. The
    quotable channel and the shaping channel are **built by separate functions
    from separate fields**, and the language sample is a separate type again —
    so there is no branch anywhere that could re-admit a `behave` claim as
    something Half may say, and none that could turn the main's own last
    sentence into content. Pure: no store, no channel, no clock.

``gate``
    Generate, judge cheaply, regenerate a bounded number of times, and
    otherwise **say nothing**. Bounded, capped, breakered and counted the way
    ``half.crisis.classifier`` bounds its consultation.

``leak``
    The tripwire. AD-18 is enforced at construction (``half.context.build``);
    this is the smoke alarm on that rule, and it **fails the send loudly**. It
    has no redaction path, because a check that quietly cleans its output is how
    the construction guarantee decays for months while everything looks fine.

**The fallback is silence, never a template** (AD-27). A hand-written sentence
is the one thing this product cannot ship worldwide — ``half.context.channels``
already records the objection against a rendering rule, and it applies with more
force to the sentence itself. Sending nothing is already a first-class outcome
and story 10 already ships a morning that is quiet most days.

**Nothing here opens a store, holds a channel, or reads a clock.** Every module
is a function over values plus one narrow ``Generator`` per main;
``tests/test_unasked.py``'s package sweep covers this package with the model
root lifted and everything else — the store, the actor, the channel, the network
— still closed.

**No generated string is ever durable** (AD-22). What comes back is returned to
the caller and counted; the log records that a morning was sent, never what it
said, and no counter, log line or error message here has a field text could
travel in.
"""
