"""The replay invariant (AD-4): delete the derived store, replay, get the same
state back — byte for byte.

If this ever fails, Half has started keeping state that exists nowhere in the
log, which breaks export, expunge and rebuild-after-model-churn at once.
"""

from __future__ import annotations

from half.store import db
from half.store.fold import fold
from half.store.ops import Op
from half.store.store import Store
from half.trust.balance import balance


def test_deleting_the_database_and_replaying_reproduces_identical_state(tier_change_log):
    store = tier_change_log
    before = store.state().canonical_json()
    assert before != "", "fixture produced no state"

    store.close()
    store.db_path.unlink()
    assert not store.db_path.exists()

    after = store.rebuild().canonical_json()
    assert after == before
    assert store.state().canonical_json() == before


def test_replay_is_stable_across_a_model_tier_change(tier_change_log):
    """The fixture spans a cheap -> frontier switch. A fold that re-derived
    rather than replayed recorded outcomes would diverge here."""
    store = tier_change_log
    first = fold(store.log).canonical_json()
    second = fold(store.log).canonical_json()
    assert first == second

    tiers = {
        r.data.get("model_tier") for r in store.log if "model_tier" in r.data
    }
    assert tiers == {"cheap", "frontier"}, "fixture must span a tier change"


def test_fold_matches_the_database_view(tier_change_log):
    store = tier_change_log
    assert store.fold().canonical_json() == store.state().canonical_json()


def test_rebuild_is_idempotent(tier_change_log):
    store = tier_change_log
    once = store.rebuild().canonical_json()
    twice = store.rebuild().canonical_json()
    assert once == twice


def test_the_trust_balance_matches_after_a_rebuild(tier_change_log):
    """Matrix: *replay* — the trust currency, and the one quantity in Half that
    the derived view deliberately does not carry (CAP-4, story 5b, AD-30).

    Every other assertion in this file compares one derived view against
    another. This one cannot, because there is nothing derived to compare: the
    balance is *delivered favours minus questions asked*, folded straight out of
    the log, so the whole point is that discarding SQLite changes nothing.

    That is also why the case matters. An increment-on-delivery,
    decrement-on-ask counter — the tempting implementation, and the one story 4
    refused for salience and story 9c for decay — would pass every other
    assertion here: a stored counter replays perfectly. It is never
    *inconsistent*, only *wrong*. What catches it is that the number survives
    the database being deleted, and that ``State`` has nowhere to keep one
    (``tests/test_trust.py``).
    """
    store = tier_change_log
    before = balance(store.log)
    assert before.earned and before.spent, "fixture must carry both halves"

    store.close()
    store.db_path.unlink()
    store.rebuild()

    assert balance(store.log) == before
    assert balance(store.log) == balance(store.log)


def test_state_survives_a_fresh_store_object(tmp_path):
    root = tmp_path / "main"
    with Store(root) as s:
        s.record(Op.ASSERT, "b_1", "2026-08-01T00:00Z", subject="self", claim="swims")
        expected = s.state().canonical_json()
    with Store(root) as reopened:
        assert reopened.rebuild().canonical_json() == expected
