"""One test per row of the story's I/O & Edge-Case Matrix."""

from __future__ import annotations

import pytest

from half.errors import CorruptLogError, SchemaVersionError, SecretLeakError, UnknownOpError
from half.store.export import export, scan_for_secrets
from half.store.fold import fold
from half.store.ops import OP_NAMES, SCHEMA_VERSION, Op
from half.store.records import decode, encode, make
from half.store.store import Store


# -- append a belief ---------------------------------------------------------

def test_appending_a_belief_writes_a_line_and_shows_in_the_fold(store):
    store.record(Op.ASSERT, "b_1", "2026-08-14T09:12Z", subject="self", claim="x")
    shard = store.log.root / "2026-08.jsonl"
    assert shard.read_text(encoding="utf-8").count("\n") == 1
    assert "b_1" in store.state().beliefs


# -- unknown op --------------------------------------------------------------

def test_unknown_op_raises_naming_op_and_line_and_is_never_skipped(store):
    store.record(Op.ASSERT, "b_1", "2026-08-01T00:00Z", claim="kept")
    shard = store.log.root / "2026-08.jsonl"
    with shard.open("a", encoding="utf-8") as fh:
        fh.write('{"t":"2026-08-02T00:00Z","op":"belief_retract","id":"b_2"}\n')

    with pytest.raises(UnknownOpError) as excinfo:
        list(store.log)
    assert excinfo.value.op == "belief_retract"
    assert excinfo.value.line == 2
    with pytest.raises(UnknownOpError):
        store.rebuild()


def test_op_vocabulary_is_closed():
    assert OP_NAMES == {
        "assert", "retract", "revise", "expunge", "tension", "loop_transition"
    }


def test_record_from_a_newer_schema_refuses_rather_than_dropping_data():
    with pytest.raises(SchemaVersionError):
        decode(
            '{"t":"2026-08-01T00:00Z","op":"assert","id":"b_1","v":%d}'
            % (SCHEMA_VERSION + 1),
            path="t", lineno=1,
        )


# -- corrupt line ------------------------------------------------------------

@pytest.mark.parametrize(
    "line",
    [
        "{not json",
        '{"t":"x","op":"assert"}',                      # missing id
        '{"t":"x","op":"assert","id":"b","id":"c"}',    # duplicate key
        '{"t":"x","op":"assert","id":"b","n":NaN}',     # non-finite
        '["not","an","object"]',
    ],
)
def test_corrupt_line_raises_with_position(line):
    with pytest.raises(CorruptLogError) as excinfo:
        decode(line, path="beliefs/2026-08.jsonl", lineno=7)
    assert excinfo.value.line == 7
    assert "2026-08.jsonl" in str(excinfo.value)


def test_earlier_records_survive_a_later_corrupt_line(store):
    store.record(Op.ASSERT, "b_1", "2026-08-01T00:00Z", claim="kept")
    good = store.state().canonical_json()
    with (store.log.root / "2026-08.jsonl").open("a", encoding="utf-8") as fh:
        fh.write("{broken\n")
    with pytest.raises(CorruptLogError):
        store.rebuild()
    assert store.state().canonical_json() == good  # derived view untouched


# -- retract / revise / expunge ---------------------------------------------

def test_retract_removes_from_fold_but_both_records_remain(store):
    store.record(Op.ASSERT, "b_x", "2026-08-01T00:00Z", claim="used to be true")
    store.record(Op.RETRACT, "r_1", "2026-08-05T00:00Z", target="b_x")
    assert "b_x" not in store.state().beliefs
    assert [r.op for r in store.log] == [Op.ASSERT, Op.RETRACT]


def test_revise_and_retract_are_distinguishable_in_the_log(store):
    """Half was wrong (revise, apology owed) vs the main changed (retract, none)."""
    store.record(Op.ASSERT, "b_a", "2026-08-01T00:00Z", claim="a")
    store.record(Op.ASSERT, "b_b", "2026-08-01T00:01Z", claim="b")
    store.record(Op.RETRACT, "r_1", "2026-08-02T00:00Z", target="b_a")
    store.record(Op.REVISE, "v_1", "2026-08-03T00:00Z", target="b_b")
    ops = [r.op for r in store.log]
    assert Op.RETRACT in ops and Op.REVISE in ops
    assert store.state().beliefs == {}


def test_expunge_tombstones_the_body_and_omits_it_from_the_fold(store):
    store.record(Op.ASSERT, "b_x", "2026-08-01T00:00Z", claim="delete me entirely")
    store.expunge("b_x", t="2026-08-06T00:00Z")
    assert "b_x" not in store.state().beliefs
    assert "b_x" in store.state().expunged
    text = (store.log.root / "2026-08.jsonl").read_text(encoding="utf-8")
    assert "delete me entirely" not in text
    assert '"tombstone":true' in text


def test_expunged_id_stays_expunged_if_reasserted(store):
    store.record(Op.ASSERT, "b_x", "2026-08-01T00:00Z", claim="gone")
    store.expunge("b_x", t="2026-08-02T00:00Z")
    store.record(Op.ASSERT, "b_x", "2026-08-03T00:00Z", claim="sneaking back")
    assert "b_x" not in store.state().beliefs


# -- unknown field -----------------------------------------------------------

def test_unknown_field_survives_decode_and_reencode():
    line = '{"future_field":42,"id":"b_1","op":"assert","t":"2026-08-01T00:00Z"}'
    record = decode(line, path="t", lineno=1)
    assert record.data["future_field"] == 42
    assert encode(record) == line  # already canonical: sorted, tight separators


def test_unknown_field_survives_a_write_read_cycle(store):
    store.append(make(Op.ASSERT, "b_1", "2026-08-01T00:00Z", odd_field=[1, 2]))
    assert next(iter(store.log)).data["odd_field"] == [1, 2]


# -- export ------------------------------------------------------------------

def test_export_reconstructs_state_and_omits_the_derived_database(store, tmp_path):
    store.record(Op.ASSERT, "b_1", "2026-08-01T00:00Z", subject="self", claim="swims")
    original = store.state().canonical_json()

    out = export(store.root, tmp_path / "export")
    assert not (out / "half.db").exists()

    with Store(tmp_path / "restored") as restored:
        (restored.root / "beliefs").mkdir(parents=True, exist_ok=True)
        for shard in (out / "beliefs").glob("*.jsonl"):
            (restored.root / "beliefs" / shard.name).write_bytes(shard.read_bytes())
        assert restored.rebuild().canonical_json() == original


def test_export_refuses_when_secret_material_is_present(store, tmp_path):
    store.record(Op.ASSERT, "b_1", "2026-08-01T00:00Z", claim="ok")
    (store.root / "stray.json").write_text(
        '{"refresh_token":"1//0abcdefghijklmnopqrstuvwxyz012345"}', encoding="utf-8"
    )
    with pytest.raises(SecretLeakError):
        export(store.root, tmp_path / "export")
    assert not (tmp_path / "export").exists()


def test_a_clean_store_scans_clean(store, tmp_path):
    store.record(Op.ASSERT, "b_1", "2026-08-01T00:00Z", claim="nothing secret here")
    assert scan_for_secrets(export(store.root, tmp_path / "export")) == []


# -- month rollover ----------------------------------------------------------

def test_month_rollover_creates_a_second_shard_read_in_order(store):
    store.record(Op.ASSERT, "b_1", "2026-08-31T23:59Z", claim="august")
    store.record(Op.ASSERT, "b_2", "2026-09-01T00:01Z", claim="september")
    assert [p.name for p in store.log.shards()] == ["2026-08.jsonl", "2026-09.jsonl"]
    assert [r.id for r in store.log] == ["b_1", "b_2"]


def test_fold_does_not_depend_on_shard_boundaries(store):
    store.record(Op.ASSERT, "b_x", "2026-08-31T23:59Z", claim="spans")
    store.record(Op.RETRACT, "r_1", "2026-09-01T00:01Z", target="b_x")
    assert "b_x" not in store.state().beliefs


# -- fts query ---------------------------------------------------------------

def test_bm25_ranked_search_over_claims(store):
    store.record(Op.ASSERT, "b_1", "2026-08-01T00:00Z", claim="has not flown a paraglider in three years")
    store.record(Op.ASSERT, "b_2", "2026-08-01T00:01Z", claim="replies to mother within three minutes")
    hits = store.search("paraglider")
    assert [h["id"] for h in hits] == ["b_1"]
    assert isinstance(hits[0]["score"], float)


def test_search_reflects_removals(store):
    store.record(Op.ASSERT, "b_1", "2026-08-01T00:00Z", claim="unique phrase here")
    assert store.search("unique") != []
    store.record(Op.RETRACT, "r_1", "2026-08-02T00:00Z", target="b_1")
    assert store.search("unique") == []


# -- volatile state ----------------------------------------------------------

def test_no_op_exists_for_volatile_state(store):
    """AD-26: mood is not a belief. There is deliberately no way to write
    volatile state into the log."""
    assert not any("state" == name or "mood" == name for name in OP_NAMES)
