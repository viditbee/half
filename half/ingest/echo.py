"""Whether one body is an echo of another (CAP-3).

Forward an email to yourself and Half counted it twice. The content axis of the
same-moment union-find is a *digest* — byte equality — and a forward is never
byte-identical: it wraps the original in ``FYI`` and a separator. So the
original and its forward shared no thread, no digest and no sender, and CAP-3's
admission floor of two independent supports was crossed by **one** message that
travelled. That is the precise failure CAP-3 exists to prevent, reached by the
most ordinary thing a person does with mail.

**The rule is containment, not similarity, and containment here is total.** One
body is an echo of another when the smaller one's whole term sequence appears
**contiguously** inside the larger one's. A forward wraps its original and
changes nothing inside it, so the original is in there, in order, untouched;
that is what makes this structural rather than a judgement about how alike two
messages are. There is no threshold to tune, because there is no fraction to
compare against one.

**A fractional floor was the first rule and the sweep rejected it.** The
measurement is kept in ``overlap`` and in ``tools/percolation_sim.py`` rather
than described, because it is the whole reason this module is shaped the way it
is. Scored as *the fraction of the smaller body's vocabulary that appears in the
larger*, every true positive sits at exactly 1.00 and the confound table spreads
from 0.38 to 0.93 — a forward against a quoted reply in any of nine scripts at
1.00, airline against hotel at 0.38, two receipts on one template at 0.89, two
one-line notes under one long legal footer at 0.93. A floor of 0.98 looks like
five points of air. It is not: a mailbox where every message carries the same
long legal footer — which is every corporate mailbox — drives that score over
0.98 on *unrelated* pairs (two one-line notes under this footer measure above
it, which is a case), and 500 such messages declare **three** handles between
them and come to **one** voice through the two levels. That is the outage story
17 measured for the sender axis, reached through a different door: the gate
never opens, Half finds one support everywhere, admits nothing, and goes quiet,
which looks exactly like a well-behaved product with nothing to say.

Total *set* containment — the same fraction with the floor at 1.00 — is better
and still not enough, because two notes whose words happen to be a subset of
each other's still collapse. It is the ``set`` column of the same sweep rather
than a remembered figure — this paragraph used to cite a number nothing in the
tree computed. What the sweep prints: **475 of 500** unrelated messages under
one footer against the window ``Run.hold`` bounds, **957 of 1000** at the
largest row, and **269 of 300** with every pair compared. The sequence is what
closes it: every message its own voice, at every density swept, bounded and
unbounded.

**Why this may be a union-find axis when the sender could not, and where the
argument stops.** Story 17 measured the sender axis percolating a mailbox into
one group, because union-find is transitive *across* axes and "shares a sender"
chaining through "shares a thread" links strangers. Containment chains only with
itself, and the *chain* shape is genuinely safe: if A is inside B and B is inside
C, A really is inside C, and all three are one derivation. That much is measured
in ``test_a_chain_of_forwards_is_one_voice_in_any_order``.

**That is not a safety proof, because the chain is not the only shape this axis
can take, and the other one was a defect.** The shape that breaks is a *fan*: A
inside B **and** A inside C, where B and C share nothing but A. Both adopt A's
handle, so B and C are one voice although neither contains the other — and A is
any block a mailbox repeats. It only needs that block to arrive as a message of
its own, which a legal footer, a policy notice or a signature routinely does.
Measured through the shipped path (``Run.declares`` → ``declaring``), against a
truth of one voice per message, story 18 shipped:

* a disclaimer arriving as its own message between two unrelated notes that
  carry it — three messages, **one** voice;
* thirty unrelated notes under one footer, with a footer-only message arriving
  first — thirty-one messages, **one** voice; the same footer arriving sixth —
  **five**;
* an eight-term line, *"Please consider the environment before printing this
  email"*, standing alone in front of six notes that carry it — seven messages,
  **one** voice; mid-stream — **three**.

**Story 19 closes it by asking who carries the block rather than what it looks
like.** A legal footer is stapled by one organisation to its own outgoing mail.
A forwarded original travels between different senders — that is what forwarding
*is*. So a block confined to a single organisation is that organisation's
furniture and must not make two messages one voice; a block that crosses
organisations is the thing being passed on and must. ``travelled`` is that
question, ``carrying`` gathers the origins it is asked about, and ``declaring``
consults it **after** containment has already answered yes: story 18's rule
decides *whether* two bodies could be one voice and this decides whether the
block that makes them so is evidence or furniture.

**Six candidate rules are dead ends and are recorded so nobody re-derives
them.** Four were measured for story 18 and two for story 19. (1) A bound on the
terms or the size a body adds — a forward-plus-footer adds 59 terms at 5.2x, an
attractor adds 61 at 8.6x; a plain forward adds 2, an attractor adds 7, and the
ranges overlap in both directions. (2) Raising ``MIN_TERMS`` — attractors
measured at 8, 8, 9 and 10 distinct terms, realistic short transactional
originals at 7, 8, 9, 9, 10 and 11, fully overlapping, and the value that blocks
every attractor, eleven, loses five of six real forwards. (3) A frequency
discount on a block seen often, globally or in a window — it inverts on a viral
forward: at eight copies of one notice the forwarded body itself looks like
boilerplate, the defence switches off, and nine copies become nine supports.
(4) Refusing a held body contained in two or more held bodies that do not
contain each other — the viral forward has exactly that shape under different
wrappers and inverts the same way. (5) **The pairwise remainder**, how much of a
body survives removing the block: a footer standing alone and an original
standing alone both leave nothing, so *pairwise there is no difference between
them* and no pairwise rule can ever work. (6) **The remainder across carriers**
— a forward's own wrapper is boilerplate too, contributing thirteen distinct
terms per carrier, so forwards look exactly like strangers.

Only origin-crossing separates them, because it is the one signal that is not in
the text. That is also why the fix is not in ``half/ingest/scrub.py``, where
story 18's deferred entry put it: ``scrub(text: str)`` sees one message with no
context, and boilerplate is not a property of one message — a footer is a footer
because it *recurs*, which one body cannot show.

**The origin is read here and never unioned on.** Story 17 measured a mailbox
collapsing when the sender became a fourth union-find axis, and this module does
not touch ``SAME_MOMENT_FIELDS``, ``ORIGIN_AXIS`` or the two-level structure —
it reads an origin to classify *a block*, and what it returns is still a key.
``half.ingest.independence`` remains the only place an origin is compared for
identity, and ``organisation`` reuses its ``_normalize`` rather than inventing a
second idea of what two spellings of one address are.

**The limit this leaves, stated up front rather than buried.** A forward that
never leaves one organisation looks exactly like that organisation's furniture,
because on the only signal that works it *is* the same shape. Half counts it as
two supports. That is the **over-claiming** direction — the one story 18 closed
— so it is the more serious residue of the two, and it is pinned by
``test_a_forward_inside_one_company_is_not_caught`` with its direction named.

**Which is why every branch that cannot decide falls back to story 18's answer
rather than to "independent".** Story 18 could say its failures should merge,
because Half saying less is the conservative failure. That is no longer
automatically true, since this rule can also cause a *split*, and a split admits
claims. So an origin that cannot be read, and a block with nothing to classify
from, both merge.

**Latin is not the case, and the tokenizer decides whether that is true.** The
comparison splits with ``half.text.terms`` — story 4c's script-aware tokenizer —
and **not** with ``half.context.build.runs``. Measured twice, independently:
``runs`` is whitespace-based, so on Thai a forward that contains its original
verbatim scores **zero** and the rule silently does nothing for that script.
``terms`` catches every forward and every quoted reply in Latin, Japanese,
Chinese, Thai, Devanagari, Arabic, Hebrew, Korean and Amharic — the last of
those because a review found it in the reader's script table and not in this
rule's, so Ge'ez had been read end to end and never once asked whether a forward
of it contains its original. The tokenizer is injectable for exactly one reason:
so a case can run the whole worldwide suite against ``runs`` and watch it fail,
which pins the choice by a test rather than by this paragraph.

**The key is the arriving body's own handle unless a travelling held body claims
it.** A
declaration has to be a value *both* sources carry, and the original cannot know
it is about to be forwarded — so every body long enough to compare declares a
digest of its own term sequence, and a body that contains, or is contained by,
one already in hand adopts *that* body's declaration instead. Both directions are
covered by the arriving source adopting, so the original arriving after its
forward collapses exactly as the forward arriving after its original does, and a
chain stays one key however it is ordered.

**Nothing here stores a body.** What leaves is a one-way digest and never a
text, a sketch or a shingle set (AD-13, AD-22). The comparison happens where the
body already exists — ``Run.hold`` — and the bodies stay there.

**The rule declines rather than guessing.** A body below ``MIN_TERMS`` distinct
terms declares nothing, so an empty body never matches another empty body and
*"thanks"* inside *"thanks, noted"* is not corroboration. A body past the
tokenizer's own growth ceilings also declines: refusing to compare costs one
collapse, where letting ``TokenGrowthLimitError`` out would cost the run every
receipt behind it.

**That ceiling is asymmetric, and it lands on the shape this module exists for.**
A forward is by construction *longer* than what it forwards, so the realistic
case is not both bodies being oversized — it is the original fitting under
``half.text.MAX_INPUT_CHARS`` while its forward does not. The rule then declines
on the forward alone and story 18's defect comes back for that pair, silently.
The ceiling is also **script-dependent**, which matters because Half ships
worldwide: ``terms`` emits one grapheme cluster per character for a
scriptio-continua script, so an unbroken Japanese, Chinese or Thai body reaches
``MAX_TERMS`` at 6,001 characters — three quarters of the 8,000 a Latin body
gets — and a realistically punctuated Japanese one at about 6,660. Both are
cases rather than sentences, and both are recorded as residue.

Pure and stdlib-plus-``half`` only. Nothing here reads a clock, the network or
the log, so a fold that reaches it stays pure (AD-30).
"""

from __future__ import annotations

import hashlib
from collections.abc import Callable, Iterable, Sequence
from typing import Final

from half.errors import TokenGrowthLimitError
from half.ingest.independence import _normalize, an_identity
from half.text import terms

#: The shortest body this rule will look at, counted in **distinct** terms.
#:
#: Below it the rule declines and the body declares nothing. Two reasons, and
#: both are cases: an empty body would otherwise sit inside every other empty
#: body at a vacuous total containment, and *"see you there"* inside *"see you
#: there tomorrow at nine"* is total containment of a body that is evidence of
#: nothing. A term is a word in a spaced script and a grapheme cluster in a
#: scriptio-continua one, which is the same tokenizer both sides use.
MIN_TERMS: Final[int] = 6

#: What a declaration is prefixed with, so a key from this rule is recognisable
#: as one wherever it is read. Namespacing inside the value costs nothing and
#: makes a stray key in a fixture legible.
PREFIX: Final[str] = "echo:"

#: Separates terms in the joined form ``an_echo`` searches, and **must not be a
#: character a term can contain**. A term comes out of ``half.text.terms``, which
#: emits only letters, digits and the marks attached to them, so a NUL can never
#: appear inside one. It is the sentinel that makes the search a search over
#: whole terms: without it, ``rat`` would be found inside ``gratis``.
JOIN: Final[str] = "\x00"

#: What separates a local part from the organisation that carries it. The whole
#: of the parsing this module does to an origin, and it is one character.
AT: Final[str] = "@"

#: How a body is cut into the units that are compared. ``half.text.terms`` in
#: production and never anything else; a parameter only so a case can run the
#: same suite against ``half.context.build.runs`` and watch the unspaced scripts
#: go to zero.
Split = Callable[[str], Sequence[str]]

#: One held body, as ``declaring`` is handed it: what that body declared, the
#: body itself, and **the origin that carried it**. The third field is story
#: 19's whole addition to the window's shape — the classification asks who
#: carries a block, and a window of texts alone cannot answer it.
#:
#: A triple rather than a pair with a default, deliberately: a caller that
#: forgets the origin is a ``ValueError`` at unpacking, where an optional third
#: field would silently classify every block as one organisation's furniture and
#: quietly hand story 18's defect back as a split.
Window = tuple[str, object, object]

#: A held body after ``declaring`` has cut it: its declaration, its units and
#: its origin. Built once per arrival and handed to ``carrying``, so a window of
#: eight costs eight tokenizations however many blocks are classified against it.
Cut = tuple[str, tuple[str, ...], object]

#: How a block's carriers are classified. ``travelled`` in production; a
#: parameter for one reason, which is the same reason ``Split`` is one: a case
#: can run the whole story-19 suite with the classifier switched off and watch
#: the footer rows collapse back to story 18's answer.
Classify = Callable[[Sequence[object]], bool]


def units(body: object, *, split: Split = terms) -> tuple[str, ...]:
    """``body`` as the ordered units this rule compares, or nothing at all.

    Whitespace is collapsed before splitting and the source is taken **whole**
    rather than line by line, which is ``half.derive.particular.quotes``'
    precedent and is deliberate for the same reason: an email's line breaks are
    its formatting, and a client that rewrapped a quoted paragraph would
    otherwise look like different text. It is also what makes a quoted reply
    match — ``>`` carries no term, so the quote marks a mail client staples to
    the front of every line simply are not there.

    Never raises, and the catch is narrow on purpose. ``TokenGrowthLimitError``
    is the **only** class ``half.text`` raises — checked by a case that reads
    every ``raise`` in that module's syntax tree rather than by trusting this
    sentence — so catching it is catching everything the tokenizer can produce,
    and a bare ``except Exception`` here would swallow a genuine defect as if it
    were an oversized body. A body past the growth ceilings yields nothing, so
    the rule declines on it rather than costing the run every receipt behind it.
    """
    if not isinstance(body, str):
        return ()
    try:
        return tuple(split(" ".join(body.split())))
    except TokenGrowthLimitError:
        return ()


def vocabulary(body: object, *, split: Split = terms) -> frozenset[str]:
    """The distinct units of ``body``. What ``overlap`` is measured over."""
    return frozenset(units(body, split=split))


def long_enough(written: Sequence[str]) -> bool:
    """Whether a body has enough distinct terms for containment to mean anything."""
    return len(frozenset(written)) >= MIN_TERMS


def an_echo(one: object, other: object, *, split: Split = terms) -> bool:
    """Whether these two bodies are the same evidence arriving twice.

    **The rule.** True when the smaller body's whole term sequence sits
    contiguously inside the larger one's — which is what *"a forward contains
    the original"* means literally, and is total by construction rather than by
    a threshold.

    Both sides must clear ``MIN_TERMS``: a body too short to be evidence cannot
    make another body a repeat of it, in either direction.

    Linear in the two bodies. The sequences are joined on ``JOIN`` and the
    question becomes one substring search, which Python answers in C — so the
    bounded window ``Run.declares`` compares against costs eight of these and
    nothing quadratic ever happens (story 9d).
    """
    mine = units(one, split=split)
    theirs = units(other, split=split)
    if not long_enough(mine) or not long_enough(theirs):
        return False
    return inside(mine, theirs)


def overlap(one: object, other: object, *, split: Split = terms) -> float:
    """How much of the smaller body's **vocabulary** is in the larger, 0 to 1.

    **Not the rule — the measurement that rejected one.** This is the fractional
    score the first version of this module fired on, kept because the numbers are
    the argument for the shape the module ended up with and a sentence saying
    *"a fractional floor percolates"* is exactly the kind of claim story 17 was
    written about. ``tests/test_echo.py`` asserts the confound row that a floor
    of 0.98 would have collapsed, so the rejected rule carries its own
    counterexample rather than being remembered.

    Measured on the *smaller* vocabulary on purpose: containment asks whether one
    body is inside the other, and a forward is larger than what it forwards.
    Either body being empty answers zero — nothing contains nothing.
    """
    mine = vocabulary(one, split=split)
    theirs = vocabulary(other, split=split)
    if not mine or not theirs:
        return 0.0
    inner, outer = (mine, theirs) if len(mine) <= len(theirs) else (theirs, mine)
    return len(inner & outer) / len(inner)


def own_key(body: object, *, split: Split = terms) -> str:
    """The declaration a body makes about itself, or ``""`` for one too short.

    A digest of the body's term **sequence**, so two bodies made of the same
    words in a different order are two bodies. That is ``half.text.sequence``'s
    correction, in the one place it would otherwise be re-made: *"prefers Delhi
    over Goa"* and *"prefers Goa over Delhi"* are not one message written twice.

    ``""`` is the correct absence. ``half.ingest.independence.an_identity``
    refuses an empty value on every axis, so a body that declares nothing unions
    with nothing — which is what keeps every empty body its own voice rather than
    one giant one.

    One-way by construction: a digest is not a body and cannot be turned back
    into one, so what leaves this module is a key and never content (AD-13).
    """
    return _handle(units(body, split=split))


def _handle(written: Sequence[str]) -> str:
    """``own_key``'s second half, over units already cut.

    Split out for one reason: ``declaring`` has the arriving body's units in
    hand and calling ``own_key`` would tokenize the same body a second time.
    That was a real cost — the arriving body is the longest thing in the
    comparison — and a docstring claiming one tokenization while paying for two
    is exactly the kind of unmeasured claim this module keeps being edited over.
    """
    if not long_enough(written):
        return ""
    digest = hashlib.sha256(JOIN.join(written).encode("utf-8")).hexdigest()
    return f"{PREFIX}{digest}"


def organisation(origin: object) -> str | None:
    """Which organisation an origin belongs to, or ``None`` where it cannot be read.

    **The one derivation this module makes from an origin, and it is one
    character.** ``half.ingest.independence`` compares origins verbatim under
    ``_normalize`` and derives nothing — no domain, no plus-address, no display
    name — because there it is deciding *identity*, and a derived identity is a
    new axis. Here the question is different: *is this block confined to one
    organisation*, and three people at one company are one organisation with
    three addresses. So the part after the last ``@`` is taken, and nothing else
    is: no public-suffix list, no subdomain folding, no known-provider table.

    ``_normalize`` is imported rather than re-spelled. Two spellings of one
    address match because it casefolds under NFC, and for no other reason — a
    second normalisation here would be a second idea of what one organisation is,
    and the two would disagree the first time a header arrived in a different
    case.

    ``None`` is the correct absence, and it is the answer for **every** origin
    this cannot read: absent, blank, whitespace, or carrying no ``@`` at all.
    ``travelled`` treats it as *cannot decide* rather than as agreement, which is
    story 17's blank-origin rule arriving at a second level — were blankness
    agreement, a mailbox whose ``from`` headers could not be read would classify
    every block as one organisation's furniture and hand story 18's defect back
    as a split.

    A display name is tolerated rather than parsed: ``Billing <b@svc.example>``
    ends at the address because the last ``@`` is inside the angle brackets, and
    the brackets are stripped off the end. That is not an address parser and does
    not pretend to be one; a shape it cannot read answers ``None``, which
    declines.
    """
    if not an_identity(origin):
        return None
    local, at, home = _normalize(str(origin)).rpartition(AT)
    if not at or not local.strip():
        return None
    return home.strip().strip("<>").strip() or None


def travelled(origins: Sequence[object]) -> bool:
    """Whether the block these origins carry is being passed on, or is furniture.

    **Story 19's whole discriminator, and the reason it is the only one that
    works.** A legal footer is stapled by one organisation to its own outgoing
    mail; a forwarded original travels between different senders, which is what
    forwarding is. So a block whose carriers are all at one organisation is that
    organisation's furniture and must not make two messages one voice, and a
    block whose carriers cross organisations is the thing being passed on and
    must.

    ``True`` means **story 18's answer stands** — adopt the held body's key, the
    two are one voice. ``False`` is the only branch that changes anything, and it
    changes it in the direction that *admits* claims, which is why every
    uncertainty answers ``True``:

    * fewer than two carriers — there is nothing to classify from, and a block
      seen once has not been shown to stay anywhere;
    * an origin that cannot be read — blankness is not agreement (story 17), so
      one unreadable carrier declines for the whole block rather than letting
      the readable ones vote;
    * more than one organisation — it travelled.

    Story 18 could say its failures should merge, because Half saying less is
    the conservative failure. That stopped being automatic here: this rule can
    also *split*, and a split admits claims. So the fallback is story 18's
    answer and never "independent".
    """
    homes = [organisation(origin) for origin in origins]
    if len(homes) < 2 or any(home is None for home in homes):
        return True
    return len(set(homes)) > 1


def carrying(
    block: Sequence[str],
    window: Iterable[Cut],
) -> tuple[object, ...]:
    """The origin of every body in ``window`` that carries ``block``.

    **Bounded by exactly what it is handed and never wider** — ``window`` is
    ``declaring``'s cut of the caller's held window, which ``Run.hold`` caps at
    ``MAX_SOURCES``. There is no pass over a mailbox, no second store and no
    state (story 9d, AD-13, AD-22): what comes back is a tuple of origins, and
    the bodies stay where they were.

    ``contains`` rather than ``inside``, and the direction is the point: a
    carrier is a body the block is **in**. A held body shorter than the block is
    not a carrier of it however much they share.

    A body that declared nothing is skipped, for the reason ``declaring`` skips
    it — it is one the rule could not read, either too short to compare or past
    the tokenizer's ceilings. The second of those is residue: an oversized body
    that genuinely carries the block is a carrier this cannot see, which makes
    the origin set smaller and so makes *furniture* — the splitting answer —
    marginally likelier. Recorded rather than guessed at.
    """
    return tuple(
        whose for key, theirs, whose in window
        if key and contains(theirs, block)
    )


def declaring(
    body: object,
    held: Iterable[Window],
    *,
    origin: object,
    split: Split = terms,
    classify: Classify = travelled,
) -> str:
    """The key ``body`` declares, given the window already in hand.

    ``held`` is ``(key, body, origin)`` per held body and ``origin`` is the
    arriving body's own. The whole of the rule, in the shape
    ``Candidate.independence_key`` takes:

    * a body too short to compare declares nothing;
    * a body that contains — or is contained by — one already held adopts **that
      body's** declaration, so the two are one voice, **unless the block they
      share never leaves one organisation**, in which case the block is that
      organisation's furniture and the two stay apart;
    * anything else declares its own handle, which is what leaves the original
      something for its forward to adopt later.

    ``held`` is the caller's bounded window and this function never widens it,
    and ``Run.hold`` caps that window at ``MAX_SOURCES``. There is no pass over
    every candidate and nothing quadratic in a mailbox (story 9d).

    **The cost, stated honestly, because the first version of this line was
    wrong twice.** It once claimed one tokenization; it then admitted that a
    window of eight costs nine, because the window carried texts rather than
    units and every held body was cut again on every arrival. Story 19 would
    have made that quadratic — a classification per match, each re-reading the
    window — so the window is now cut **once**, before the loop, and ``carrying``
    is handed the units. A window of eight still costs nine tokenizations per
    arriving message, whatever the shape of what arrives.

    **The first *travelling* match wins, in the caller's arrival order, and that
    is a limit.** Every held body in one containment chain already carries the
    same key, so *which* of them matched cannot change the answer for a chain. It
    is not a chain that this loses: a body containing **two** unrelated held
    originals — a digest mail, or a forward of a thread quoting several messages
    — unions with the first and leaves the others standing as separate supports,
    which is ordinary mail rather than a contrived shape. Recorded as an accepted
    limit and pinned by a case; the harm is under-collapsing, which leaves those
    others exactly as independent as they were before this rule existed.

    Story 19 narrows *first match* to *first travelling match*: a held body whose
    shared block is furniture is stepped over rather than ending the search, so a
    genuine forward further down the window is still found. Strictly more of
    story 18's rule reaches its answer than before, never less.
    """
    mine = units(body, split=split)
    if not long_enough(mine):
        return ""
    # Cut once. The comprehension is the only place ``held`` is read, so the
    # bound the caller set is the bound both loops below run under.
    window: list[Cut] = [
        (key, units(text, split=split), whose) for key, text, whose in held
    ]
    for key, theirs, _whose in window:
        if not key or not long_enough(theirs):
            continue
        if not inside(mine, theirs):
            continue
        # The block is the smaller body — that is what containment means — and
        # its carriers are every body in hand that it sits inside, the arriving
        # one included. ``carrying`` finds the held ones; the arriving body is
        # a carrier by construction, since it matched.
        block = mine if len(mine) <= len(theirs) else theirs
        if classify((origin, *carrying(block, window))):
            return key
    return _handle(mine)


def contains(outer: Sequence[str], inner: Sequence[str]) -> bool:
    """Whether ``inner``'s whole sequence sits contiguously inside ``outer``'s.

    **Directional, which ``inside`` is not, and story 19 needs the direction.**
    Asking *"who carries this block"* means asking which bodies the block is
    **in**, and a held body shorter than the block that happens to sit inside it
    is not one of them. ``inside`` answered that question in both directions at
    once, which is right for *"are these two the same evidence"* and wrong for
    *"is this body a carrier"*.

    Joined on a sentinel that cannot occur inside a term and searched as a
    string, so this is one C-level substring search rather than a sliding window
    in Python. The leading and trailing sentinels are what keep the match on
    whole-term boundaries at the ends.

    Either sequence being empty answers ``False``: nothing contains nothing, and
    two empty bodies must not be one voice. Without the guard the joined form of
    two empty sequences is one sentinel found inside another.
    """
    if not outer or not inner or len(inner) > len(outer):
        return False
    needle = JOIN + JOIN.join(inner) + JOIN
    haystack = JOIN + JOIN.join(outer) + JOIN
    return needle in haystack


def inside(mine: Sequence[str], theirs: Sequence[str]) -> bool:
    """Whether either sequence sits contiguously inside the other.

    **Public because a second consumer arrived**, and the alternative was a
    second implementation. ``tools/percolation_sim.py`` compares every pair in a
    thousand-message mailbox, which is a hundred times more comparisons than the
    product ever makes, and it can only afford that by tokenizing each body once
    and comparing the ``units`` directly. Ask this with two ``units`` results, or
    ask ``an_echo`` with two bodies; there is no third way to spell the rule.

    ``contains`` in both directions, and spelled that way rather than repeated:
    the sentinel discipline that makes the search whole-term lives in one place,
    and a rule about mailbox ordering is exactly what an asymmetric answer here
    would be.
    """
    return contains(theirs, mine) or contains(mine, theirs)


def _check_rule() -> None:
    """Import-time invariants, as raises rather than bare ``assert``.

    A guarantee ``python -O`` removes is not a guarantee, and both of these are
    a one-character edit away from a rule that either collapses a mailbox or
    does nothing at all.
    """
    if MIN_TERMS < 2:
        raise ValueError(
            f"a minimum of {MIN_TERMS} distinct terms lets an empty or one-word "
            "body declare a key, so every empty body would answer to the same "
            "handle and a mailbox nothing could be read out of would count as "
            "one support"
        )
    if JOIN.isalnum() or not JOIN:
        raise ValueError(
            f"the term separator {JOIN!r} can appear inside a term, so a "
            "containment search would match across term boundaries and 'rat' "
            "would be found inside 'gratis'"
        )
    if not travelled(("a@one.example", "b@two.example")):
        raise ValueError(
            "a block carried by two organisations no longer classifies as "
            "travelling, so every forward is furniture and story 18's defect "
            "is back as a split — which admits claims rather than withholding "
            "them, the direction CAP-3 exists to prevent"
        )
    if travelled(("a@one.example", "b@one.example")):
        raise ValueError(
            "a block confined to one organisation classifies as travelling, so "
            "the classifier decides nothing and a footer-only message collapses "
            "every message that carries it (story 19's defect)"
        )
    if not travelled(("a@one.example", "")) or not travelled(("a@one.example",)):
        raise ValueError(
            "the classifier answers on an unreadable origin or on a single "
            "carrier. Both are *cannot decide*, and both must fall back to "
            "story 18's answer: blankness is not agreement (story 17), and a "
            "branch that cannot decide must merge rather than split"
        )


_check_rule()
