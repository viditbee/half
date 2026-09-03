"""The shape three callers share: ``half/model/consult.py`` (story 14).

This file covers the extracted shape on its own terms. The three callers keep
their own suites, and each of them gained an equivalence case pinning that its
bound, breaker, tally, allowlist and report behave exactly as they did at
``95d9709`` — asserted per caller rather than inferred from a green suite.

**The one thing worth reading twice is the alarm.** ``due`` is the branch that
was wrong in all three copies, fixed here once. It is exercised directly rather
than through a hundred consultations against a provider double, because the
whole argument for this module is that a correction made here reaches every
caller — and an argument made through three different fixtures is an argument
about the fixtures.
"""

from __future__ import annotations

import ast
import math
from pathlib import Path

import pytest

from half.model import consult
from half.model.consult import (
    ALARM_AFTER,
    BREAK_AFTER,
    PER_CALL_MICRO_USD,
    PER_PASS_MICRO_USD,
    REPORT_EVERY,
    Breaker,
    Due,
    a_bound,
    count_one,
    due,
    failure_key,
    rate,
    refuses_as_a_bound,
    wider_than,
)
from half.model.port import Failure, Kind, Reason

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "half" / "model" / "consult.py"

MAIN = "vidit"


# =============================================================================
# the report cadence, and the bug this module exists to fix once
# =============================================================================


@pytest.mark.ad19_guarantee
def test_the_alarm_is_not_hidden_by_a_round_number():
    """The payoff, at its source.

    All three copies asked the periodic question first and hung the alarm off
    an ``elif``, so at the hundredth consultation — and every hundredth after —
    a wholly failing consultation reported at ``info``. Story 13a fixed exactly
    one of them. Here it is one branch, and the three callers read it.
    """
    assert due(REPORT_EVERY, 1.0, alarm_rate=0.2) is Due.ALARM
    assert due(REPORT_EVERY * 2, 1.0, alarm_rate=0.5) is Due.ALARM
    assert due(REPORT_EVERY * 7, 0.51, alarm_rate=0.5) is Due.ALARM


@pytest.mark.ad19_guarantee
def test_the_round_number_still_reports_when_nothing_is_wrong():
    """The other half. Fixing the alarm must not cost the ordinary line: a
    healthy consultation still says what it did every hundred calls, at
    ``info``, which is what makes the rate visible rather than merely
    reachable."""
    assert due(REPORT_EVERY, 0.0, alarm_rate=0.2) is Due.PERIODIC
    assert due(REPORT_EVERY, 0.1, alarm_rate=0.2) is Due.PERIODIC


@pytest.mark.ad19_guarantee
def test_a_rate_below_the_threshold_is_arithmetic_and_not_evidence():
    """Under ``ALARM_AFTER`` consultations one failure is a large fraction of a
    small number, and an alarm on it teaches an operator to ignore alarms."""
    for count in range(1, ALARM_AFTER):
        assert due(count, 1.0, alarm_rate=0.2) is Due.NOTHING


@pytest.mark.ad19_guarantee
def test_the_alarm_fires_on_its_own_interval_and_not_only_on_round_hundreds():
    """A wholly failing consultation must not be silent for as long as it takes
    to reach a round number, which is the reason the alarm has an interval of
    its own."""
    fired = [
        count for count in range(1, REPORT_EVERY + 1)
        if due(count, 1.0, alarm_rate=0.2) is Due.ALARM
    ]
    assert fired == list(range(ALARM_AFTER, REPORT_EVERY + 1, ALARM_AFTER))


@pytest.mark.ad19_guarantee
def test_between_the_intervals_nothing_is_written():
    assert due(ALARM_AFTER + 1, 1.0, alarm_rate=0.2) is Due.NOTHING
    assert due(REPORT_EVERY - 1, 0.0, alarm_rate=0.2) is Due.NOTHING


@pytest.mark.ad19_guarantee
def test_the_alarm_rate_is_the_callers_and_is_never_defaulted_here():
    """A fifth of a waiting main's turns and half of a nightly pass's mornings
    are different questions, so the number has no default in the shape. Calling
    without one is a ``TypeError`` at the call site rather than somebody else's
    policy applied quietly."""
    with pytest.raises(TypeError):
        due(ALARM_AFTER, 1.0)  # type: ignore[call-arg]
    assert due(ALARM_AFTER, 0.3, alarm_rate=0.2) is Due.ALARM
    assert due(ALARM_AFTER, 0.3, alarm_rate=0.5) is Due.NOTHING


@pytest.mark.ad19_guarantee
def test_the_periodic_and_alarm_answers_are_one_decision_and_not_two():
    """The shape of the bug, not its instance. Two independent booleans is how
    the periodic line and the alarm became mutually exclusive in three modules;
    one value means a caller cannot spell that arrangement."""
    answers = {due(c, r, alarm_rate=0.2)
               for c in range(1, 301) for r in (0.0, 0.19, 0.2, 1.0)}
    assert answers <= {Due.NOTHING, Due.PERIODIC, Due.ALARM}
    assert len(list(Due)) == 3


# =============================================================================
# the breaker
# =============================================================================


@pytest.mark.ad19_guarantee
def test_a_run_of_failures_trips_the_breaker_and_not_one_short_of_it():
    breaker = Breaker(break_for=50)
    for _ in range(BREAK_AFTER - 1):
        assert breaker.note(MAIN, failed=True) is False
    assert breaker.note(MAIN, failed=True) is True


@pytest.mark.ad19_guarantee
def test_one_success_clears_the_run():
    """A breaker that counted failures cumulatively would stand a healthy
    holder down for one bad afternoon spread over a month."""
    breaker = Breaker(break_for=50)
    for _ in range(BREAK_AFTER - 1):
        breaker.note(MAIN, failed=True)
    breaker.note(MAIN, failed=False)
    for _ in range(BREAK_AFTER - 1):
        assert breaker.note(MAIN, failed=True) is False


@pytest.mark.ad19_guarantee
def test_the_stand_down_lasts_exactly_the_injected_length():
    """``break_for`` is policy — fifty turns for a waiting main, twenty mornings
    for a nightly pass — so the shape takes it and never supplies it."""
    breaker = Breaker(break_for=3)
    for _ in range(BREAK_AFTER):
        breaker.note(MAIN, failed=True)
    assert [breaker.spend(MAIN) for _ in range(4)] == [True, True, True, False]


@pytest.mark.ad19_guarantee
def test_the_countdown_runs_on_every_unit_including_the_quiet_ones():
    """Story 13a's finding, kept: a countdown that only advanced on units that
    reached a holder left a main stood down for twenty mornings silent for a
    month and a half after a quiet fortnight."""
    breaker = Breaker(break_for=2)
    for _ in range(BREAK_AFTER):
        breaker.note(MAIN, failed=True)
    assert breaker.spend(MAIN) is True
    assert breaker.spend(MAIN) is True
    assert breaker.spend(MAIN) is False


@pytest.mark.ad19_guarantee
def test_the_breaker_is_one_holders_and_not_the_deployments():
    """One main's provider being down says nothing about another's, and a
    global breaker would take the consultation away from everybody because of
    one bad key."""
    breaker = Breaker(break_for=50)
    for _ in range(BREAK_AFTER):
        breaker.note("down", failed=True)
    assert breaker.spend("down") is True
    assert breaker.spend("up") is False
    assert breaker.note("up", failed=True) is False


@pytest.mark.ad19_guarantee
def test_a_holder_that_never_failed_is_never_standing_down():
    breaker = Breaker(break_for=50)
    assert breaker.spend("never-seen") is False
    for _ in range(BREAK_AFTER * 3):
        assert breaker.note(MAIN, failed=False) is False
        assert breaker.spend(MAIN) is False


@pytest.mark.ad19_guarantee
def test_the_breaker_closes_again_and_can_trip_a_second_time():
    """A breaker that never closed would be an outage that removed the
    consultation permanently — the silent degradation, arriving as a fix."""
    breaker = Breaker(break_for=1)
    for _ in range(BREAK_AFTER):
        breaker.note(MAIN, failed=True)
    assert breaker.spend(MAIN) is True
    assert breaker.spend(MAIN) is False
    for _ in range(BREAK_AFTER - 1):
        assert breaker.note(MAIN, failed=True) is False
    assert breaker.note(MAIN, failed=True) is True


@pytest.mark.ad19_guarantee
def test_the_breaker_says_nothing_and_holds_nothing_public():
    """It decides; the caller writes the line. A report routed through here
    would move three callers' log calls out from under the scans that prove no
    log line on those paths can carry content."""
    breaker = Breaker(break_for=50)
    assert sorted(n for n in dir(breaker) if not n.startswith("_")) == [
        "note", "spend",
    ]
    assert not hasattr(breaker, "__dict__")


# =============================================================================
# the holder allowlist
# =============================================================================


class Narrow:
    """What the port hands back: one method, and no way to reach anything."""

    async def classify(self, work): ...


#: Method names **no denylist would contain**, which is story 13a's review
#: finding turned into a sweep. The check this replaced named six methods, and
#: the replacement passed only because one double happened to carry
#: ``classify``. A guard that is only as good as the names somebody thought of
#: is not a guard, so this is deliberately a list of names nobody would think
#: of.
UNGUESSABLE = (
    "wobble", "ʃibboleth", "資料", "запрос", "n7", "z", "do_the_thing",
    "as_provider", "reset", "batch", "spawn",
    "eval_", "exfiltrate", "τηλε", "a" * 200,
)


@pytest.mark.ad19_guarantee
def test_the_narrow_holder_the_port_hands_back_is_accepted():
    """The other direction: a guard that refused the shipped holder would be a
    guard nobody could use."""
    assert wider_than(Narrow(), frozenset({"classify"})) == []


@pytest.mark.ad19_guarantee
@pytest.mark.parametrize("method", UNGUESSABLE)
def test_a_method_no_denylist_would_name_is_still_refused(method):
    holder = Narrow()
    setattr(holder, method, lambda *a, **k: None)
    assert wider_than(holder, frozenset({"classify"})) == [method]


@pytest.mark.ad19_guarantee
def test_every_wider_method_is_named_and_not_only_the_first():
    """An operator handed one name fixes one method and runs into the next."""
    holder = Narrow()
    for method in ("chat", "invoke", "run"):
        setattr(holder, method, lambda *a, **k: None)
    assert wider_than(holder, frozenset({"classify"})) == ["chat", "invoke", "run"]


@pytest.mark.ad19_guarantee
def test_a_wider_method_defined_on_the_class_is_seen_too():
    """``dir`` rather than ``vars``: an attribute set on the instance and a
    method defined on the class are the same reach."""

    class Wide:
        async def classify(self, work): ...
        async def generate(self, work): ...

    assert wider_than(Wide(), frozenset({"classify"})) == ["generate"]


@pytest.mark.ad19_guarantee
def test_a_non_callable_attribute_is_not_a_method():
    """The allowlist is about *reach*, not about tidiness. A counter or a name
    hanging off a holder is not a way to produce text."""
    holder = Narrow()
    holder.calls = 3  # type: ignore[attr-defined]
    holder.model = "x"  # type: ignore[attr-defined]
    assert wider_than(holder, frozenset({"classify"})) == []


@pytest.mark.ad19_guarantee
def test_a_dunder_is_not_swept_and_the_caller_asks_about_callable_itself():
    """``dir`` on anything returns two dozen dunders, so sweeping them would
    refuse every object there is. That an object is *itself* callable is a
    method by another name, and each caller asks that question separately —
    over the object, where the answer is unambiguous."""

    class CallableHolder:
        async def classify(self, work): ...
        def __call__(self): ...

    assert wider_than(CallableHolder(), frozenset({"classify"})) == []
    assert callable(CallableHolder())


@pytest.mark.ad19_guarantee
def test_the_allowlist_is_what_is_passed_in_and_not_a_name_this_module_knows():
    """The shape holds no protocol vocabulary: the voice allows ``generate``
    and the two classifiers allow ``classify``, and this module knows neither
    word."""
    holder = Narrow()
    assert wider_than(holder, frozenset({"classify"})) == []
    assert wider_than(holder, frozenset()) == ["classify"]
    assert wider_than(holder, frozenset({"generate"})) == ["classify"]


# =============================================================================
# the bound
# =============================================================================


@pytest.mark.ad19_guarantee
@pytest.mark.parametrize("bad", [0, -1, -0.5, None, "5", True, False, object()])
def test_what_three_constructors_have_always_refused_as_a_bound(bad):
    assert refuses_as_a_bound(bad) is True
    assert a_bound(bad) is False


@pytest.mark.ad19_guarantee
@pytest.mark.parametrize("good", [2.0, 20.0, 1, 0.5])
def test_a_positive_number_of_seconds_is_a_bound(good):
    assert refuses_as_a_bound(good) is False
    assert a_bound(good) is True


@pytest.mark.ad19_guarantee
def test_infinity_and_nan_are_refused_by_the_predicate_the_call_path_uses():
    """``asyncio.timeout(nan)`` never fires and ``asyncio.timeout(inf)`` never
    fires, which is a main waiting on a hung provider through the guard that
    exists to stop exactly that. Every comparison against a NaN is ``False``,
    so ``value <= 0`` admits one."""
    for value in (math.nan, math.inf, -math.inf):
        assert a_bound(value) is False


@pytest.mark.ad19_guarantee
def test_the_constructor_predicate_still_admits_infinity_and_says_so():
    """The asymmetry is pinned rather than left to be rediscovered.

    The three constructors have always admitted an infinite bound; the per-call
    override in two of them has not. Closing the gap is a behaviour change in
    three callers and is Ask First, so this story reports it and pins what is
    actually true today — a passing suite that quietly disagreed with the
    shipped constructors would be worse than the gap.
    """
    assert refuses_as_a_bound(math.inf) is False
    assert a_bound(math.inf) is False
    assert refuses_as_a_bound(math.nan) is False
    assert a_bound(math.nan) is False


# =============================================================================
# the counting
# =============================================================================


@pytest.mark.ad19_guarantee
def test_a_failure_is_counted_under_two_closed_enums_and_nothing_else():
    key = failure_key(Failure(Kind.UNAVAILABLE, Reason.TRANSPORT_FAILED))
    assert key == "unavailable/transport-failed"
    assert key.count("/") == 1


@pytest.mark.ad19_guarantee
def test_one_key_is_one_counter_however_often_it_arrives():
    counter: dict[str, int] = {}
    for _ in range(3):
        count_one(counter, "a")
    count_one(counter, "b")
    assert counter == {"a": 3, "b": 1}


@pytest.mark.ad19_guarantee
def test_no_consultations_reads_as_a_rate_of_zero_and_not_as_a_fault():
    """A build with no model wired is a supported deployment. A rate that
    raised — or reported one — on an empty denominator would alarm on every
    deployment that had not equipped anybody."""
    assert rate(0, 0) == 0.0
    assert rate(1, 2) == 0.5
    assert rate(50, 100) == 0.5


# =============================================================================
# purity: the shape knows no domain
# =============================================================================


def identifiers_and_literals(tree: ast.AST) -> set[str]:
    """Every name the module binds or reads, and every string that is not a
    docstring.

    Public, and imported by ``tests/test_correction.py``, because the
    correction path's own label is the word ``correction`` — which the shape's
    prose uses to name ``half.correction.candidate`` while explaining what it
    must not know. A raw substring sweep would report that sentence as a leak.
    The crisis path's labels are distinctive enough to be checked against the
    source directly, and are.

    Docstrings are excluded deliberately and it is the only honest way to run
    this scan: this module's docstring has to be able to say *what it must not
    know*, and a substring sweep over prose would refuse the sentence that
    states the rule. What is scanned is what the module can actually do with —
    identifiers, and the literals it computes with.
    """
    docstrings = {
        id(node.body[0].value)
        for node in ast.walk(tree)
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef,
                             ast.AsyncFunctionDef))
        and node.body
        and isinstance(node.body[0], ast.Expr)
        and isinstance(node.body[0].value, ast.Constant)
        and isinstance(node.body[0].value.value, str)
    }
    found: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Name):
            found.add(node.id)
        elif isinstance(node, ast.Attribute):
            found.add(node.attr)
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef,
                              ast.ClassDef)):
            found.add(node.name)
        elif isinstance(node, ast.arg):
            found.add(node.arg)
        elif isinstance(node, ast.Constant) and isinstance(node.value, str):
            if id(node) not in docstrings:
                found.add(node.value)
    return found


#: Words the shape may not know. The crisis label set, the correction label
#: set, the voice's silence vocabulary, and the three domains themselves.
DOMAIN_WORDS = (
    "main_at_risk", "another_at_risk", "no_risk", "unsure",
    "correction", "no_correction",
    "nothing-quotable", "no-language", "standing-down", "past-the-bound",
    "crisis", "morning", "suicide", "belief", "claim", "ledger", "quarantine",
    "classifier", "widening", "voice", "template", "instruction",
)


@pytest.mark.ad19_guarantee
def test_the_shape_names_no_label_no_meaning_and_no_morning():
    """The condition the deferred entry set, and the reason it matters:
    ``tests/test_crisis_golden.py`` pins the crisis label set and instructions
    by digest as clinical-review material, and a shared module holding any of
    it would turn that pin into a pin on a base class."""
    found = identifiers_and_literals(ast.parse(SOURCE.read_text("utf-8")))
    offending = sorted(
        f"{word} in {name!r}"
        for name in found for word in DOMAIN_WORDS
        if word in name.lower()
    )
    assert not offending, offending


@pytest.mark.ad19_guarantee
@pytest.mark.parametrize(
    "bypass",
    [
        'MAIN_AT_RISK = "main_at_risk"',
        'def morning(): ...',
        'ACTION = {"correction": 1}',
        'x = crisis.label',
        'def f(no_risk): ...',
    ],
    ids=["constant", "function", "literal", "attribute", "argument"],
)
def test_the_domain_scan_sees_each_shape_of_a_leak(bypass):
    """Non-vacuity, one shape at a time. A scan nobody has tried to defeat is a
    scan nobody has tested — and this one had to exclude docstrings, which is
    exactly the kind of exclusion that quietly makes a scan see nothing."""
    found = identifiers_and_literals(ast.parse(bypass))
    assert any(word in name.lower() for name in found for word in DOMAIN_WORDS)


@pytest.mark.ad19_guarantee
def test_the_shape_imports_the_port_and_the_standard_library_and_nothing_else():
    """AD-30 and the layer table at once. Nothing here may reach a domain
    module — ``half.crisis`` is the entry gate and is depended on by no domain
    module, which is the obstacle that kept this extraction from living
    there."""
    tree = ast.parse(SOURCE.read_text("utf-8"))
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(a.name for a in node.names)
        elif isinstance(node, ast.ImportFrom):
            assert node.level == 0, "a relative import hides which layer it is"
            imported.add(node.module or "")
    half_imports = sorted(i for i in imported if i.startswith("half"))
    assert half_imports == ["half.model.port"], half_imports


@pytest.mark.ad19_guarantee
def test_the_shape_reads_no_clock_and_opens_no_store():
    """AD-30. A clock here would put one in three modules at once, and the
    breaker counts in turns and mornings precisely so that it cannot."""
    tree = ast.parse(SOURCE.read_text("utf-8"))
    called = {
        node.func.attr if isinstance(node.func, ast.Attribute) else
        node.func.id if isinstance(node.func, ast.Name) else ""
        for node in ast.walk(tree) if isinstance(node, ast.Call)
    }
    ambient = {"now", "utcnow", "today", "time", "monotonic", "perf_counter",
               "random", "getenv", "urandom", "uuid4", "open", "sleep"}
    assert not called & ambient, sorted(called & ambient)


@pytest.mark.ad19_guarantee
def test_the_shape_writes_no_log_line_at_all():
    """Each caller proves that no log line *it* writes can carry content, by
    scanning the arguments of the logging calls in its own files. A report
    routed through a shared writer would move those calls out from under the
    scan that is the whole guarantee, so there is no logger here to route
    them to."""
    tree = ast.parse(SOURCE.read_text("utf-8"))
    log_calls = [
        node.func.attr for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
        and node.func.attr in {
            "debug", "info", "warning", "error", "exception", "critical", "log",
        }
    ]
    assert not log_calls, log_calls
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(a.name for a in node.names)
        elif isinstance(node, ast.ImportFrom):
            imported.add(node.module or "")
    assert "logging" not in imported, "there is a logger here to route lines to"


@pytest.mark.ad19_guarantee
def test_the_five_shared_numbers_are_the_ones_that_were_identical():
    """Measured before the extraction, pinned after it. Moving one of these is
    moving it for three callers at once, which is the point and is also the
    risk."""
    assert (BREAK_AFTER, REPORT_EVERY, ALARM_AFTER) == (5, 100, 10)
    assert PER_CALL_MICRO_USD == 100_000
    assert PER_PASS_MICRO_USD == 500_000_000
    assert PER_CALL_MICRO_USD <= PER_PASS_MICRO_USD


@pytest.mark.ad19_guarantee
def test_the_three_policy_numbers_have_no_default_in_the_shape():
    """A bound, a stand-down and an alarm rate differ between the callers for
    reasons — a waiting main against a nightly pass — so the shape refuses to
    guess. There is no module constant here for any of them."""
    for name in ("BOUND_SECONDS", "BREAK_FOR", "ALARM_RATE"):
        assert not hasattr(consult, name), name
    with pytest.raises(TypeError):
        Breaker()  # type: ignore[call-arg]
