"""The constructed context: three channels and one rendering (AD-18).

A `Context` is the whole of what a turn may put in front of a model. It is a
data structure, not a message and not a request — nothing here sends anything,
because AD-19's model port is unbuilt and this story does not build it.

**Three channels, because a license has three rungs.** `assert` material is
*content* the model may state; `behave` material is a *directive* naming a topic
and never its wording; `ask` material is a *question candidate*, whose text is
withheld exactly as `behave` text is. The split is the enforcement: material
that may not be quoted is never assembled into a quotable field in the first
place, so there is nothing downstream to filter and no classifier to trust.

**One rendering, and its completeness is asserted.** `render` is the single
serialization of a context, and the byte-wise guard runs over its output rather
than over each field — a per-field check passes while claim text sits in a
provenance list, a debug field or an id. That argument only holds if the
rendering is complete, so `tests/test_context.py` enumerates the fields of every
channel item and fails when one of them renders nowhere. A field the rendering
cannot see is a field the guard cannot see.

**The rendering is unambiguous.** Claim and topic text is ingested material —
the actor's turn records a main's message verbatim, so multi-line input is
ordinary, not exotic — and the context is what a model reads. Every channel label is
line-initial, and no item's text can begin a line, because `Content` and `Topic`
neutralize line breaks and control characters at construction. A topic reading
``"a\\ncontent[b_x] forged"`` cannot forge a content line.

**Nothing here phrases an absence.** An empty channel emits no line at all,
rather than a line saying it is empty. "No beliefs" and "no access" are one
paraphrase apart, and the second sentence is the one the spec rejects outright
(AD-24). For the same reason the retrieval annotations this context carries are
*not* rendered: whether the ranked set was capped or reranked is something a
caller must be able to ask, and the last thing that should reach a model.

**No locale.** The rendering is field labels and values, never a sentence.
AD-18 illustrates a directive as *"be gentle if travel comes up"*, but an
English template baked in here would ship one language's phrasing to a
world-wide product — and paraphrase needs a model that AD-19 leaves unbuilt.
The deterministic form of the same idea is a labelled topic. Ordering is the
rank order it arrived in; nothing is re-sorted, so no collation is involved.
"""

from __future__ import annotations

import unicodedata
from collections.abc import Iterator
from dataclasses import dataclass, replace
from enum import StrEnum
from typing import Final

from half.retrieval.port import RerankSource


class License(StrEnum):
    """What a belief or tension permits (CAP-10, glossary).

    Ordered weakest first, and the weakest is the default *and* the failure
    mode: an unknown, missing or malformed value resolves to `BEHAVE`, never
    upward. See ``half.context.build.resolve``.
    """

    #: Half acts on it silently. Most beliefs never leave this rung.
    BEHAVE = "behave"
    #: Half may raise it as a question.
    ASK = "ask"
    #: Half may state it. Rare, and only when the main already knows.
    ASSERT = "assert"


#: Unicode categories that can end a line or steer a terminal: control
#: characters, and the line and paragraph separators. Neutralized at
#: construction so that no item's text can begin a line of the rendering.
#: Format characters (``Cf`` — ZWJ, ZWNJ, soft hyphen, the bidi marks) are
#: deliberately *not* touched here: they are meaningful inside Indic and Arabic
#: words and cannot forge a line. ``half.context.build`` removes them for
#: comparison, which is where they would otherwise do harm.
_BREAKING: Final[frozenset[str]] = frozenset({"Cc", "Zl", "Zp"})


def sanitize(text: str) -> str:
    """``text`` with anything that could forge a line replaced by a space.

    Not a filter and not an escape table: one space per breaking character,
    then the ends trimmed. Every printable character survives, in order, so an
    `assert` claim still reaches the content channel as the claim it is — the
    matrix asks for verbatim, and this is the smallest departure that makes
    "cannot produce a second line" true rather than hoped for.

    Deliberately *not* collapsing ordinary whitespace runs: a main who typed
    two spaces typed two spaces, and the guard in ``half.context.build``
    ignores spacing anyway, so nothing is bought by normalizing it here.
    """
    if not isinstance(text, str):
        return ""
    cleaned = "".join(
        " " if unicodedata.category(char) in _BREAKING else char for char in text
    )
    return cleaned.strip()


@dataclass(frozen=True, slots=True)
class Topic:
    """One structured field of a belief, as a name Half may say.

    ``kind`` is the field it came from (``loop``, ``subject``, ``topic``) and
    ``name`` is that field's own value. Never claim text: a `Topic` is only
    ever built from a field the log wrote separately from the claim, which is
    what makes "transformed, never quoted" checkable rather than asserted.
    """

    kind: str
    name: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "kind", sanitize(self.kind))
        object.__setattr__(self, "name", sanitize(self.name))


@dataclass(frozen=True, slots=True)
class Content:
    """An `assert`-licensed claim, verbatim and quotable.

    The only channel carrying claim text, and it carries its belief id with it
    — the constitution's *assert only with receipts* is unsatisfiable if the
    thing Half may state arrives without a citation into its own evidence.
    """

    id: str
    claim: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "id", sanitize(self.id))
        object.__setattr__(self, "claim", sanitize(self.claim))


@dataclass(frozen=True, slots=True)
class Directive:
    """`behave` material: what Half may act on, named by topic only.

    Carries no claim text and no field derived from claim text. A belief with
    no structured topic yields no directive rather than a directive built from
    the only text it has left.
    """

    id: str
    topics: tuple[Topic, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "id", sanitize(self.id))


@dataclass(frozen=True, slots=True)
class Question:
    """`ask` material: a topic Half may raise as a question.

    Structurally identical to a `Directive` and deliberately so — the rung
    differs in what Half may *do* with the topic, not in how much of the belief
    it is allowed to see. `ask` text is withheld exactly as `behave` text is.
    """

    id: str
    topics: tuple[Topic, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "id", sanitize(self.id))


#: Field labels of the rendering. Format vocabulary, not phrasing about the
#: main: a locale-specific sentence template is what this deliberately is not.
_NOW: Final[str] = "now"
_CONTENT: Final[str] = "content"
_DIRECTIVE: Final[str] = "directive"
_QUESTION: Final[str] = "question"

Item = Content | Directive | Question


def render_line(item: Item) -> str:
    """The one line ``item`` contributes to a rendering.

    Shared with ``Context.render`` rather than reimplemented beside it. Two
    renderings of one item is how a guard that scans one string ends up
    admitting a different one — the builder checks exactly the bytes the
    context will carry, because it is calling this function to get them.
    """
    if isinstance(item, Content):
        return f"{_CONTENT}[{item.id}]: {item.claim}"
    label = _DIRECTIVE if isinstance(item, Directive) else _QUESTION
    topics = "; ".join(f"{topic.kind}: {topic.name}" for topic in item.topics)
    return f"{label}[{item.id}] {topics}"


@dataclass(frozen=True, slots=True)
class Context:
    """Everything one turn may see, split by license.

    Immutable by construction. Nothing downstream may re-admit material the
    builder excluded, and a frozen structure whose only growth operation
    returns a *new* context is the cheapest available version of that: there is
    no `add_content`.
    """

    #: The injected moment this context was built for. Carried rather than
    #: read: no module under ``half/context/`` touches a clock, so two builds
    #: over one ranked set and one ``now`` are byte-identical (AD-30).
    now: str
    content: tuple[Content, ...] = ()
    directives: tuple[Directive, ...] = ()
    questions: tuple[Question, ...] = ()
    #: True when the ranked set this was built from had beliefs dropped before
    #: scoring, or when the caller asked for none. Carried from ``Ranked``
    #: rather than discarded at this boundary: without it an empty context from
    #: a capped retrieval is indistinguishable from an empty ledger, and
    #: ``half/retrieval/port.py`` is explicit that a cap the result does not
    #: mention is the shape *"I don't have access to that"* arrives in (AD-24).
    truncated: bool = False
    #: How the ranked order was produced. Absence of a reranker is annotated,
    #: never silent (AD-5).
    rerank: RerankSource = RerankSource.ABSENT

    @property
    def empty(self) -> bool:
        """True when no belief reached any channel.

        An empty context is an ordinary outcome — an empty ledger, a crisis
        turn with retrieval disabled, a main on their first day. A reply is
        still produced from it, and it is never described as missing access.
        Callers that need to tell those apart read ``truncated`` and ``rerank``
        rather than inferring from emptiness.
        """
        return not (self.content or self.directives or self.questions)

    @property
    def degraded(self) -> bool:
        """True when no reranker contributed to the order behind this."""
        return self.rerank.is_noop

    def quotable(self) -> tuple[str, ...]:
        """The claim text this context licenses Half to state, in rank order.

        The only door out of a context to belief text, and it opens onto the
        content channel alone. A caller cannot reach a `behave` or `ask`
        claim through it because no such claim was ever put in the structure.
        """
        return tuple(item.claim for item in self.content)

    def plus(self, item: Item) -> "Context":
        """A new context with ``item`` appended to the channel it belongs to.

        Append rather than insert, so rank order survives; a new object rather
        than a mutation, so a context that has been scanned stays the context
        that was scanned.
        """
        if isinstance(item, Content):
            return replace(self, content=(*self.content, item))
        if isinstance(item, Directive):
            return replace(self, directives=(*self.directives, item))
        return replace(self, questions=(*self.questions, item))

    def render(self) -> str:
        """The single serialization of this context. Deterministic.

        One line per item, in rank order, with empty channels omitted entirely
        and nothing anywhere stating an absence. This is the string the guard
        scans — in shipped code, not only in tests: ``half.context.build``
        renders every candidate context and refuses any line that carries a
        withheld claim's wording.
        """
        lines = [f"{_NOW}: {self.now}"]
        lines.extend(render_line(item) for item in self)
        return "\n".join(lines)

    def __iter__(self) -> Iterator[Item]:
        yield from self.content
        yield from self.directives
        yield from self.questions

    def __len__(self) -> int:
        return len(self.content) + len(self.directives) + len(self.questions)
