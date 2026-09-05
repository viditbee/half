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
identity, and ``domain`` reuses its ``normalized`` rather than inventing a
second idea of what two spellings of one address are. The two agree on
casefolding under NFC and on nothing else: that module compares whole addresses,
this one compares the tail.

**A domain is not an organisation, and the first build of this rule proved it.**
Two people at ``gmail.com`` are not one company. Read as one, an ordinary
forward between them was that "organisation's" furniture, refused to collapse,
and became **two supports from one message** — story 18's over-claiming defect
handed back for what is plausibly the commonest sender population in a personal
mailbox. Measured through ``Run.declares``, truth one in every row:
``gmail.com`` **2** voices, ``outlook.com`` **2**, two students at one
university **2**.

So a domain that hosts many unrelated people — a webmail provider, an ISP, a
university — is not an organisation. ``shared`` names them, ``organisation``
answers ``None`` for them, and a block carried only there tells us nothing and
declines. A domain *not* on that list is an organisation, which is what keeps
the footer attractor fixed.

**That list names origins and never text, which is why it is not the pattern
list this approach exists to avoid.** A disclaimer, a separator and a signature
exist in every language and matching them is a rule about how mail *reads*;
``gmail.com`` is a fact about the world and is spelled the same in every
language. The list is also **incomplete by nature** and leans deliberately
permissive, because its two error directions are not symmetric: a domain
wrongly on it declines, which merges and under-claims, while a provider missing
from it splits an ordinary forward, which over-claims. So a family with country
variants — ``hotmail.*``, ``yahoo.*`` — is matched on its first label rather
than enumerated, and the academic pattern (``.edu``, ``.ac.<cc>``,
``.edu.<cc>``) is matched by shape rather than by listing universities.

**The limits this leaves, stated up front rather than buried.** A forward that
never leaves one organisation looks exactly like that organisation's furniture,
because on the only signal that works it *is* the same shape. Half counts it as
two supports. That is the **over-claiming** direction — the one story 18 closed
— so it is the more serious residue of the two, and it is pinned by
``test_a_forward_inside_one_company_is_not_caught`` with its direction named.
A forward on a provider **absent** from ``SHARED_DOMAINS`` is the same defect
reached through the list's incompleteness, and is pinned beside it. In the other
direction — merging, so the conservative one — a footer stapled by a shared-
domain sender, a university mailing its own students, still collapses the
messages carrying it, because the exclusion cannot tell that block from a
forward between two people at that university.

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
from half.ingest.independence import an_identity, normalized
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

#: What separates a local part from the domain that carries it.
AT: Final[str] = "@"

#: What separates the labels of a domain.
DOT: Final[str] = "."

#: Domains that host **many unrelated people**, so that two addresses at one of
#: them are not one organisation and a block carried only there says nothing.
#:
#: **Origins, never text.** The Never list forbids a pattern list for
#: disclaimers, separators, quote markers and signatures — rules about how mail
#: *reads*, which differ in every language and are the failure this whole
#: approach is chosen to avoid. This is data about the world: ``gmail.com`` is
#: spelled ``gmail.com`` in every language on earth.
#:
#: **Worldwide, and incomplete by nature.** A list of Western providers alone
#: would be its own defect, so the large regional providers are here. It can
#: never be complete, and the two ways of being wrong are not symmetric: a
#: domain wrongly listed declines, which merges and under-claims, and a provider
#: missing from it splits an ordinary forward, which over-claims and is the
#: serious direction. So it leans permissive on purpose, and what it misses is a
#: recorded limit rather than a surprise.
SHARED_DOMAINS: Final[frozenset[str]] = frozenset({
    # Global webmail.
    "gmail.com", "googlemail.com", "outlook.com", "hotmail.com", "live.com",
    "msn.com", "yahoo.com", "ymail.com", "rocketmail.com", "aol.com",
    "icloud.com", "me.com", "mac.com", "mail.com", "gmx.com", "gmx.net",
    "zoho.com", "proton.me", "protonmail.com", "protonmail.ch",
    "tutanota.com", "tuta.com", "fastmail.com", "hushmail.com",
    # China, Korea, Japan.
    "qq.com", "163.com", "126.com", "yeah.net", "sina.com", "sohu.com",
    "naver.com", "daum.net", "hanmail.net", "nate.com",
    "docomo.ne.jp", "ezweb.ne.jp", "softbank.ne.jp", "nifty.com",
    # Russia and the CIS.
    "mail.ru", "inbox.ru", "list.ru", "bk.ru", "internet.ru",
    "yandex.ru", "yandex.com", "rambler.ru", "ukr.net", "i.ua",
    # Western Europe.
    "gmx.de", "web.de", "t-online.de", "freenet.de", "arcor.de",
    "orange.fr", "wanadoo.fr", "free.fr", "laposte.net", "sfr.fr",
    "libero.it", "virgilio.it", "alice.it", "tin.it", "tiscali.it",
    "terra.es", "telefonica.net", "sapo.pt", "ziggo.nl", "kpnmail.nl",
    "telenet.be", "skynet.be", "bluewin.ch", "gmx.at", "aon.at",
    "btinternet.com", "sky.com", "virginmedia.com", "talktalk.net",
    "eircom.net", "telia.com", "online.no", "bredband.net", "elisanet.fi",
    # Central and Eastern Europe.
    "seznam.cz", "centrum.cz", "atlas.cz", "azet.sk", "zoznam.sk",
    "wp.pl", "o2.pl", "interia.pl", "onet.pl", "gazeta.pl",
    "freemail.hu", "citromail.hu", "abv.bg", "mail.bg",
    # Latin America.
    "uol.com.br", "bol.com.br", "terra.com.br", "ig.com.br", "globo.com",
    "prodigy.net.mx", "hotmail.com.ar",
    # South Asia, the Middle East and Africa.
    "rediffmail.com", "sify.com", "indiatimes.com", "in.com",
    "emirates.net.ae", "walla.co.il", "webmail.co.za", "vodamail.co.za",
    # Oceania.
    "bigpond.com", "optusnet.com.au", "iinet.net.au", "xtra.co.nz",
})

#: The **first label** of a family that ships a domain per country. Enumerating
#: ``hotmail.co.uk``, ``hotmail.fr``, ``yahoo.co.jp``, ``yahoo.com.br`` and the
#: hundred others is a list nobody will keep current, and a missing entry is the
#: over-claiming direction. So the family is matched by name and the country
#: part is not read at all.
#:
#: The cost is stated rather than hidden: a company whose domain *starts* with
#: one of these labels — ``live.example.com`` — is read as shared and declines.
#: That is the merging direction, which is the side to be wrong on.
SHARED_HOSTS: Final[frozenset[str]] = frozenset({
    "hotmail", "yahoo", "ymail", "rocketmail", "outlook", "live", "msn",
    "gmail", "googlemail", "aol", "gmx", "yandex", "zoho", "protonmail",
})

#: The label that makes a domain academic, in the two shapes it takes: a
#: ``.edu`` top level, and ``ac`` or ``edu`` as the label before a two-letter
#: country code — ``cam.ac.uk``, ``u-tokyo.ac.jp``, ``usp.edu.br``.
#:
#: A university is the same shape as a webmail provider for this rule's purpose:
#: thousands of unrelated people at one domain, so two of them forwarding mail
#: to each other is not one organisation talking to itself. Matched by shape
#: because listing the world's universities is not a list anyone can hold.
ACADEMIC_LABELS: Final[frozenset[str]] = frozenset({"ac", "edu"})

#: How a body is cut into the units that are compared. ``half.text.terms`` in
#: production and never anything else; a parameter only so a case can run the
#: same suite against ``half.context.build.runs`` and watch the unspaced scripts
#: go to zero.
Split = Callable[[str], Sequence[str]]

#: **One** held body, as ``declaring`` is handed it: what that body declared,
#: the body itself, and **the origin that carried it**. The third field is story
#: 19's whole addition to the window's shape — the classification asks who
#: carries a block, and a window of texts alone cannot answer it.
#:
#: A triple rather than a pair with a default, deliberately: a caller that
#: forgets the origin is a ``ValueError`` at unpacking, where an optional third
#: field would silently classify every block as one organisation's furniture and
#: quietly hand story 18's defect back as a split.
#:
#: Singular, and the plural is a ``list[Held]``. The first spelling of these two
#: names had ``Window`` for one body and ``Cut`` for one cut body, which inverts
#: the relationship a reader expects between a window and the things in it.
Held = tuple[str, object, object]

#: **One** held body after ``declaring`` has cut it: its declaration, its units,
#: those units already joined for searching, and its **organisation** — the
#: three derivations that would otherwise be redone on every match.
#:
#: All three are here for measured reasons. Tokenizing per match made the cost
#: quadratic in the window. Rebuilding the joined form per match cost up to
#: sixty-four string joins on a window of eight that every body matched.
#: Re-deriving the organisation per call did the same for the classifier. A
#: window of eight now costs eight tokenizations, eight joins and eight domain
#: reads per arriving message, whatever the shape of what arrives.
Cut = tuple[str, tuple[str, ...], str, str | None]

#: How a block's carriers are classified — over **resolved organisations**, not
#: over raw origins. ``travelled`` in production; a parameter for one reason,
#: which is the same reason ``Split`` is one: a case can run the whole story-19
#: suite with the classifier switched off and watch the footer rows collapse
#: back to story 18's answer.
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


def domain(origin: object) -> str | None:
    """The domain of an origin, or ``None`` where it cannot be read.

    **The whole of the derivation, and it is one field of an address.** No
    public-suffix list, no subdomain folding, no known-provider table, no
    plus-address stripping, and no locale. ``normalized`` is
    ``half.ingest.independence``'s own, so two spellings of one address agree
    here exactly as they agree there — on casefolding under NFC, and on nothing
    else, since that module compares whole addresses and this one compares the
    tail.

    **A display name is parsed, and calling that "one character" was wrong.**
    Every real ``From:`` header is ``Billing <billing@svc.example>``, so a
    version that declined on the angle-bracket form would turn this rule off for
    most of a real mailbox — which is the over-claiming direction. So the
    brackets are handled: exactly one ``@``, the tail taken, one trailing ``>``
    removed, and one trailing root dot removed so ``corp.example.`` and
    ``corp.example`` are one organisation rather than two.

    **Everything it cannot read declines, which merges.** A non-string; an
    absent, blank or whitespace origin; no ``@`` at all (a bare display name is
    not an address); *more than one* ``@``, which is two addresses in one header
    and picking either would be a guess; an empty local part; and anything left
    that is not shaped like a domain — no dot, an empty label, or a character
    that is neither alphanumeric nor a hyphen, which is what catches
    ``corp.example (Legal)``.

    The type check is not decoration. ``str(b"a@corp.example")`` is
    ``"b'a@corp.example'"``, whose tail reads as a plausible domain, so coercing
    would have answered confidently on a value that is not an address at all —
    the same refusal ``Run.declares`` makes when it is handed something that is
    not a ``Scrubbed``.
    """
    if not isinstance(origin, str) or not an_identity(origin):
        return None
    value = normalized(origin)
    if value.count(AT) != 1:
        return None
    local, _, home = value.partition(AT)
    if not local.strip():
        return None
    home = home.strip()
    if home.endswith(">"):
        home = home[:-1].strip()
    home = home.rstrip(DOT)
    return home if _a_domain(home) else None


def _a_domain(home: str) -> bool:
    """Whether what is left after the ``@`` is shaped like a domain at all.

    Deliberately a shape check and not a grammar: at least two labels, none of
    them empty, no whitespace anywhere, and every **ASCII** character
    alphanumeric or a hyphen.

    **Non-ASCII is allowed through, and that is a worldwide requirement rather
    than laxity.** An internationalised domain is non-ASCII by definition, and
    the obvious spelling — ``character.isalnum() or character == "-"`` — rejects
    it, because a Devanagari matra and an Arabic harakat are *marks* rather than
    alphanumerics. That version answered ``None`` for
    ``संपर्क@उदाहरण.भारत``, which is this rule declining for a large share of the
    world with nothing saying so. Excluding the marks would need
    ``unicodedata``, which this module may not import (see the purity case), and
    the whitespace test is Unicode-aware on its own — so what a non-ASCII
    character could smuggle past this is a non-ASCII *punctuation* mark inside a
    domain, which is neither a shape real headers produce nor one that changes
    the answer for any block.
    """
    if not home or DOT not in home:
        return False
    labels = home.split(DOT)
    if not all(labels):
        return False
    return all(
        not character.isspace()
        and (not character.isascii() or character.isalnum() or character == "-")
        for label in labels for character in label
    )


def shared(home: object) -> bool:
    """Whether a domain hosts **many unrelated people** rather than one company.

    Two addresses at ``gmail.com`` are two strangers who happen to use one
    provider, so a block carried only there has been shown to stay nowhere. The
    first build of this rule missed that and read any domain as an organisation,
    which made an ordinary forward between two ``gmail.com`` addresses two
    supports from one message — story 18's over-claiming defect, handed back for
    the commonest sender population in a personal mailbox.

    Three ways to match, and each is chosen so the answer does not depend on a
    list somebody has to keep current:

    * the domain, **or any suffix of it**, is in ``SHARED_DOMAINS`` — so
      ``mail.yahoo.com`` is matched by ``yahoo.com``;
    * any such suffix begins with a label in ``SHARED_HOSTS``, which is how the
      country variants of one family are covered without enumerating them;
    * the domain is academic by shape — a ``.edu`` top level, or ``ac``/``edu``
      before a two-letter country code. A university is thousands of unrelated
      people at one domain, which is this rule's own definition of shared.

    Single-label suffixes are never tested, so a top level alone can never make
    a domain shared and ``corp.example`` is not matched by ``example``.
    """
    if not isinstance(home, str) or not home:
        return False
    labels = home.split(DOT)
    if _academic(labels):
        return True
    for start in range(len(labels) - 1):
        suffix = labels[start:]
        if DOT.join(suffix) in SHARED_DOMAINS or suffix[0] in SHARED_HOSTS:
            return True
    return False


def _academic(labels: Sequence[str]) -> bool:
    """Whether these domain labels are a university's, by shape.

    ``mit.edu``; ``cam.ac.uk``, ``u-tokyo.ac.jp``, ``usp.edu.br``. The
    two-letter test on the last label is what keeps ``edu.example`` and
    ``ac.example`` out, and the three-label minimum keeps a bare ``ac.uk`` — not
    an address anybody has — from matching.
    """
    if labels and labels[-1] == "edu":
        return True
    return (len(labels) >= 3 and labels[-2] in ACADEMIC_LABELS
            and len(labels[-1]) == 2)


def organisation(origin: object) -> str | None:
    """The organisation an origin belongs to, or ``None`` where there is none.

    ``domain`` unless that domain is ``shared``, in which case there is no
    organisation to read: a webmail provider, an ISP and a university are places
    many unrelated people send mail from, and a block carried only there has not
    been shown to stay anywhere.

    ``None`` therefore means the same thing for both causes — *this tells us
    nothing* — and ``travelled`` treats it the same way for both, which is
    story 18's answer and the merging direction.
    """
    home = domain(origin)
    return None if home is None or shared(home) else home


def travelled(homes: Sequence[object]) -> bool:
    """Whether a block carried by these **organisations** is being passed on.

    **Story 19's whole discriminator, and the reason it is the only one that
    works.** A legal footer is stapled by one organisation to its own outgoing
    mail; a forwarded original travels between different senders, which is what
    forwarding is. So a block whose carriers are all at one organisation is that
    organisation's furniture and must not make two messages one voice, and a
    block whose carriers cross organisations is the thing being passed on and
    must.

    **It takes resolved organisations, not raw origins**, because ``declaring``
    resolves each held body's once per arrival rather than once per match.
    ``organisation`` is the only thing that produces one; a value with an ``@``
    still in it is a caller that forgot, and is read as unresolved rather than
    compared — which declines and merges instead of answering confidently on a
    string this function was never given.

    ``True`` means **story 18's answer stands** — adopt the held body's key, the
    two are one voice. ``False`` is the only branch that changes anything, and it
    changes it in the direction that *admits* claims, which is why every
    uncertainty answers ``True``:

    * fewer than two carriers — there is nothing to classify from, and a block
      seen once has not been shown to stay anywhere;
    * an organisation that cannot be read — a blank origin (story 17's rule:
      blankness is not agreement), an unparseable one, or a shared domain, where
      two addresses are two strangers;
    * more than one organisation — it travelled.

    Story 18 could say its failures should merge, because Half saying less is
    the conservative failure. That stopped being automatic here: this rule can
    also *split*, and a split admits claims. So the fallback is story 18's
    answer and never "independent".
    """
    resolved = list(homes)
    if len(resolved) < 2:
        return True
    if any(not isinstance(home, str) or AT in home for home in resolved):
        return True
    return len(set(resolved)) > 1


def carrying(
    block: Sequence[str],
    window: Iterable[Cut],
) -> tuple[object, ...]:
    """The organisation of every body in ``window`` that carries ``block``.

    **Bounded by exactly what it is handed and never wider** — ``window`` is
    ``declaring``'s cut of the caller's held window, which ``Run.hold`` caps at
    ``MAX_SOURCES``. There is no pass over a mailbox, no second store and no
    state (story 9d, AD-13, AD-22): what comes back is a tuple of organisations,
    and the bodies stay where they were.

    **Directional, and the direction is the point**: a carrier is a body the
    block is **in**. A held body shorter than the block is not a carrier of it
    however much they share, which is why this searches ``needle in joined`` and
    never the other way round.

    The block is joined **once**, at the top, and every held body's joined form
    was built when the window was cut. So a window of eight costs one join and
    eight searches, where the first version of this function rebuilt both sides
    for every held body it looked at.

    A body that declared nothing is skipped, for the reason ``declaring`` skips
    it — it is one the rule could not read, either too short to compare or past
    the tokenizer's ceilings. The second of those is residue: an oversized body
    that genuinely carries the block is a carrier this cannot see, which makes
    the organisation set smaller and so makes *furniture* — the splitting
    answer — marginally likelier. Pinned by a case rather than guessed at.
    """
    if not block:
        return ()
    needle = _joined(block)
    return tuple(home for key, _written, joined, home in window
                 if key and needle in joined)


def declaring(
    body: object,
    held: Iterable[Held],
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

    **The cost, stated honestly, because this line has been wrong three times.**
    It once claimed one tokenization. It then admitted a window of eight costs
    nine, because the window carried texts rather than units. It then counted
    only tokenizations and said nothing about the joins and searches story 19
    added. What the code does now, per arriving message against a window of
    ``w``:

    * ``w`` tokenizations and ``w`` string joins — the window is cut once,
      before the loop — plus one of each for the arriving body;
    * ``w`` substring searches to find the matches, and no join at all in the
      loop, because both sides were joined before it;
    * one join and ``w`` searches per **match**, inside ``carrying``, so at
      worst ``w`` joins and ``w²`` searches when every held body matches *and
      every one of them is furniture* — a travelling match returns, so it costs
      one. The worst case is therefore ``2w + 1`` joins in all: measured at
      ``MAX_SOURCES``, **17** where every match is furniture and **10** where
      the first one travels, against sixty-four joins before this was fixed. A
      constant, and not anything that grows with a mailbox;
    * ``w + 1`` domain reads, one per cut entry and one for the arriving origin.

    **Cutting the window is unconditional, and that is a trade rather than free.**
    A held body with no key, or one too short to compare, is now tokenized before
    it is skipped, where the first version skipped it first. That is at most ``w``
    tokenizations of bodies the rule will not use. It is paid because the moment
    *any* match happens ``carrying`` needs the whole window cut anyway, and
    cutting lazily would mean either cutting twice or carrying a half-built
    window into the classifier. The bound a case asserts — one reading per held
    body plus one — is therefore exact rather than an upper limit, and it
    forbids an early-exit shape that would have saved nothing.

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
    shared block is furniture is **stepped over** rather than ending the search,
    so a genuine forward further down the window is still found. That matters on
    an ordinary shape — a forward carrying its forwarder's legal footer, arriving
    after the footer itself — where returning on the first match would hand the
    forward the footer's key and leave the original standing as a second support.
    Strictly more of story 18's rule reaches its answer than before, never less.
    """
    mine = units(body, split=split)
    if not long_enough(mine):
        return ""
    mine_joined = _joined(mine)
    # Cut once. The comprehension is the only place ``held`` is read, so the
    # bound the caller set is the bound the loop below runs under.
    window: list[Cut] = [_cut(key, text, whose, split) for key, text, whose in held]
    home = organisation(origin)
    for key, theirs, theirs_joined, _theirs_home in window:
        if not key or not long_enough(theirs):
            continue
        # ``_inside_joined`` rather than ``inside``: both joined forms are
        # already built — the window's when it was cut, the arriving body's
        # above — and ``inside`` would rebuild both on every comparison, which
        # is ``w`` extra joins of the arriving body per arrival.
        if not _inside_joined(mine, mine_joined, theirs, theirs_joined):
            continue
        # The block is the smaller body — that is what containment means — and
        # its carriers are every body in hand that it sits inside, the arriving
        # one included. ``carrying`` finds the held ones; the arriving body is
        # a carrier by construction, since it matched.
        block = mine if len(mine) <= len(theirs) else theirs
        if classify((home, *carrying(block, window))):
            return key
    return _handle(mine)


def _cut(key: str, text: object, whose: object, split: Split) -> Cut:
    """One held body, with every derivation this rule makes from it done once.

    A module-level function rather than a nested expression so that the guard
    reading ``declaring``'s syntax tree can say what the comprehension building
    the window is allowed to call: a name this module already exposes, each of
    which is pure and reads only what it is handed.
    """
    written = units(text, split=split)
    return (key, written, _joined(written), organisation(whose))


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
    return _joined(inner) in _joined(outer)


def inside(mine: Sequence[str], theirs: Sequence[str]) -> bool:
    """Whether either sequence sits contiguously inside the other.

    **Public because a second consumer arrived**, and the alternative was a
    second implementation. ``tools/percolation_sim.py`` compares every pair in a
    thousand-message mailbox, which is a hundred times more comparisons than the
    product ever makes, and it can only afford that by tokenizing each body once
    and comparing the ``units`` directly. Ask this with two ``units`` results, or
    ask ``an_echo`` with two bodies; there is no third way to spell the rule.

    **One search, not two.** This was ``contains`` asked in both directions,
    which is two joins and two searches where one of each answers — and
    ``tools/percolation_sim.py``, its second consumer, pays that a hundred times
    over, since it compares every pair in a thousand-message mailbox. The
    shorter sequence is the inner one, which is what containment means.

    The rule itself lives in ``_inside_joined`` and is spelled once.
    ``declaring`` calls that directly, because it has both joined forms already
    and calling this would rebuild them on every comparison — which is the join
    cost this rewrite exists to remove. Both callers therefore run the same
    line, and a mutation to it is a mutation to both.
    """
    return _inside_joined(mine, _joined(mine), theirs, _joined(theirs))


def _inside_joined(mine: Sequence[str], mine_joined: str,
                   theirs: Sequence[str], theirs_joined: str) -> bool:
    """``inside``, over sequences whose joined forms are already built.

    The one place the containment rule is spelled. It takes both forms of both
    sides rather than deriving either, so the caller that has them — the loop in
    ``declaring``, where the window was joined once when it was cut — pays no
    join at all, and the caller that does not — ``inside`` — builds them once.
    """
    if not mine or not theirs:
        # Nothing contains nothing, and two empty bodies must not be one voice.
        return False
    if len(mine) <= len(theirs):
        return mine_joined in theirs_joined
    return theirs_joined in mine_joined


def _joined(written: Sequence[str]) -> str:
    """``written`` as the sentinel-wrapped string every containment search runs on.

    One place, because the leading and trailing sentinels are what keep a match
    on whole-term boundaries at the ends, and two spellings of that would be two
    rules. Built once per body when the window is cut, rather than once per
    comparison.
    """
    return JOIN + JOIN.join(written) + JOIN


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
    if not travelled(("one.example", "two.example")):
        raise ValueError(
            "a block carried by two organisations no longer classifies as "
            "travelling, so every forward is furniture and story 18's defect "
            "is back as a split — which admits claims rather than withholding "
            "them, the direction CAP-3 exists to prevent"
        )
    if travelled(("one.example", "one.example")):
        raise ValueError(
            "a block confined to one organisation classifies as travelling, so "
            "the classifier decides nothing and a footer-only message collapses "
            "every message that carries it (story 19's defect)"
        )
    if not travelled(("one.example", None)) or not travelled(("one.example",)):
        raise ValueError(
            "the classifier answers on an unreadable organisation or on a "
            "single carrier. Both are *cannot decide*, and both must fall back "
            "to story 18's answer: blankness is not agreement (story 17), and a "
            "branch that cannot decide must merge rather than split"
        )
    if not travelled(("a@one.example", "b@one.example")):
        raise ValueError(
            "the classifier compared raw origins as though they were resolved "
            "organisations; a caller that forgot ``organisation`` must decline "
            "and merge rather than be answered confidently on two addresses "
            "that share a company"
        )
    if organisation("a@corp.example") != "corp.example":
        raise ValueError(
            "an ordinary company address no longer resolves to its domain, so "
            "no block is ever furniture and the footer attractor is back"
        )
    for anyone in ("a@gmail.com", "b@yahoo.co.uk", "c@cam.ac.uk"):
        if organisation(anyone) is not None:
            raise ValueError(
                f"{anyone!r} resolved to an organisation. A webmail provider, "
                "an ISP and a university host many unrelated people, so two "
                "addresses at one of them are two strangers — reading them as "
                "one company makes an ordinary forward between them two "
                "supports from one message, which is story 18's over-claiming "
                "defect handed back"
            )


_check_rule()
