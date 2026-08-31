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


def test_no_module_imports_the_pipeline_around_the_gate():
    """Nothing outside the gate and its own module may reach the pipeline."""
    offenders = []
    for path in (ROOT / "half").rglob("*.py"):
        rel = str(path.relative_to(ROOT))
        if rel in {"half/crisis/gate.py", "half/actor/runtime.py"}:
            continue
        if PIPELINE_ATTR in path.read_text(encoding="utf-8"):
            offenders.append(rel)
    assert not offenders, f"modules reaching the pipeline outside the gate: {offenders}"


def test_the_crisis_stub_is_honest():
    """An empty gate is safer than a plausible one.

    A keyword scan here would read as coverage and discourage building the real
    detector, which the crisis-protocol companion specifies precisely.
    """
    source = (ROOT / "half/crisis/gate.py").read_text(encoding="utf-8")
    assert "story 6" in source, "the stub must say where the real logic lands"
    assert "NotImplementedError" in source, "the crisis response must not be faked"
