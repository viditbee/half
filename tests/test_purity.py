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
    # Ambient process state. A fold reading os.environ is the actual "just
    # re-derive it" mistake: it is not a clock, network or model call, so an
    # earlier version of this list let it through while every test stayed
    # green. AD-30 requires a fold to be a pure function of the log alone.
    "os", "sys", "pathlib", "platform", "sqlite3", "configparser",
    "importlib", "shutil", "tempfile",
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


@pytest.mark.parametrize("relative", PURE_MODULES)
def test_pure_modules_do_not_alias_an_impure_import(relative):
    """`import time as t` binds the name `t`, so the root-name scan above would
    miss `t.time()`. This resolves aliases back to their real module."""
    tree = ast.parse((ROOT / relative).read_text(encoding="utf-8"))
    aliased: dict[str, str] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.asname:
                    aliased[alias.asname] = alias.name.split(".")[0]
    offending = {a: r for a, r in aliased.items() if r in FORBIDDEN_ROOTS}
    assert not offending, f"{relative} aliases impure imports: {offending}"


@pytest.mark.parametrize("relative", PURE_MODULES)
def test_pure_modules_never_call_dunder_import(relative):
    """A dynamic import evades every static scan above."""
    source = (ROOT / relative).read_text(encoding="utf-8")
    assert "__import__" not in source, f"{relative} uses __import__ — AD-30 forbids it"


def test_fold_is_indifferent_to_ambient_process_state(tier_change_log, monkeypatch):
    """The mutation the earlier suite could not catch.

    Folding twice in one process cannot see a value that is stable within a
    process but varies across machines. This changes the environment between
    the two folds, so a fold reading ambient config diverges here.
    """
    from half.store.fold import fold

    monkeypatch.setenv("HALF_MODEL_TIER", "cheap")
    monkeypatch.setenv("HOME", "/tmp/one")
    first = fold(tier_change_log.log).canonical_json()

    monkeypatch.setenv("HALF_MODEL_TIER", "frontier")
    monkeypatch.setenv("HOME", "/tmp/two")
    second = fold(tier_change_log.log).canonical_json()

    assert first == second, "fold read ambient process state — AD-30 forbids it"


def test_fold_is_deterministic_over_repeated_runs(tier_change_log):
    from half.store.fold import fold

    results = {fold(tier_change_log.log).canonical_json() for _ in range(5)}
    assert len(results) == 1
