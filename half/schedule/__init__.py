"""The due-time scheduler: the one thing in Half that knows what time it is
(AD-9, AD-30).

Nothing else in the product runs on a schedule. Ingestion was constructed and
never run, aftercare waited for the main to speak first, and the nightly pass,
the morning surface and the nagging bound were all defined against times no
code could reach. This package is what reaches them.

Three modules, and the split is the whole point:

* ``clock`` — **the one clock reader.** It reads once per tick and hands the
  instant downward, so that everything beneath it stays a pure function of what
  it was given (AD-30). Every other module in this package, and every module
  the tick calls, takes an injected ``now``.
* ``due`` — ``next_pass_at``: local pre-dawn with jitter, from a zone the main
  *told* Half, and a defined, recorded fallback when they have not. Pure, given
  an instant and a zone.
* ``tick`` — the file-locked drain: what is due runs under bounded concurrency,
  one main's failure cannot touch another's, and a window that was missed sends
  nothing at all.

**A due-time queue, never a global cron.** Timezone spread does not save a user
base that shares one timezone, so the herd is prevented by per-main due times
and per-main jitter rather than by hoping.

**This package deliberately re-exports nothing**, following ``half.loops`` and
for the same reason: ``half.channel.telegram`` imports ``half.schedule.clock``
so that the adapter's wall-clock boundary is the *one* clock reader rather than
a second one, and an ``__init__`` that pulled in ``tick`` — which reaches
``half.actor``, which reaches ``half.crisis`` — would close a cycle through a
module that needs nothing but ``time``. Every consumer names the module it
wants.
"""
