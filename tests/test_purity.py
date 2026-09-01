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
#:
#: The ladder is here rather than carrying its own scan in ``test_ladder.py``.
#: A second copy of this list is a second, weaker list — the one it replaces
#: had no alias case, so ``import time as t`` inside the ladder passed the new
#: gate while failing this one.
PURE_MODULES = (
    "half/store/fold.py",
    "half/store/ops.py",
    "half/store/records.py",
    "half/governance/ladder.py",
    # The aftercare schedule. It computes elapsed days from two stamps the
    # caller supplies, and the whole point of writing the civil-date
    # arithmetic out by hand was that it could not reach a clock — so the scan
    # that says so has to include it.
    "half/governance/aftercare.py",
    # The civil-date arithmetic itself, since story 8 gave it a second caller.
    # It is the module every floor and every timescale in the product measures
    # with; a clock reaching *this* one would make two subsystems impure at
    # once and neither of their own scans would see it.
    "half/civil.py",
    # The open-loop ledger (CAP-6). Silence is computed from ``last_movement``,
    # the loop's timescale and an **injected** ``now``, so that the same log and
    # the same stamp give the same answer for ever. A clock in any of these
    # three would make the ranking function for everything Half does
    # irreproducible, and the fold that carries loops non-deterministic.
    "half/loops/states.py",
    "half/loops/timescale.py",
    "half/loops/ledger.py",
    # The tension ledger (CAP-7, story 9c). *Drift is tension velocity* is one
    # of the three metrics the product is measured on, and a clock or a model
    # reaching any of these three would make it a number two builds reading one
    # log disagree about — and a model upgrade look like a life event. Widening
    # is computed from the log and an **injected** ``now``, or it is not
    # computed at all.
    "half/tensions/states.py",
    "half/tensions/widening.py",
    "half/tensions/ledger.py",
)

#: **``half/schedule/due.py`` is deliberately not in that list**, and the reason
#: is worth stating so nobody adds it and then deletes the check that actually
#: covers it. It imports ``datetime`` and ``zoneinfo`` because turning an epoch
#: and an IANA key into a local civil time is arithmetic over given values — the
#: import scan above is an import scan, so it cannot tell that from a clock
#: read. What it must not do is *ask what time it is*, and that is asserted at
#: call level in ``tests/test_schedule.py``, over the whole ``half/`` tree
#: rather than one module: exactly one file may call anything ambient, and it is
#: ``half/schedule/clock.py``. That gate is strictly stronger here than adding a
#: name to ``PURE_MODULES`` would be, and it carries its own CI floor.

ROOT = Path(__file__).resolve().parents[1]


def _imported_roots(path: Path) -> set[str]:
    """Root packages ``path`` imports, relative spellings included.

    A relative import used to be skipped outright, which was safe only by
    accident: every relative import inside ``half/`` resolves to a root of
    ``half``, and ``half`` is not forbidden. It stopped being safe the moment
    somebody added a ``half`` submodule to the list — and story 9b found the
    identical condition in its own AD-30 scan letting
    ``from ..model.port import Prompt`` into the fold with every test green.
    So both resolve now, and the two spellings give one answer.
    """
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    package = path.relative_to(ROOT).with_suffix("").parts[:-1]
    roots: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            roots.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            if node.level:
                base = package[: len(package) - (node.level - 1)]
                if base:
                    roots.add(base[0])
            elif node.module:
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


#: Calls that read something the log does not contain. Import scanning alone is
#: not enough: a module can reach ``dt.datetime.now()`` through an import its
#: own line looks innocent, and ``getenv`` is not an import at all.
#:
#: **Lifted here from ``tests/test_ladder.py``, where it globbed
#: ``half/governance/**``.** Story 8 moved the civil-date arithmetic out of
#: ``half/governance/aftercare.py`` into ``half/civil.py`` — and moved it out
#: from under this scan at the same time. A/B verified with identical code: a
#: clock read in ``half/civil.py`` passed the whole suite, while the same read
#: in ``half/governance/aftercare.py`` failed by name. That module is now the
#: arithmetic *both* the thirty-day crisis floor and every loop timescale run
#: on, so it is the last place that may contain a hidden clock. Shared code
#: keeps the guards it had.
AMBIENT_CALLS = {
    "now", "utcnow", "today", "time", "monotonic", "perf_counter",
    "random", "getenv", "urandom", "uuid4",
}


@pytest.mark.parametrize("relative", PURE_MODULES)
def test_pure_modules_call_nothing_ambient(relative):
    """AD-30, at call level rather than import level."""
    tree = ast.parse((ROOT / relative).read_text(encoding="utf-8"))
    called = {
        node.func.attr if isinstance(node.func, ast.Attribute) else
        node.func.id if isinstance(node.func, ast.Name) else ""
        for node in ast.walk(tree) if isinstance(node, ast.Call)
    }
    assert not called & AMBIENT_CALLS, (
        f"{relative} calls {sorted(called & AMBIENT_CALLS)} — a fold, a floor "
        f"and a loop's silence must be pure functions of what they are given "
        f"(AD-30)"
    )


@pytest.mark.parametrize(
    "bypass", ["dt.datetime.now()", "time()", "os.getenv('X')", "uuid4()",
               "datetime.utcnow()", "random()"],
)
def test_the_ambient_scan_sees_each_shape_of_a_clock_read(bypass):
    """Non-vacuity, one shape at a time — the scan is only as good as the names
    it knows, and a scan nobody has tried to defeat is a scan nobody has
    tested."""
    tree = ast.parse(f"def _f():\n    return {bypass}\n")
    called = {
        node.func.attr if isinstance(node.func, ast.Attribute) else
        node.func.id if isinstance(node.func, ast.Name) else ""
        for node in ast.walk(tree) if isinstance(node, ast.Call)
    }
    assert called & AMBIENT_CALLS, f"the ambient scan does not see {bypass!r}"


def test_the_scan_covers_the_arithmetic_two_subsystems_share():
    """The specific regression: ``half/civil.py`` must be in the list."""
    assert "half/civil.py" in PURE_MODULES
    assert "half/governance/aftercare.py" in PURE_MODULES


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
