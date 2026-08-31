from __future__ import annotations

import pytest

from half.store.ops import Op
from half.store.store import Store


@pytest.fixture
def store(tmp_path):
    with Store(tmp_path / "main") as s:
        yield s


@pytest.fixture
def tier_change_log(tmp_path):
    """A log whose consolidation output was produced under two different model
    tiers, plus a month rollover.

    This fixture is the point of the replay test. A fold that re-derives
    instead of replaying recorded outcomes would produce different tensions on
    the second run, and a fixture without a tier change would never notice
    (AD-30).
    """
    with Store(tmp_path / "tiered") as s:
        s.record(Op.ASSERT, "b_1", "2026-07-04T08:00Z", subject="self",
                 claim="replies to mother within three minutes", ledger="revealed",
                 license="behave", independent=2, model_tier="cheap")
        s.record(Op.ASSERT, "b_2", "2026-07-19T21:30Z", subject="self",
                 claim="said he would start running in March", ledger="stated",
                 license="ask", independent=1, model_tier="cheap")
        s.record(Op.TENSION, "x_1", "2026-07-20T02:10Z",
                 between=["b_1", "b_2"], state="fresh", license="behave",
                 model_tier="cheap")
        # tier changes here — anything re-derived would now differ
        s.record(Op.ASSERT, "b_3", "2026-08-02T07:15Z", subject="self",
                 claim="has not flown a paraglider in three years", ledger="revealed",
                 license="behave", independent=3, model_tier="frontier")
        s.record(Op.TENSION, "x_2", "2026-08-03T02:40Z",
                 between=["b_2", "b_3"], state="widening", license="behave",
                 model_tier="frontier")
        s.record(Op.LOOP_TRANSITION, "l_1", "2026-08-03T02:41Z",
                 loop="buy-farmland", state="stalled", timescale="years",
                 last_movement="2026-03-12")
        yield s
