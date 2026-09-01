"""CAP-12 story 6c: the safety plan Half holds and must never write.

Three rows of the matrix, and the third is the one that matters:

**Produced verbatim on request** — every line the clinician wrote, in their
order, with nothing added and nothing dropped, asserted segment by segment
rather than by looking at a rendering.

**Said plainly when there is none** — and never repaired into one. Half offers
nothing invented, and it does not say it holds nothing when it holds something
it cannot show, because a lie at three in the morning is the failure this whole
subsystem is built around.

**Structurally impossible to author** — *not a filter*. What is asserted is not
that the code does not write a plan but that there is nothing here that could:
one writer of the field in the whole tree, and that writer is a copy of its
only argument. Steps three and four of the Stanley–Brown plan are literally
Half's own data, which is what makes authoring feel one field away, so the
guarantee is a property of the files rather than a rule about them.

**A green run here is not clinical review.** Build requirement 6 is a qualified
reviewer before launch, and that covers the boundary this file draws as much as
the wording either side of it.
"""

from __future__ import annotations

import ast
import asyncio
from pathlib import Path

import pytest

from half.actor.registry import ActorRegistry
from half.actor.runtime import Runtime
from half.channel.telegram import TelegramChannel
from half.crisis import respond, rows, safetyplan, signals, templates
from half.crisis.safetyplan import Holder, SafetyPlan, held_fields
from half.governance import ladder
from half.store.ops import Op
from half.store.store import Store
from tests.conftest import FakeTransport, msg, seed_belief

pytestmark = [pytest.mark.cap12, pytest.mark.cap12_aftercare]

ROOT = Path(__file__).resolve().parents[1]
AT = 1_788_256_800   # 2026-09-01T10:00:00Z

#: A plan as a professional would have written one, in the main's own words.
#: Deliberately not six tidy headed sections: Half holds what it was given, and
#: a fixture that looked like a form would be testing a shape this build must
#: not know.
LINES = (
    "When I start pacing at two in the morning, that is the sign.",
    "Put the phone in the other room and open the window.",
    "Ring Asha. She knows and she does not mind being woken.",
    "Dr Rao — Tuesdays, and the practice takes messages.",
)

ASK_FOR_IT = "can you show me my safety plan"


def store_with(tmp_path, *, lines=LINES, quarantine=None, ident="p_1"):
    root = tmp_path / "mains"
    with Store(root / "vidit") as store:
        if lines is not None:
            store.record(Op.ASSERT, ident, "2026-08-01T00:00Z",
                         **held_fields(list(lines)))
        if quarantine is not None:
            record = store.state().beliefs[ident]
            candidate = ladder.quarantine_candidate(record, reason=quarantine)
            store.record(Op.ASSERT, ident, "2026-08-02T00:00Z",
                         **ladder.quarantine(record, candidate=candidate,
                                             answered=True))
    return root


def drive(registry, turns, *, mains=None):
    replies: list[str | None] = []
    for index, (text, at) in enumerate(turns):
        transport = FakeTransport([
            msg(text=text, message_id=f"m{index}", chat_id="123", date=at)
        ])
        channel = TelegramChannel(
            transport=transport, mains=mains or {"123": "vidit"}
        )
        asyncio.run(Runtime(channel=channel, registry=registry).run())
        replies.append(transport.sent[-1][1] if transport.sent else None)
    return replies


def holder_over(root) -> Holder:
    return Holder(held=ActorRegistry(root))


# =============================================================================
# matrix: a plan is held
# =============================================================================


def test_a_held_plan_is_reproduced_word_for_word(tmp_path):
    """Matrix: safety plan held. *Produced verbatim on request.*"""
    said = holder_over(store_with(tmp_path)).produce("vidit")
    for line in LINES:
        assert line in said, line


def test_the_lines_come_back_in_the_order_they_were_written(tmp_path):
    """A plan is a sequence. Reordering it is editing it, and step six is not
    interchangeable with step one."""
    said = holder_over(store_with(tmp_path)).produce("vidit")
    positions = [said.index(line) for line in LINES]
    assert positions == sorted(positions)


def test_nothing_is_added_to_a_plan(tmp_path):
    """*No step invented.* Every segment of the reply is either a paragraph
    from the reviewed corpus or one of this plan's own lines — asserted over
    the segments rather than by reading the rendering, and split the way the
    renderer joins."""
    plan = SafetyPlan(id="p_1", lines=LINES)
    said = safetyplan.render(plan)
    allowed = set(templates.TEXTS) | set(LINES)
    for segment in rows.segments(said):
        assert segment in allowed, f"a segment nobody wrote: {segment!r}"


def test_no_line_of_the_plan_is_dropped(tmp_path):
    """The other half of *nothing added*: nothing left out either. A plan
    produced with a section missing is worse than one not produced, because the
    missing section is the one nobody notices is missing."""
    plan = SafetyPlan(id="p_1", lines=LINES)
    segments = rows.segments(safetyplan.render(plan))
    assert [s for s in segments if s in LINES] == list(LINES)


@pytest.mark.cap12_aftercare_property
def test_a_plan_line_is_rendered_as_itself_and_nothing_else():
    """The pinned format, pinned against a literal. A bullet, a number, a
    heading or a *"step three:"* is a word Half added to a clinical document,
    and the guard compares against this function rather than the renderer."""
    assert safetyplan.line("Ring Asha.") == "Ring Asha."


@pytest.mark.cap12_aftercare_property
def test_the_guard_refuses_a_rendering_that_grew_a_clause():
    """Non-vacuity for the closed-set check, written as the bypass the
    handoff's guard actually had: a renderer that appended something would ship
    blessed if the guard recomputed its input through the renderer."""
    plan = SafetyPlan(id="p_1", lines=LINES)
    said = safetyplan.render(plan)
    assert safetyplan.is_plan_templated(said, plan)
    assert not safetyplan.is_plan_templated(
        said + rows.ROW + "I would start with the second one.", plan
    )


def test_a_plan_is_produced_inside_the_mode_after_the_opener(tmp_path):
    """The point of holding one at all: a safety plan in a drawer is useless at
    three in the morning. The opener still comes first — the plan is appended
    to the reply, never instead of it."""
    root = store_with(tmp_path)
    registry = ActorRegistry(root)
    replies = drive(registry, [
        ("i want to kill myself", AT),
        (ASK_FOR_IT, AT + 60),
    ])
    registry.close()

    reply = replies[1]
    assert reply.index(templates.OPEN_HELD.text) < reply.index(
        templates.PLAN_OPEN.text
    ), "the plan arrived before the words"
    for line in LINES:
        assert line in reply


def test_producing_a_plan_writes_nothing_and_enters_nothing(tmp_path):
    """A request is a request. It records no belief, moves no ceiling, and
    neither enters nor exits the mode."""
    root = store_with(tmp_path)
    registry = ActorRegistry(root)
    drive(registry, [(ASK_FOR_IT, AT)])
    registry.close()

    ops = [r.op for r in Store(root / "vidit").log]
    assert Op.CRISIS not in ops
    assert Op.CEILING not in ops


@pytest.mark.cap12_aftercare_property
def test_a_quarantined_plan_is_not_produced(tmp_path):
    """A pin is the main saying leave this alone, and it is permanent. The
    equivalent mistake in story 6b offered a quarantined contact as a crisis
    door with a prefilled draft."""
    root = store_with(tmp_path, quarantine="the main asked me to drop it")
    said = holder_over(root).produce("vidit")
    assert said == templates.PLAN_ABSENT.text
    for line in LINES:
        assert line not in said


def test_the_newest_plan_is_the_one_produced(tmp_path):
    """A main whose clinician gave them a new plan has a new plan. Producing
    the older one would be producing a document that was replaced — and
    merging the two would be authoring a third."""
    root = tmp_path / "mains"
    with Store(root / "vidit") as store:
        store.record(Op.ASSERT, "p_1", "2026-06-01T00:00Z",
                     **held_fields(["the old plan"]))
        store.record(Op.ASSERT, "p_2", "2026-08-01T00:00Z",
                     **held_fields(["the new plan"]))
    said = holder_over(root).produce("vidit")
    assert "the new plan" in said and "the old plan" not in said


# =============================================================================
# matrix: no plan is held
# =============================================================================


def test_a_main_with_no_plan_is_told_plainly(tmp_path):
    """Matrix: safety plan absent. *Half says so plainly and offers nothing
    invented.*"""
    root = tmp_path / "mains"
    (root / "vidit").mkdir(parents=True)
    said = holder_over(root).produce("vidit")
    assert said == templates.PLAN_ABSENT.text
    assert respond.is_templated(said)


@pytest.mark.cap12_aftercare_property
def test_the_absent_sentence_offers_nothing_invented():
    """Nothing improvised. The sentence names no warning sign, no coping
    strategy, no contact and no professional — it says what Half holds and what
    Half will not write, and stops."""
    said = templates.PLAN_ABSENT.text.casefold()
    for invented in ("you could try", "here is one", "start with",
                     "in the meantime", "why not", "a good first step",
                     "write down", "make a list"):
        assert invented not in said, invented


@pytest.mark.cap12_aftercare_property
def test_an_unwired_holder_says_it_holds_nothing():
    """A Half with no store is a Half holding no plan, and saying so is true.
    A holder that failed loudly when unwired would cost somebody their reply on
    the day it was half-deployed."""
    assert Holder().produce("vidit") == templates.PLAN_ABSENT.text


@pytest.mark.cap12_aftercare_property
def test_a_store_failure_never_claims_there_is_no_plan():
    """The lie this distinction exists to prevent. *"I am not holding a plan
    for you"* said to somebody whose plan Half is holding and cannot read is
    worse than any of the three honest answers."""
    class Exploding:
        def safetyplan_records(self, main_id):
            raise OSError("the disk is gone")

    said = Holder(held=Exploding()).produce("vidit")
    assert said == templates.PLAN_UNREADABLE.text
    assert said != templates.PLAN_ABSENT.text


@pytest.mark.parametrize(
    "line",
    ["a step\nand a second line", "a step\twith a tab", "a step\u2028and a hidden one",
     "x" * (safetyplan.MAX_LINE + 1), "   "],
    ids=["newline", "tab", "line-separator", "too-long", "blank"],
)
def test_a_line_that_cannot_be_shown_withholds_the_whole_plan(line):
    """Whole or not at all. Dropping the offending line would produce a plan
    with a section missing under a clinician's authority; repairing it would
    render a guess in front of somebody in crisis."""
    plan = SafetyPlan(id="p_1", lines=(LINES[0], line, LINES[1]))
    assert safetyplan.render(plan) is None
    assert Holder(held=_Records([{"id": "p_1", "plan": list(plan.lines)}])).produce(
        "vidit"
    ) == templates.PLAN_UNREADABLE.text


@pytest.mark.cap12_aftercare_property
def test_a_plan_line_may_hold_an_em_dash_and_an_option_row_may_not():
    """The split story 6c makes in ``half.crisis.rows``, asserted in both
    directions. A row's separators are refused in a value *joined into* a row,
    because the guard reads a row back apart; a plan line is joined into
    nothing, and withholding somebody's whole safety plan over a dash in a
    clinician's sentence would be this module's strictness turned against the
    person it protects.
    """
    dashed = "Dr Rao — Tuesdays."
    assert rows.one_line(dashed, limit=rows.MAX_LABEL) == dashed
    assert rows.plain(dashed, limit=rows.MAX_LABEL) is None
    for hostile in ("a step\nand another", "a step\twith a tab", "  "):
        assert rows.one_line(hostile, limit=rows.MAX_LABEL) is None, hostile


def test_a_plan_longer_than_a_plan_is_withheld():
    """Past the ceiling it is not a safety plan, and there is no honest way to
    show part of one."""
    plan = SafetyPlan(id="p_1", lines=tuple(f"step {n}" for n in range(200)))
    assert safetyplan.render(plan) is None


class _Records:
    """A store stub holding exactly the records it was given."""

    def __init__(self, records):
        self._records = records

    def safetyplan_records(self, main_id):
        return self._records


# =============================================================================
# matrix: authoring a plan
# =============================================================================


def _plan_writers() -> list[str]:
    """Every place in ``half/`` that puts a value into the plan field.

    Three spellings, because one is not enough: a keyword argument to an
    append, a dict literal key, and an assignment into a mapping. The ladder's
    writer gate had exactly this shape for the license field, and for the same
    reason — read-side enforcement alone leaves the field something anyone can
    set, at the price of finding a second spelling.
    """
    #: ``safetyplan.py`` is the single writer. ``store/records.py`` owns the
    #: field's *name* and its type validation and writes no value.
    allowed = {"half/crisis/safetyplan.py", "half/store/records.py"}
    found: list[str] = []
    for path in sorted((ROOT / "half").rglob("*.py")):
        relative = str(path.relative_to(ROOT))
        if relative in allowed:
            continue
        found += _plan_writes_in(path, relative)
    return found


def _plan_writes_in(path: Path, relative: str) -> list[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    found: list[str] = []

    def names(node) -> bool:
        return (
            isinstance(node, ast.Constant) and node.value == "plan"
        ) or (isinstance(node, ast.Name) and node.id == "PLAN")

    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            for keyword in node.keywords:
                if keyword.arg == "plan":
                    found.append(f"{relative}:{node.lineno} plan=")
        elif isinstance(node, ast.Dict):
            for key in node.keys:
                if key is not None and names(key):
                    found.append(f"{relative}:{node.lineno} dict key")
        elif isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Subscript) and names(target.slice):
                    found.append(f"{relative}:{node.lineno} assignment")
    return found


@pytest.mark.cap12_aftercare_property
def test_only_one_function_in_the_tree_can_write_a_plan():
    """Matrix: plan authoring. *Structurally impossible, not a filter.*

    Half may hold a document somebody else wrote. It may not produce one, and
    the guarantee is that there is exactly one expression in the codebase that
    puts a value into the plan field — a copy of its only argument.
    """
    assert not _plan_writers(), (
        f"a second writer of the plan field: {_plan_writers()}"
    )


@pytest.mark.cap12_aftercare_property
def test_the_writer_gate_catches_the_bypass_it_exists_for(tmp_path):
    """Non-vacuity, run through the same scan rather than a walker written
    again here."""
    bypass = tmp_path / "bypass.py"
    bypass.write_text(
        "def compose(store, warning_signs):\n"
        "    store.record(op, ident, t, plan=['step one'] + warning_signs)\n"
        "    fields = {'plan': ['step two']}\n"
        "    fields[PLAN] = ['step three']\n",
        encoding="utf-8",
    )
    found = _plan_writes_in(bypass, "bypass.py")
    assert len(found) == 3, found


@pytest.mark.cap12_aftercare_property
def test_the_one_writer_is_a_copy_of_its_only_argument():
    """It cannot add a step, fill a gap, reorder, retitle or summarise, because
    there is nothing for it to do any of that *from*: one argument, and the
    output is it."""
    import inspect

    assert list(inspect.signature(held_fields).parameters) == ["lines"]
    for given in (["a"], list(LINES), ["  spaced  "], ["one", "two", "three"]):
        assert held_fields(given)["plan"] == given


@pytest.mark.cap12_aftercare_property
def test_the_one_writer_refuses_what_it_could_never_show():
    """The size and shape limits belong at the append, not at the render. The
    log is append-only, so a plan too long or with a line that cannot be shown
    would otherwise be stored permanently and be permanently unproducible —
    answered for ever with *"I cannot get to a safety plan for you right now"*
    over a document the main can see is there."""
    with pytest.raises(ValueError):
        held_fields(["x" * (safetyplan.MAX_LINE + 1)])
    with pytest.raises(ValueError):
        held_fields(["a step\nand a second line"])
    with pytest.raises(ValueError):
        held_fields([f"step {n}" for n in range(safetyplan.MAX_LINES + 1)])


@pytest.mark.cap12_aftercare_property
def test_the_one_writer_refuses_an_empty_plan():
    """*"Half holds a plan with no steps in it"* is a state whose only honest
    rendering is the absent sentence, and having two ways to be absent is how
    one of them stops being checked."""
    with pytest.raises(ValueError):
        held_fields([])
    with pytest.raises(TypeError):
        held_fields("a plan is not a string")


@pytest.mark.cap12_aftercare_property
def test_the_module_does_not_know_the_shape_of_a_safety_plan():
    """The subtlest authoring surface there is. A module that knew the six
    Stanley–Brown sections could notice one missing and offer to fill it, and
    the offer would be clinical work done by software at three in the morning.

    So the section names appear nowhere: there is no template of a plan for a
    gap to be measured against.
    """
    for relative in _package_modules():
        literals = _speakable_literals(ROOT / relative)
        for section in ("warning sign", "coping strateg", "social contact",
                        "distraction", "professional and agenc", "lethal means",
                        "restricting access", "reasons for living"):
            assert section not in literals, (
                f"{relative} names a section of a safety plan: {section!r}"
            )


@pytest.mark.cap12_aftercare_property
def test_no_template_in_the_corpus_is_a_step_of_a_plan():
    """The same rule one file over. The four plan templates are a *frame* — the
    paragraphs either side of somebody else's document — and none of them is a
    step, a heading or a prompt for a missing one."""
    for line in (templates.PLAN_OPEN, templates.PLAN_CLOSE,
                 templates.PLAN_ABSENT, templates.PLAN_UNREADABLE):
        lowered = line.text.casefold()
        for shape in ("step one", "step 1", "first,", "warning sign",
                      "coping", "distraction", "lethal"):
            assert shape not in lowered, f"{line.id}: {shape!r}"


@pytest.mark.cap12_aftercare_property
def test_the_plan_templates_are_in_the_reviewed_corpus():
    for line in (templates.PLAN_OPEN, templates.PLAN_CLOSE,
                 templates.PLAN_ABSENT, templates.PLAN_UNREADABLE):
        assert line in templates.LINES


@pytest.mark.cap12_aftercare_property
def test_half_says_out_loud_that_writing_one_is_not_its_job():
    """The absent sentence is the one place a main is told where the boundary
    is. If it stopped saying so, Half would look like something that had simply
    not got round to it."""
    lowered = templates.PLAN_ABSENT.text.casefold()
    assert "clinical" in lowered
    assert "not mine to do" in lowered


# =============================================================================
# reaching the plan is not reaching the ledger
# =============================================================================


@pytest.mark.cap12_aftercare_property
def test_the_crisis_path_sees_the_plan_and_never_the_claim_beside_it(tmp_path):
    """Crisis mode hard-disables ledger retrieval, so producing a held plan
    must not become the route by which the ledger comes back. Narrowing by
    *record* was not narrowing — a belief carrying both a plan and a claim is
    the most ordinary shape there is once a document is also a subject."""
    root = tmp_path / "mains"
    with Store(root / "vidit") as store:
        seed_belief(store, "p_1", "2026-08-01T00:00Z",
                    claim="has not flown a paraglider in three years",
                    subject="self", **held_fields(["Ring Asha."]))
    registry = ActorRegistry(root)
    records = registry.safetyplan_records("vidit")
    registry.close()

    assert records and "plan" in records[0]
    assert "claim" not in records[0], "a claim about the main left the store"
    assert "subject" not in records[0]


@pytest.mark.cap12_aftercare_property
def test_a_belief_without_a_plan_is_invisible_to_this_path(tmp_path):
    root = tmp_path / "mains"
    with Store(root / "vidit") as store:
        seed_belief(store, "b_1", "2026-08-01T00:00Z", claim="ordinary",
                    subject="self")
    registry = ActorRegistry(root)
    assert registry.safetyplan_records("vidit") == ()
    registry.close()


# =============================================================================
# asking for it
# =============================================================================


@pytest.mark.parametrize(
    "text",
    ["can you show me my safety plan", "what does my safety plan say",
     "safety plan", "read me the plan we made", "my crisis plan please",
     "the plan my therapist and i wrote"],
)
def test_a_request_for_the_plan_is_recognised(text):
    assert signals.is_plan_request(text)


@pytest.mark.parametrize(
    "text",
    ["my plan for the weekend", "the plan is to leave at six",
     "we have a plan for the quarter", "any plans tonight",
     "i planned the whole thing badly"],
)
def test_an_ordinary_plan_is_not_a_safety_plan(text):
    """Tight on purpose. Answering *"my plan for the weekend"* with a safety
    plan would be Half deciding what somebody meant at the worst possible
    moment."""
    assert not signals.is_plan_request(text)


@pytest.mark.cap12_aftercare_property
def test_asking_for_a_plan_is_not_a_crisis_signal():
    """It produces no tier, so it enters no mode, caps nothing and records
    nothing. Continuing care is not an emergency."""
    assert not signals.assess(ASK_FOR_IT).enters
    assert not signals.assess(ASK_FOR_IT).asks


@pytest.mark.cap12_aftercare_property
def test_the_plan_is_never_gated_by_tier(tmp_path):
    """Never gated, ever — and there is no value to branch on: nothing on this
    path reads a plan, a subscription or a payment state."""
    forbidden = {"subscription", "paid", "premium", "billing",
                 "entitlement", "quota", "is_paid", "plan_id"}
    for relative in _package_modules():
        tree = ast.parse((ROOT / relative).read_text(encoding="utf-8"))
        seen = {
            node.attr.casefold() for node in ast.walk(tree)
            if isinstance(node, ast.Attribute)
        } | {
            node.value.casefold() for node in ast.walk(tree)
            if isinstance(node, ast.Constant) and isinstance(node.value, str)
        }
        assert not seen & forbidden, f"{relative}: {sorted(seen & forbidden)}"


# =============================================================================
# review round 1: the guard has to catch the property, not the spelling
# =============================================================================


def _package_modules() -> list[str]:
    """Every module under ``half/``, globbed.

    **Globbed, never listed**, which is the widening story 6b's send-path scan
    needed one story earlier. The section-name and no-tier scans each read one
    hardcoded filename, so a module written next year — or a second writer
    added inside the one file the writer gate exempts — was scanned by nothing.
    """
    return sorted(
        str(path.relative_to(ROOT)) for path in (ROOT / "half").rglob("*.py")
        if path.stat().st_size
    )


def _speakable_literals(path: Path) -> str:
    """Every string literal in ``path`` that is not a docstring, folded.

    Docstrings are excluded, and only docstrings. A module may *explain* why
    steps three and four are the temptation — that is the reasoning a reviewer
    needs — and prose in a docstring is not a value a renderer can emit. What
    must not exist is a section name the code could put in front of a main.
    """
    tree = ast.parse(path.read_text(encoding="utf-8"))
    documented = {
        id(node.body[0].value) for node in ast.walk(tree)
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef,
                             ast.AsyncFunctionDef))
        and node.body and isinstance(node.body[0], ast.Expr)
        and isinstance(node.body[0].value, ast.Constant)
        and isinstance(node.body[0].value.value, str)
    }
    return " ".join(
        node.value.casefold() for node in ast.walk(tree)
        if isinstance(node, ast.Constant) and isinstance(node.value, str)
        and id(node) not in documented
    )


@pytest.mark.cap12_aftercare_property
def test_the_package_scans_have_modules_to_scan():
    """A glob that matched nothing would make every scan above and below pass
    having read no code at all."""
    modules = _package_modules()
    assert len(modules) >= 20, modules
    assert "half/crisis/safetyplan.py" in modules


#: An argument that was *given* to the caller rather than built by it. A name,
#: an attribute, a call to something that reads a message the main sent — the
#: value came from outside. A comprehension, an f-string, a concatenation or a
#: literal is a value the caller composed, and a plan Half composed is the one
#: thing this story exists to make impossible.
def _locally_built(node: ast.AST) -> bool:
    return isinstance(node, (ast.ListComp, ast.SetComp, ast.GeneratorExp,
                             ast.DictComp, ast.JoinedStr, ast.BinOp,
                             ast.List, ast.Tuple, ast.Dict, ast.Constant,
                             ast.IfExp))


def _composed_names(scope: ast.AST) -> set[str]:
    """Names that ``scope`` builds a value into, rather than receives.

    A name assigned from a comprehension, an f-string, a concatenation or a
    literal is a value this function made. So is one appended to or extended.
    Passing such a name to the writer is composing a plan and handing it over,
    which is the exact shape review found: the argument is a bare ``Name`` and
    every shape check on the argument alone waves it through.
    """
    built: set[str] = set()
    for node in ast.walk(scope):
        if isinstance(node, ast.Assign) and _locally_built(node.value):
            built |= {t.id for t in node.targets if isinstance(t, ast.Name)}
        elif isinstance(node, ast.AnnAssign) and node.value is not None:
            if _locally_built(node.value) and isinstance(node.target, ast.Name):
                built.add(node.target.id)
        elif isinstance(node, ast.AugAssign) and isinstance(node.target, ast.Name):
            built.add(node.target.id)
        elif isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
            if node.func.attr in {"append", "extend", "insert"} and isinstance(
                node.func.value, ast.Name
            ):
                built.add(node.func.value.id)
    return built


def _plan_writer_call_sites() -> list[str]:
    """Every call of ``held_fields`` under ``half/`` handed a composed plan.

    Composed means: built on the spot, or built into a local name and then
    passed. Both, because the first version checked the argument's shape alone
    and a comprehension assigned to ``lines`` two lines above sailed through
    it — which is precisely how the reproduction was written.

    **Honest about its limits.** A plan built in one function, returned, and
    passed to the writer by another still evades this, as would one assembled
    through a helper. No static check closes that; what closes it is that the
    one production caller hands over a value it read off the main's own
    message, and that call site is asserted below by name.
    """
    offenders: list[str] = []
    for relative in _package_modules():
        tree = ast.parse((ROOT / relative).read_text(encoding="utf-8"))
        scopes = [
            node for node in ast.walk(tree)
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Module))
        ]
        for scope in scopes:
            built = _composed_names(scope)
            for node in ast.walk(scope):
                if not isinstance(node, ast.Call):
                    continue
                name = (
                    node.func.attr if isinstance(node.func, ast.Attribute)
                    else node.func.id if isinstance(node.func, ast.Name) else ""
                )
                if name != "held_fields":
                    continue
                given = node.args[0] if node.args else None
                composed = given is None or _locally_built(given) or (
                    isinstance(given, ast.Name) and given.id in built
                )
                if composed:
                    offenders.append(f"{relative}:{node.lineno}")
    return sorted(set(offenders))


@pytest.mark.cap12_aftercare_property
def test_no_module_hands_the_writer_a_plan_it_composed_itself():
    """Matrix: plan authoring, any spelling. *The property, not the spelling.*

    The reproduction this exists for: a module with

        def compose(warning_signs, contacts, clinician):
            lines = [f"Warning sign: {s}" for s in warning_signs]
            lines += [f"Call {c.name}" for c in contacts]
            return held_fields(lines)

    built a safety plan out of Half's **own ledger**, handed it to the blessed
    writer, and left the whole suite green — after which ``Holder.produce``
    read it back under a paragraph saying none of it was Half's. The writer
    gate counted three ways of *writing the field* and said nothing about where
    the content came from, which is the same failure shape as the send-path
    scan a story earlier: the spelling, not the property.

    So this checks the argument. A value that was passed in is a plan Half was
    given; a comprehension, an f-string or a concatenation is a plan Half made.
    """
    assert not _plan_writer_call_sites(), (
        f"a plan was composed and handed to the writer: {_plan_writer_call_sites()}"
    )


@pytest.mark.cap12_aftercare_property
def test_the_call_site_gate_catches_the_bypass_it_exists_for(tmp_path):
    """Non-vacuity, written as the exact module review used — including the
    spelling the first version of this gate missed, where the comprehension is
    assigned to a name and the *name* is passed."""
    bypass = tmp_path / "planner.py"
    bypass.write_text(
        "from half.crisis.safetyplan import held_fields\n"
        "\n"
        "def compose(signs, people, doctor):\n"
        "    lines = [f'{s}' for s in signs]\n"
        "    lines += [f'Ring {p}.' for p in people]\n"
        "    return held_fields(lines)\n"
        "\n"
        "def other(signs):\n"
        "    return held_fields(['a'] + list(signs))\n",
        encoding="utf-8",
    )
    tree = ast.parse(bypass.read_text(encoding="utf-8"))
    caught = 0
    for scope in ast.walk(tree):
        if not isinstance(scope, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        built = _composed_names(scope)
        for node in ast.walk(scope):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) \
                    and node.func.id == "held_fields":
                given = node.args[0]
                if _locally_built(given) or (
                    isinstance(given, ast.Name) and given.id in built
                ):
                    caught += 1
    assert caught == 2, "a composed plan walked past the call-site gate"


@pytest.mark.cap12_aftercare_property
def test_the_one_production_call_site_hands_over_what_the_main_sent():
    """The other half of the guarantee, and the half a static check cannot
    give: the single caller passes a value read straight off the main's own
    message, and nothing between the two adds a word."""
    tree = ast.parse((ROOT / "half/crisis/safetyplan.py").read_text("utf-8"))
    calls = [
        node for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
        and node.func.id == "held_fields"
    ]
    assert len(calls) == 1, "there is more than one production call site"
    given = calls[0].args[0]
    assert isinstance(given, ast.Call), given
    assert given.func.id == "lines_from", (
        "the writer is handed something other than the main's own message"
    )


@pytest.mark.cap12_aftercare_property
def test_only_one_expression_in_the_writer_puts_a_value_into_the_field():
    """The exemption the writer gate has to grant, bounded so it is not a hole.

    ``safetyplan.py`` is exempt from the field-spelling scan because it *is*
    the writer — and a second writer added inside it therefore passed. So the
    file is scanned too, and exactly one expression may build the field, inside
    exactly one function.
    """
    tree = ast.parse((ROOT / "half/crisis/safetyplan.py").read_text(encoding="utf-8"))
    writers: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            for inner in ast.walk(node):
                if isinstance(inner, ast.Dict) and any(
                    isinstance(key, ast.Name) and key.id == "PLAN"
                    or isinstance(key, ast.Constant) and key.value == "plan"
                    for key in inner.keys if key is not None
                ):
                    writers.append(f"{node.name}:{inner.lineno}")
    assert len(writers) == 1, f"more than one writer inside the writer: {writers}"
    assert writers[0].startswith("held_fields:"), writers


# =============================================================================
# matrix: plan ingestion — a production path exists
# =============================================================================


INTAKE = "here is my safety plan\n" + "\n".join(LINES)


@pytest.mark.cap12_aftercare_property
def test_the_writer_has_a_production_caller():
    """Matrix: plan ingestion. *Not test-only.*

    Without this the whole feature is unreachable: ``held_fields`` had no
    caller outside the suite, so in a shipped build ``Holder.produce`` could
    only ever answer *"I am not holding a safety plan for you"*, and the
    retrieval, the projection, the rendering and the quarantine rule were all
    dead code behind a sentence nobody could change.
    """
    callers = [
        relative for relative in _package_modules()
        if any(
            isinstance(node, ast.Call) and (
                node.func.attr if isinstance(node.func, ast.Attribute)
                else node.func.id if isinstance(node.func, ast.Name) else ""
            ) == "held_fields"
            for node in ast.walk(ast.parse((ROOT / relative).read_text("utf-8")))
        )
    ]
    assert callers, "nothing in the product can ever hold a plan"


def test_a_main_can_hand_half_a_plan_and_ask_for_it_back(tmp_path):
    """The round trip, end to end, through the real runtime: the main sends it,
    Half acknowledges holding it, and gives it back word for word."""
    root = tmp_path / "mains"
    (root / "vidit").mkdir(parents=True)
    registry = ActorRegistry(root)
    replies = drive(registry, [(INTAKE, AT), (ASK_FOR_IT, AT + 60)])
    registry.close()

    assert templates.PLAN_HELD_NOW.text in replies[0]
    for line in LINES:
        assert line in replies[1], line


def test_what_is_stored_is_what_was_sent(tmp_path):
    """Verbatim at the *intake*, not only at the render. Nothing is reordered,
    retitled, numbered or reworded on the way in."""
    root = tmp_path / "mains"
    (root / "vidit").mkdir(parents=True)
    registry = ActorRegistry(root)
    drive(registry, [(INTAKE, AT)])
    records = registry.safetyplan_records("vidit")
    registry.close()
    assert [r["plan"] for r in records] == [list(LINES)]


@pytest.mark.cap12_aftercare_property
def test_the_marker_decides_where_the_plan_starts_and_nothing_else():
    """A marker, not a parser. Half stores everything after the line the main
    put the marker on, and the only thing it drops is a blank line — which is
    not a step and could not be rendered as one."""
    assert safetyplan.lines_from("here is my safety plan\na\n\nb") == ["a", "b"]
    assert safetyplan.lines_from("here is my safety plan") == []
    assert safetyplan.lines_from("no marker at all") == []


def test_an_intake_of_nothing_is_refused_rather_than_held(tmp_path):
    """A marker with no document under it is not a plan, and claiming to hold
    one would be a lie the main finds out about at three in the morning."""
    root = tmp_path / "mains"
    (root / "vidit").mkdir(parents=True)
    registry = ActorRegistry(root)
    replies = drive(registry, [("here is my safety plan", AT)])
    assert templates.PLAN_UNREADABLE.text in replies[0]
    assert registry.safetyplan_records("vidit") == ()
    registry.close()


def test_a_plan_too_long_to_show_is_refused_at_the_intake(tmp_path):
    """Refused on the turn the main can still do something about it, rather
    than stored for ever and withheld for ever."""
    root = tmp_path / "mains"
    (root / "vidit").mkdir(parents=True)
    huge = "here is my safety plan\n" + "\n".join(
        f"step {n}" for n in range(safetyplan.MAX_LINES + 5)
    )
    registry = ActorRegistry(root)
    replies = drive(registry, [(huge, AT)])
    assert templates.PLAN_UNREADABLE.text in replies[0]
    assert registry.safetyplan_records("vidit") == ()
    registry.close()


def test_a_plan_handed_over_inside_the_mode_is_still_held(tmp_path):
    """The moment a main is most likely to send one is the moment they are
    least able to be told to try again later."""
    root = tmp_path / "mains"
    (root / "vidit").mkdir(parents=True)
    registry = ActorRegistry(root)
    replies = drive(registry, [
        ("i want to kill myself", AT),
        (INTAKE, AT + 60),
    ])
    registry.close()
    assert templates.PLAN_HELD_NOW.text in replies[1]
    assert respond.is_templated(replies[1]) or templates.OPEN_HELD.text in replies[1]


def test_the_acknowledgement_repeats_nothing_back(tmp_path):
    """Quoting somebody's own worst day back at them the moment they send it is
    not a receipt. Half says it has it and stops."""
    for line in LINES:
        assert line not in templates.PLAN_HELD_NOW.text


@pytest.mark.cap12_aftercare_property
def test_the_acknowledgement_claims_nothing_about_who_wrote_it():
    """And neither does the sentence that frames a produced plan. Half stores
    a document; it cannot check who made it, and printing a claim it cannot
    check over a clinical document is not a claim to make on somebody's
    behalf."""
    for line in (templates.PLAN_OPEN, templates.PLAN_HELD_NOW):
        lowered = line.text.casefold()
        assert "with a professional" not in lowered, line.id
        assert "your clinician" not in lowered, line.id
        assert "your therapist" not in lowered, line.id


# =============================================================================
# review round 1: the newest plan, and the turn about somebody else
# =============================================================================


def test_the_newest_plan_is_the_one_written_last_not_the_one_named_last(tmp_path):
    """*Supersession* has to be a fact about time. Sorting by id alone called
    itself supersession and was not: ids are opaque, so ``p_zebra`` written
    first beat ``p_alpha`` written last and a withdrawn document came back as
    current, under a sentence saying nothing had been changed."""
    root = tmp_path / "mains"
    with Store(root / "vidit") as store:
        store.record(Op.ASSERT, "p_zebra", "2026-06-01T00:00Z",
                     **held_fields(["the old plan"]))
        store.record(Op.ASSERT, "p_alpha", "2026-08-01T00:00Z",
                     **held_fields(["the new plan"]))
    said = holder_over(root).produce("vidit")
    assert "the new plan" in said and "the old plan" not in said


@pytest.mark.cap12_aftercare_property
def test_a_plan_with_no_stamp_does_not_outrank_a_dated_one():
    """"I cannot tell when this was written" does not read as "it is the
    current one"."""
    plans = [
        {"id": "p_1", "plan": ["undated"]},
        {"id": "p_0", "t": "2026-08-01T00:00Z", "plan": ["dated"]},
    ]
    assert safetyplan.held(plans).lines == ("dated",)


def test_a_plan_is_not_produced_on_a_turn_about_somebody_else(tmp_path):
    """Matrix: plan on a third-party turn. *Not produced* — the same rule that
    keeps aftercare silent there.

    The message is both a third-party disclosure and a plan phrase, and
    answering it with the main's own document changes the subject to them at
    the moment they are frightened for somebody else.
    """
    root = store_with(tmp_path)
    registry = ActorRegistry(root)
    replies = drive(registry, [(
        "my friend said she wants to kill herself, should i make her a safety plan",
        AT,
    )])
    registry.close()

    assert signals.assess(
        "my friend said she wants to kill herself, should i make her a safety plan"
    ).action is signals.Action.SURFACE
    assert templates.OTHER_LIMIT.text in replies[0]
    for line in LINES:
        assert line not in replies[0], line
    assert templates.PLAN_OPEN.text not in replies[0]


def test_a_plan_request_out_of_the_mode_is_answered_on_the_reply(tmp_path):
    """Observed on what the main receives rather than on what was written. The
    only out-of-mode case before this asserted on log ops, so replacing the
    branch with a bare pipeline return left the suite green."""
    root = store_with(tmp_path)
    registry = ActorRegistry(root)
    replies = drive(registry, [(ASK_FOR_IT, AT)])
    registry.close()

    assert templates.PLAN_OPEN.text in replies[0]
    for line in LINES:
        assert line in replies[0], line
