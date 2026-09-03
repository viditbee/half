"""The license split, and directives assembled from structured fields (AD-18).

This is where enforcement happens. Licenses are resolved here, once, and the
material a rung does not permit is never assembled into a quotable field — so
there is nothing downstream to filter and no generated text to inspect. A
post-generation filter would invert AD-18 exactly: pay for the tokens, then
trust a classifier to suppress them.

**Fail closed, at every step.** Every uncertain case resolves toward the
weakest rung, because the cost of the two mistakes is not symmetric: losing a
directive costs subtlety, leaking one costs trust. Which rung a belief lands on
is the ladder's answer; what this module adds is that a directive whose only
available topic echoes the claim is dropped rather than degraded.

**A question is not a rung, it is a purchase** (CAP-4, story 11). Every other
channel is decided by what a belief's license resolves to; the question channel
needs that *and* a favour already spent, and this module is told which belief
was paid for rather than working it out. That is deliberate and it is story
10's lesson repeated: a subsystem that decides for itself which beliefs deserve
a question can be made to decide wrongly, whereas one that can only emit what it
was handed cannot. An `ask`-rung belief nobody bought becomes a *directive* —
Half may act on it silently and may not raise it — so nothing is filtered away
and AD-18's second failure stays closed.

**The rung rules are the ladder's, and the ceiling is applied here** (AD-28).
``resolve`` is the single place a license becomes a decision, which is exactly
why the actor's global ceiling belongs inside it and not beside whatever
composes a message. What the rungs *require* is not stated here at all —
``half.governance.ladder`` holds that, and its module docstring is the one
account of it.

**Directives are assembled, never paraphrased.** AD-18 illustrates a directive
as *"be gentle if travel comes up"*, which is a paraphrase, and paraphrase needs
a model AD-19 leaves unbuilt. The deterministic form of the same idea is the
belief's own structured fields — loop, topic, subject — which the log wrote
separately from the claim. A paraphrase built from the claim's own words would
be a quotation with extra steps.

**The drop rule is per belief, not per field.** If any of a belief's structured
topics echoes its claim, the whole directive is dropped rather than emitted
with the offending topic removed. Emitting the safe half is precisely the
degradation the story forbids: it announces which words were unsafe.

**Withholding is by fragment, and the guard runs here rather than in a test.**
A guard that blocks only a withheld claim *entire* lets its whole substance
through inside somebody else's sentence — ``"has been avoiding the conversation
with his brother"`` is withheld while ``"he keeps avoiding the conversation
with his brother lately"`` is quoted, and every word that mattered has been
said. So the unit is the **adjacent pair**: no two consecutive words of a
withheld claim may appear consecutively anywhere in the context. Checking pairs
is sufficient for runs of every length, because a longer shared run contains a
shared pair.

A pair rather than a single word, deliberately. A single shared word is a
*topic*, and naming a topic is exactly what the directives channel is licensed
to do — a one-word floor would empty that channel and land on AD-18's second
named failure, Half left blunt about what it may not name. Two adjacent words
are wording, and wording is what may not be quoted. The cost is real and
one-directional: an `assert` claim sharing an incidental pair (``"has been"``)
with some `behave` claim is dropped from content. Half says less; Half never
says what it may not.

**Comparison ignores spacing, and the invisible characters between words.**
Japanese does not space its words, so ``転職 を 考えている`` sits unspaced inside
``日記に「転職を考えている」と書いた`` and a spaced comparison misses it entirely.
Words are therefore concatenated before matching. Format characters — ZWJ,
ZWNJ, soft hyphen, the bidi marks (Unicode ``Cf``) — are removed rather than
treated as boundaries, so a zero-width joiner cannot be dropped into the middle
of a word to slip it past the echo rule in an Indic or Arabic script.

**The comparison unit is deliberately not the index's.** SQLite's ``unicode61``
treats a Devanagari matra as a separator, so ``यात्रा`` shatters into ``य``,
``त``, ``र`` — three single consonants that collide with almost any other
Devanagari string. A drop rule built on that unit would emit no directive for
any belief written in an Indic script, which is a channel dropping a belief for
its script. So splitting here keeps marks attached to the letter they belong
to. ``half.text.words`` now splits identically, for its own reason — it hands
FTS5 whole words as phrases and lets FTS5 shatter them — and
``tests/test_scripts.py`` pins the two to the same output rather than merging
them, because they answer different questions and only one of them is allowed to
grow a growth ceiling, a cluster expansion, or anything else an index needs.
A *wording* check must not be answered by the terms an index happens to hold.
Folding is then ``half.text.normalize``, which casefolds and strips *non-spacing*
marks — so ``Café`` and ``cafe`` are one word, and so are ``ज़मीन`` and ``जमीन``,
because the nukta goes with the accents. Matras survive, which is what keeps
the word whole. The over-folding is safe in the only direction that matters: it
merges words that differ, so it drops more than it must and never less. The
index tokenizer is untouched — this is a second question (*does this echo the
claim's wording?*), not a second answer to the first one.

Pure and stdlib-only. No clock, no network, no ambient state: ``now`` is
injected and carried, so two builds over one ranked set are byte-identical
(AD-30).
"""

from __future__ import annotations

import unicodedata
from collections.abc import Iterable, Mapping, Sequence
from typing import Any, Final

from half.context.channels import (
    Content,
    Context,
    Directive,
    Item,
    License,
    Question,
    Topic,
)
from half.governance.ladder import Ceiling, permitted
from half.retrieval.port import Candidate, Ranked, RerankSource
from half.text import normalize

#: Which rung admits a belief to the quotable channel.
_QUOTABLE: Final[License] = License.ASSERT

#: Unicode categories that are neither a word character nor a word boundary:
#: format and control characters, surrogates, private use. Removed outright, so
#: that an invisible character can neither split a word nor join two.
_INVISIBLE: Final[frozenset[str]] = frozenset({"Cc", "Cf", "Co", "Cs"})

#: Belief fields a directive may name, most specific first. ``subject`` is
#: absent by design — see ``_topics``.
_LOOP: Final[str] = "loop"
_TOPICS: Final[str] = "topics"
_SUBJECT: Final[str] = "subject"


#: The one rung a question may be raised from.
#:
#: Named here rather than compared inline because ``bought_question`` and
#: ``tests/test_bought.py`` both read it, and because it is deliberately an
#: **equality** and not a floor: ``half.trust.unasked.may_be_raised`` permits
#: `ask` *or above*, which is the right rule for *may Half raise this*, and a
#: belief the ladder lifted to `assert` belongs in the content channel where Half
#: may simply say it. The gap between the two is real and cost a favour before
#: review found it — see ``bought_question``.
_ASKABLE: Final[License] = License.ASK


def bought_question(
    candidate_id: object, license_: License, *, bought: object
) -> bool:
    """Whether this candidate is the one question a favour paid for.

    **The predicate the builder and the tests both read**, rather than a
    condition each of them writes out. The first version of this rule lived only
    inside ``_item`` and was guarded in the tests by an AST scan for a branch
    naming ``bought`` — which ``if not bought: return Question(...)`` satisfies
    while doing the exact opposite, and which a ternary or a ``match`` would have
    made false-fail. A predicate can be swept exhaustively against an
    independently written expectation; a syntax scan can only ever be as clever
    as whoever wrote it.

    Two facts, and neither is inferred here. The rung is the ladder's answer,
    resolved under this main's ceiling one frame up. Whether a favour was spent
    is the trust package's, decided before the build and handed in. A belief the
    ladder does not put at `ask` is never a question however much was paid for
    it, and an `ask`-rung belief nobody paid for is never a question however
    clearly it looks like one.

    The rung is compared for **equality** with `ask`, not for reaching it. A
    belief at `assert` is one Half may state, so it belongs in the content
    channel; asking about something you are licensed to assert is not a question.
    That asymmetry against ``may_be_raised``'s *ask-or-above* is why a spend must
    never happen until the built context actually carries a question line.
    """
    if license_ is not _ASKABLE:
        return False
    paid = bought.strip() if isinstance(bought, str) else ""
    ident = candidate_id.strip() if isinstance(candidate_id, str) else ""
    return bool(paid) and paid == ident


def resolve(belief: Mapping[str, Any] | Any, *, ceiling: Ceiling | None) -> License:
    """The license this belief actually permits, resolved downward only.

    The one place a license becomes a decision, and therefore the one place the
    actor's global ceiling is applied (AD-28). ``ceiling`` is keyword-only and
    has **no default**: a caller that forgets it gets a ``TypeError`` rather
    than a belief resolved as though no cap existed, which is the bypass AD-28
    is written to prevent. ``None`` is the configured absence — a main with no
    ceiling set — and resolves to the belief's own license, never above it.

    This never raises whatever the belief looks like, and that is load-bearing
    rather than tidy: the only caller is on the turn's reply path, ahead of the
    append that records the main's message, so an exception here costs the main
    both their answer and their message — the belief is never written and the
    redelivery is suppressed by the idempotency check.

    This function is the door, not the rule set. Which rung a belief has earned
    is answered by ``half.governance.ladder.permitted``, and answered there
    only, so that it reads identically to whoever writes a license change and
    to whoever reads one.
    """
    return permitted(belief, ceiling=ceiling)


def split(
    ranked: Ranked | Iterable[Candidate] | None,
    *,
    now: str,
    ceiling: Ceiling | None,
    bought: str | None = None,
) -> tuple[Context, frozenset[str]]:
    """The context, **and the wordings it may not carry**, resolved once.

    ``build`` is this function with the second half of the answer thrown away,
    and it stays the whole of what every caller before story 13a needs. This
    exists because one caller now needs both: ``half.surface.morning`` hands the
    context to a generator and the withheld set to the tripwire that watches
    what comes back, and computing them separately meant resolving the ladder
    twice over the same material and passing the same ceiling to two functions
    by convention. Two entry points to one resolution is two chances for them to
    disagree about what was withheld — which, on this path, is two chances for
    the tripwire to be watching for the wrong words.

    Everything else — the split, the guard, the ordering, the bought question —
    is ``build``'s docstring, and it applies here unchanged.
    """
    licensed = tuple((c, resolve(c.belief, ceiling=ceiling)) for c in (ranked or ()))

    # Every wording the context may not carry, as adjacent pairs. `ask` sits
    # here beside `behave`: its material surfaces as a question about a topic,
    # and its text is withheld exactly as `behave` text is.
    hidden = _withheld_from(licensed)

    context = Context(
        now=now,
        truncated=bool(getattr(ranked, "truncated", False)),
        rerank=getattr(ranked, "rerank", RerankSource.ABSENT),
    )
    for candidate, license_ in licensed:
        item = _item(candidate, license_, bought=bought)
        if item is None:
            continue
        trial = context.plus(item)
        if leaks(trial.render(), hidden):
            continue  # this line would carry a withheld claim's wording
        context = trial
    return context, hidden


def build(
    ranked: Ranked | Iterable[Candidate] | None,
    *,
    now: str,
    ceiling: Ceiling | None,
    bought: str | None = None,
) -> Context:
    """Split ``ranked`` into the three channels, as of ``now``.

    ``bought`` is **the belief id a favour has already been spent on**, and it
    is the only way a question reaches a context (CAP-4, story 11).

    *The channel is bought by what this function is handed, never by what it
    filters.* A builder that read the rung and decided for itself which beliefs
    deserve a question can always be made to decide wrongly — and was: before
    story 11 every `ask`-rung belief became a ``Question`` and the morning
    surface put that line on the wire with no favour spent, which is CAP-4's
    central rule enforced in a package with no production caller. A builder that
    can only emit what it was handed cannot make that mistake, which is story
    10's AD-28 lesson (narrow the input, do not filter the output) applied to a
    second subsystem.

    **Singular, not a collection.** *"Never more than one question in a single
    send"* is asserted by the parameter's own type: there is no way to hand two
    in. See ``half.context.channels.Context.question``.

    **Defaulted, and empty is fail-closed** — which is why a default is
    permitted here at all, where ``resolve``'s ``ceiling`` is not. Forgetting
    ``ceiling`` would resolve a belief as though no cap existed, so its absence
    must be a ``TypeError``; forgetting ``bought`` asks nothing, which is a
    first-class outcome (AD-27). Every caller that existed before this story
    therefore emits no question at all, and a caller that wants one opts in.

    ``bought`` names a *belief*, not a question: what reaches a context is the
    belief's own topics, and the question's opaque id lives in the log
    (``half.questions.mint`` derives one from the other). A ``bought`` naming a
    belief that is not in ``ranked``, or one whose rung does not resolve to
    `ask` under this ceiling, emits no question — the ladder still decides what
    may be raised, and being paid for is not a permission.

    ``ceiling`` is this main's global cap (AD-28), handed down to every
    ``resolve`` in one place. Keyword-only and undefaulted, like ``resolve``'s:
    a scan that catches callers who forget it can only catch the spellings it
    thought of, and this story's own package re-exports made the uncaught
    spelling the natural one. ``None`` is still how a caller says *this main has
    no cap*; what it may not do is say it by omission.

    A capped belief is withheld exactly as an ordinary `behave` belief is: its
    wording joins the set no other line may echo, so lowering the ceiling
    cannot leak a claim sideways through somebody else's sentence.

    ``now`` is carried, not read: nothing under ``half/context/`` touches a
    clock, so the same ranked set and the same ``now`` build the same bytes.

    ``None`` and an empty ranked set both build an empty context. Neither is an
    error and neither is described anywhere as missing access — a main with
    nothing yet, and a main whose retrieval a crisis disabled, both still get a
    reply (AD-27, AD-24). ``Ranked``'s own annotations travel onto the context
    so that those cases stay tellable apart.

    Every candidate item is admitted by rendering the context it *would*
    produce and scanning that rendering. The guard therefore runs on the exact
    bytes the context will carry, in shipped code, and the returned context is
    the last one that passed it.

    Rank order is preserved within each channel. Nothing is re-sorted, so no
    collation — and therefore no locale — is involved in the ordering.
    """
    context, _ = split(ranked, now=now, ceiling=ceiling, bought=bought)
    return context


def withheld(
    ranked: Ranked | Iterable[Candidate] | None, *, ceiling: Ceiling | None
) -> frozenset[str]:
    """Every wording a context built from ``ranked`` may not carry.

    **Public because a second consumer arrived and a second implementation
    would be a Latin-only one.** ``half.voice.leak`` needs exactly this set to
    run its tripwire over generated text, and the rule it encodes — adjacent
    word pairs, over units that keep a Devanagari matra attached to its letter,
    folded by ``half.text.normalize``, with invisible characters removed — took
    two stories and a script sweep to get right. A copy of it beside the
    generator would have been a copy of whatever somebody remembered.

    Computed the same way ``build`` computes it, by calling the same helper over
    the same resolution, so the two cannot disagree about what is withheld.
    ``ceiling`` is keyword-only and undefaulted for ``resolve``'s reason: a
    caller that forgets it would compute the withheld set as though no cap
    existed, and a capped belief's wording must be withheld exactly as an
    ordinary `behave` belief's is.
    """
    return frozenset(
        _withheld_from(
            (c, resolve(c.belief, ceiling=ceiling)) for c in (ranked or ())
        )
    )


def _withheld_from(
    licensed: Iterable[tuple[Candidate, License]],
) -> frozenset[str]:
    """The wordings of everything in ``licensed`` that may not be quoted."""
    found: set[str] = set()
    for candidate, license_ in licensed:
        if license_ is not _QUOTABLE:
            found.update(fragments(candidate.claim))
    return frozenset(found)


def _item(
    candidate: Candidate, license_: License, *, bought: object
) -> Item | None:
    """The one channel item this candidate contributes, or nothing.

    **The question channel needs two facts and this function holds neither of
    them alone.** The rung is the ladder's answer, resolved under the ceiling
    one frame up; whether a favour was spent is the trust package's, decided
    before this call and handed in as ``bought``. Both are required, and neither
    is inferred here: a belief the ladder does not raise to `ask` is never a
    question however much was paid for it, and an `ask`-rung belief nobody paid
    for is never a question however clearly it looks like one.

    **An `ask`-rung belief nobody bought becomes a directive**, rather than
    disappearing. AD-18 names two failures and the second is the quiet one:
    filtering the material out entirely leaves Half blunt, unable to be gentle
    about what it may not name. Half may not *raise* an unbought claim; it may
    still act on it, which is what `behave` means and what a directive says.
    Its wording is withheld either way — an `ask` belief is not ``_QUOTABLE``,
    so its fragments are already in the withheld set.
    """
    if license_ is _QUOTABLE:
        return _content(candidate)
    topics = _topics(candidate)
    if topics is None:
        return None  # no structured topic, or one that echoes the claim
    # The rungs differ in what Half may do with the topic, never in how much of
    # the belief it was allowed to see — so they share every line above this.
    if bought_question(candidate.id, license_, bought=bought):
        return Question(id=candidate.id, topics=topics)
    return Directive(id=candidate.id, topics=topics)


# -- the content channel -----------------------------------------------------


def _content(candidate: Candidate) -> Content | None:
    """The quotable claim, or nothing.

    A belief licensed to be stated but carrying no claim text has nothing to
    contribute to this channel, and silently contributing nothing is the right
    answer — there is no degraded version of a quotation.
    """
    claim = candidate.claim
    if not isinstance(claim, str) or not claim.strip():
        return None
    item = Content(id=candidate.id, claim=claim)
    return item if item.claim else None


# -- the directive and question channels -------------------------------------


def _topics(candidate: Candidate) -> tuple[Topic, ...] | None:
    """This belief's structured topics, or ``None`` if no directive may be
    built from them.

    ``None`` covers both failure modes and they are deliberately the same
    outcome: a belief with no structured topic, and a belief every one of whose
    topics shares a word with its claim. In the first case there is nothing to
    say; in the second, saying it would be quoting. The belief still never
    leaks either way.

    **``subject`` is a last resort rather than a topic.** Every belief about
    the main carries ``subject="self"`` — the actor's turn writes it on every
    inbound message — so emitting it beside a loop says nothing a model can
    use, and, because the drop rule is per belief, any claim containing the
    word "self" would silently kill the whole directive including the loop that
    *was* worth naming. So subject is named only when the belief has no loop
    and no topics: better a weak directive than none, and never a weak one
    standing in the way of a strong one.
    """
    belief = candidate.belief
    if not isinstance(belief, Mapping):
        return None

    found = [
        *_named(belief.get(_LOOP), _LOOP),
        *_named(belief.get(_TOPICS), "topic"),
    ]
    if not found:
        found = _named(belief.get(_SUBJECT), _SUBJECT)
    found = _distinct(found)
    if not found:
        return None

    # Drop over degrade, and over the whole belief: one echoing topic kills the
    # directive rather than being edited out of it. Word-level here, because a
    # topic and the claim belong to the *same* belief — any word they share is
    # that claim's own wording being handed back.
    claim_words = frozenset(_units(candidate.claim))
    for topic in found:
        topic_words = frozenset(_units(topic.name))
        # A topic with no comparable words — an emoji, a bare numeral, a
        # punctuation slug — cannot echo any wording, so it is kept rather than
        # taking the belief's other, valid topics down with it.
        if topic_words and topic_words & claim_words:
            return None
    return tuple(found)


def _named(value: object, kind: str) -> list[Topic]:
    """Topics from one belief field, whatever ordered shape it arrived in.

    A bare string is accepted for the plural field as well as the singular
    ones: a log that wrote ``topics="travel"`` instead of ``topics=["travel"]``
    still names a topic, and silently discarding it can take the belief out of
    the context entirely — AD-18's second failure, arriving through a typo.

    Unordered shapes (a set, a generator) are *not* accepted. Their iteration
    order is not a property of the log, and a context whose directive order
    depends on hash seeding is not deterministic (AD-30).
    """
    values: Sequence[object]
    if isinstance(value, str):
        values = (value,)
    elif isinstance(value, (list, tuple)):
        values = value
    else:
        return []
    return [
        Topic(kind=kind, name=name)
        for item in values
        if isinstance(item, str) and (name := item.strip())
    ]


def _distinct(topics: Iterable[Topic]) -> list[Topic]:
    """``topics`` with repeats removed, first occurrence winning.

    Keyed on the folded name, so ``Café`` and ``cafe`` are one topic and a
    directive never reads ``subject: self; topic: self``. Order is the order
    they were found in, which is the order the log wrote them.
    """
    seen: set[str] = set()
    kept: list[Topic] = []
    for topic in topics:
        if not topic.name:
            continue
        key = "".join(_units(topic.name)) or topic.name
        if key in seen:
            continue
        seen.add(key)
        kept.append(topic)
    return kept


# -- the guard ---------------------------------------------------------------


def leaks(rendering: str, withheld: Iterable[str]) -> bool:
    """Whether any withheld wording survived into ``rendering``.

    Scanned line by line, which is the whole rendering and nothing but it:
    every character of a context appears on exactly one line, and no item's
    text can contain a line break (``half.context.channels.sanitize``). Going
    line by line rather than over the joined string avoids inventing adjacency
    that the rendering does not have — the last word of one directive is not
    next to the first word of the next one.
    """
    fragments = tuple(withheld)
    if not fragments:
        return False
    for line in rendering.split("\n"):
        haystack = "".join(_units(line))
        if any(fragment in haystack for fragment in fragments):
            return True
    return False


def fragments(text: object) -> tuple[str, ...]:
    """``text`` as the wordings that may not be repeated: its adjacent pairs.

    Pairs are sufficient for runs of every length — a shared run of five words
    contains four shared pairs — and they are the shortest unit that is wording
    rather than a topic.

    A claim that is a single word has no pair, so that word alone is its
    fragment: the whole claim must not appear even when the whole claim is one
    word. Concatenated without separators, because the comparison must hold for
    languages that do not space their words.
    """
    units = _units(text)
    if not units:
        return ()
    if len(units) == 1:
        return (units[0],)
    return tuple(first + second for first, second in zip(units, units[1:]))


def _units(text: object) -> list[str]:
    """``text`` as comparable words, in order.

    A word is a run of letters, digits and the marks that belong to them —
    matras, viramas, nuktas, combining accents — so that a Devanagari word
    stays one word rather than shattering into consonants. Invisible
    characters are removed rather than treated as boundaries, so neither
    splitting a word with a zero-width joiner nor joining two with one changes
    what is compared. Each word is then folded by ``half.text.normalize``,
    which casefolds and strips non-spacing marks: ``Café`` and ``cafe`` become
    one word, and so do ``ज़`` and ``ज``.

    Anything that is not a string yields nothing rather than raising: the log
    preserves fields this build does not recognise, and one odd value must not
    cost a main their turn.
    """
    if not isinstance(text, str):
        return []
    found: list[str] = []
    current: list[str] = []
    for char in text:
        category = unicodedata.category(char)
        if category in _INVISIBLE:
            continue
        if char.isalnum() or category.startswith("M"):
            current.append(char)
        elif current:
            found.append("".join(current))
            current = []
    if current:
        found.append("".join(current))
    return [folded for word in found if (folded := normalize(word))]
