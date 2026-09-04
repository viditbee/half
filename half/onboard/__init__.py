"""Onboarding: the first thing Half ever says (CAP-2, story 7).

Two modules, and the order between them is the story:

* ``half.onboard.consent`` — what the main is told, and **when**. The notice
  that their messages leave the machine is delivered before a source is
  connected, and a deployment that has no wording for it connects nothing.
* ``half.onboard.flow`` — the demonstration: connect, ingest, derive, offer
  exactly one claim for confirmation, and route the main's answer.

**Nothing here promotes anything and nothing here corrects anything.** A
confirmation becomes ``half.governance.ladder.promote(..., acknowledged=True)``
and a denial becomes ``half.correction.apply.plan``; this package builds the
arguments and the caller appends, which is the rule every writing module in
this tree already follows (AD-3, AD-30).
"""
