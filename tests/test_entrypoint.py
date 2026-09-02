"""AD-10: crisis owns the entrypoint and the pipeline has exactly one caller.

A crisis *check* the pipeline calls is an ordinary function call, and function
calls get refactored around. Making crisis the entrypoint means no route into
the pipeline can skip it — but Python cannot forbid a direct import, so this
asserts the property statically instead. It is the strongest guarantee
available, not a proof, and the spine says so.
"""

from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PIPELINE_ATTR = "_pipeline"


def _module(relative: str) -> ast.Module:
    return ast.parse((ROOT / relative).read_text(encoding="utf-8"))


def test_the_pipeline_has_exactly_one_caller_and_it_is_the_gate():
    callers: list[str] = []
    for path in (ROOT / "half").rglob("*.py"):
        for node in ast.walk(_module(str(path.relative_to(ROOT)))):
            if isinstance(node, ast.Call):
                func = node.func
                if isinstance(func, ast.Attribute) and func.attr == PIPELINE_ATTR:
                    callers.append(str(path.relative_to(ROOT)))
    assert callers == ["half/crisis/gate.py"], (
        f"the pipeline must have exactly one caller, the crisis gate; found {callers}"
    )


def test_the_runtime_routes_inbound_through_the_gate():
    """The runtime must not call its own pipeline directly."""
    source = (ROOT / "half/actor/runtime.py").read_text(encoding="utf-8")
    assert "gate.handle(" in source, "runtime must delegate inbound to the gate"
    tree = _module("half/actor/runtime.py")
    direct = [
        n for n in ast.walk(tree)
        if isinstance(n, ast.Call)
        and isinstance(n.func, ast.Attribute)
        and n.func.attr == PIPELINE_ATTR
    ]
    assert not direct, "runtime calls the pipeline directly, bypassing the gate"


def pipeline_reach(path: Path) -> set[str]:
    """Every way ``path``'s **code** names the pipeline. The predicate.

    Four spellings, and each is a real route rather than a guess at one: taking
    the attribute (which covers calling it, aliasing it and passing it on),
    binding the bare name, defining a function with that name, and reaching it
    through a string — ``getattr(runtime, "_pipeline")`` is the bypass an
    attribute scan does not see.

    **Not a substring scan over the file**, which is what this replaced. That
    version fired on the word appearing in a *docstring*, so a module that
    merely explained where the pipeline is failed the gate, and the fix on offer
    was to reword the prose — which teaches exactly the wrong lesson about what
    the rule is. Prose about a rule is not a violation of it; code is.

    String constants inside docstrings are excluded for that reason, and only
    for that reason: every other string is a candidate for a ``getattr``.
    """
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    docstrings = {
        id(node.body[0].value) for node in ast.walk(tree)
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef,
                             ast.AsyncFunctionDef))
        and node.body and isinstance(node.body[0], ast.Expr)
        and isinstance(node.body[0].value, ast.Constant)
        and isinstance(node.body[0].value.value, str)
    }
    found: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Attribute) and node.attr == PIPELINE_ATTR:
            found.add("attribute")
        elif isinstance(node, ast.Name) and node.id == PIPELINE_ATTR:
            found.add("name")
        elif (
            isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
            and node.name == PIPELINE_ATTR
        ):
            found.add("definition")
        elif (
            isinstance(node, ast.Constant)
            and isinstance(node.value, str)
            and node.value == PIPELINE_ATTR
            and id(node) not in docstrings
        ):
            found.add("string")
    return found


def test_no_module_reaches_the_pipeline_around_the_gate():
    """Nothing outside the gate and its own module may reach the pipeline."""
    offenders = {}
    for path in (ROOT / "half").rglob("*.py"):
        rel = str(path.relative_to(ROOT))
        if rel in {"half/crisis/gate.py", "half/actor/runtime.py"}:
            continue
        reached = pipeline_reach(path)
        if reached:
            offenders[rel] = sorted(reached)
    assert not offenders, f"modules reaching the pipeline outside the gate: {offenders}"


def test_the_pipeline_scan_catches_every_spelling_and_ignores_prose(tmp_path):
    """A guard nobody has run against the mutation it forbids is a guard nobody
    knows the reach of — and this one replaced a scan that reported a docstring
    as a violation while never having been run against a real bypass.
    """
    for name, line in (
        ("attribute", "x = runtime._pipeline\n"),
        ("name", "from half.actor.runtime import _pipeline\n_pipeline\n"),
        ("string", 'x = getattr(runtime, "_pipeline")\n'),
        ("definition", "async def _pipeline(inbound):\n    return None\n"),
    ):
        bypass = tmp_path / f"bypass_{name}.py"
        bypass.write_text(line, encoding="utf-8")
        assert name in pipeline_reach(bypass), (name, line)

    prose = tmp_path / "prose.py"
    prose.write_text(
        '"""The turn path is _pipeline, and this module does not touch it."""\n'
        "def go():\n"
        '    """Called from _pipeline, once."""\n'
        "    return 1\n",
        encoding="utf-8",
    )
    assert pipeline_reach(prose) == set(), "prose about the rule is not a breach"


def test_the_crisis_stub_is_gone():
    """The inverse of what this asserted through story 5a.

    Until story 6a an empty gate was safer than a plausible one: a keyword scan
    would have read as coverage and discouraged building the real detector. The
    detector exists now, so the assertion flips — a gate that still raised
    ``NotImplementedError`` on the crisis path, or still deferred to a later
    story, would be a gate that goes quiet in the one place going quiet is a
    documented catastrophic failure.
    """
    source = (ROOT / "half/crisis/gate.py").read_text(encoding="utf-8")
    assert "NotImplementedError" not in source, (
        "the crisis response must be answered, not deferred"
    )
    for reached in ("half.crisis.signals", "half.crisis import respond"):
        assert reached in source, f"the gate must reach {reached}"
