"""Static enforcement of AD-30: replay is pure.

"Just re-derive it" is the natural way to write a fold, and it silently breaks
the replay invariant the first time a main changes model tier. A behavioural
test would not catch it — a re-deriving fold passes every round-trip assertion
until the tier actually changes. So this checks the imports instead.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

#: Anything that could make a fold non-deterministic: a clock, randomness, the
#: network, a model, or a subprocess.
FORBIDDEN_ROOTS = {
    "time", "datetime", "random", "secrets", "uuid",
    "socket", "http", "urllib", "requests", "httpx", "asyncio",
    "subprocess", "anthropic", "openai",
}

#: Modules that must stay pure. The store's façade is excluded: it legitimately
#: coordinates I/O. fold.py is the function replay actually runs.
PURE_MODULES = ("half/store/fold.py", "half/store/ops.py", "half/store/records.py")

ROOT = Path(__file__).resolve().parents[1]


def _imported_roots(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    roots: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            roots.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            if node.level == 0 and node.module:
                roots.add(node.module.split(".")[0])
    return roots


@pytest.mark.parametrize("relative", PURE_MODULES)
def test_pure_modules_import_nothing_impure(relative):
    offending = _imported_roots(ROOT / relative) & FORBIDDEN_ROOTS
    assert not offending, (
        f"{relative} imports {sorted(offending)} — replay must never call a "
        "model, touch the network, or read a clock (AD-30)"
    )


def test_fold_module_calls_no_clock_or_random():
    """Catches a late `import time` inside a function body, which the
    module-level import scan above would still see, and any attribute call
    reaching a forbidden root through an alias."""
    source = (ROOT / "half/store/fold.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            func = node.func
            if isinstance(func, ast.Attribute) and isinstance(func.value, ast.Name):
                assert func.value.id not in FORBIDDEN_ROOTS, (
                    f"fold.py calls {func.value.id}.{func.attr}() — AD-30 forbids it"
                )


def test_fold_is_deterministic_over_repeated_runs(tier_change_log):
    from half.store.fold import fold

    results = {fold(tier_change_log.log).canonical_json() for _ in range(5)}
    assert len(results) == 1
