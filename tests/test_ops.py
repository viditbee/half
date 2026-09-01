"""One test per row of the story's I/O & Edge-Case Matrix."""

from __future__ import annotations

import dataclasses
import json

import pytest

from half.errors import (
    CorruptLogError,
    SchemaVersionError,
    SecretLeakError,
    StoreError,
    UnknownOpError,
)
from half.loops import ledger
from half.store.export import SECRET_PATTERNS, export, scan_for_secrets
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
        "assert", "retract", "revise", "expunge", "tension", "loop_transition",
        # `ceiling` joined the vocabulary in story 5a, with the schema version
        # bumped alongside it (AD-29): an older build meeting one must refuse
        # to fold rather than skip it, because a log whose ceiling records go
        # unseen resolves every license uncapped.
        "ceiling",
        # `crisis` joined in story 6a, on the same terms and one degree more
        # urgently: a build that could not see one would fold a main who is in
        # the mode to a main who is not, and answer their next message through
        # the ordinary pipeline.
        "crisis",
        # `aftercare` joined in story 6c, again with the schema version bumped.
        # It is the only record that carries the main's *answer* about resuming
        # the mirror, and a build that could not see one would read a main who
        # declined as a main who was never asked.
        "aftercare",
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
    # Assembled at runtime rather than written as a literal: this repo is
    # public, and a secret-shaped literal trips GitHub's own scanning and every
    # grep anyone runs over the tree. The value is synthetic either way.
    fake = {"refresh" + "_token": "1/" + "/0" + "abcdefghijklmnopqrstuvwxyz012345"}
    (store.root / "stray.json").write_text(json.dumps(fake), encoding="utf-8")
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

def test_state_carries_only_durable_objects(store):
    """AD-26: mood is not a belief. The folded State exposes beliefs, tensions,
    loops, expunged ids and the license ceiling — and deliberately no
    volatile-state container, so there is nowhere for a mood to be written even
    if an op tried.

    The ceiling and the crisis record are here rather than in memory and that
    is not a breach of AD-26: what AD-26 keeps out of the log is *how the main
    is right now*, overwritten and expiring. A cap that runs for thirty days of
    aftercare is a governance decision, and one held only in memory lifts
    itself on the next eviction. A crisis mode held in memory ends at the same
    moment, and its ending is a mode exit nobody decided.

    The aftercare record joins them in story 6c on the same terms, and it is
    the sharpest case of the three. It carries whether Half has asked the main
    about resuming the mirror and what they answered — a question held in
    memory is asked again after every eviction, which is nagging, and a decline
    held in memory disappears, leaving some later "yes" free to land on a
    question the main already refused.

    The crisis record is also the one place in the log that names a *state* of
    the main, so its fields are checked here: tier, signal count and mode
    state, and never a word of what was said (AD-22). The aftercare record is
    held to the same rule and carries only a state and a time.

    ``expunged_loops`` joins them in story 8, and it is a *separate* set rather
    than tidiness: belief ids and loop slugs share one id space, and one shared
    set meant erasing a belief froze a loop that happened to share its name —
    the loop stayed in the fold, which every firewall test asserted, while every
    later transition on it was silently dropped."""
    store.record(Op.ASSERT, "b_1", "2026-08-01T00:00Z", claim="durable")
    names = {f.name for f in dataclasses.fields(store.state())}
    assert names == {"beliefs", "tensions", "loops", "expunged",
                     "expunged_loops", "ceiling", "crisis", "aftercare"}


# ── findings from review: gaps the original suite could not observe ─────────

# -- export never destroys the destination -----------------------------------

def test_export_leaves_a_pre_existing_destination_untouched_when_it_refuses(
    store, tmp_path
):
    """The earlier version rmtree'd the destination on a secret finding, which
    deleted whatever was already there."""
    store.record(Op.ASSERT, "b_1", "2026-08-01T00:00Z", claim="ok")
    fake = {"refresh" + "_token": "1/" + "/0" + "abcdefghijklmnopqrstuvwxyz012345"}
    (store.root / "stray.json").write_text(json.dumps(fake), encoding="utf-8")

    dest = tmp_path / "dest"
    dest.mkdir()
    precious = dest / "tax_return.pdf"
    precious.write_text("do not delete me", encoding="utf-8")

    with pytest.raises(StoreError):
        export(store.root, dest)
    assert precious.read_text(encoding="utf-8") == "do not delete me"


def test_export_refuses_a_non_empty_destination(store, tmp_path):
    store.record(Op.ASSERT, "b_1", "2026-08-01T00:00Z", claim="ok")
    dest = tmp_path / "dest"
    dest.mkdir()
    (dest / "existing.txt").write_text("hello", encoding="utf-8")
    with pytest.raises(StoreError):
        export(store.root, dest)


def test_export_creates_nothing_when_a_secret_is_found(store, tmp_path):
    store.record(Op.ASSERT, "b_1", "2026-08-01T00:00Z", claim="ok")
    fake = {"refresh" + "_token": "1/" + "/0" + "abcdefghijklmnopqrstuvwxyz012345"}
    (store.root / "stray.json").write_text(json.dumps(fake), encoding="utf-8")
    dest = tmp_path / "never"
    with pytest.raises(SecretLeakError):
        export(store.root, dest)
    assert not dest.exists()


# -- the scan fails closed ---------------------------------------------------

def test_secret_inside_a_non_utf8_file_is_still_caught(store, tmp_path):
    """A single invalid byte used to disable the scan for the whole file, so a
    credential in a binary blob exported clean."""
    store.record(Op.ASSERT, "b_1", "2026-08-01T00:00Z", claim="ok")
    key = "AKIA" + "IOSFODNN7EXAMPLE"
    (store.root / "creds.bin").write_bytes(
        b"\xff\xfe\x00binary junk " + key.encode() + b" more\x00\x80"
    )
    with pytest.raises(SecretLeakError):
        export(store.root, tmp_path / "export")


SECRET_SAMPLES = {
    "google oauth refresh token": "1/" + "/0" + "abcdefghijklmnopqrstuvwxyz012345",
    "google api key": "AIza" + "0123456789abcdefghijklmnopqrstuvwxy",
    "bearer/access token field": '{"access' + '_token": "abc123"}',
    "client secret field": '{"client' + '_secret": "shhh"}',
    "authorization header": "Authorization: " + "Bearer abc.def.ghi",
    "private key block": "-----BEGIN " + "RSA PRIVATE KEY-----",
    "aws access key id": "AKIA" + "IOSFODNN7EXAMPLE",
    "anthropic api key": "sk-" + "ant-" + "abcdefghijklmnopqrstuvwxyz0123",
}


@pytest.mark.parametrize("label", [label for label, _ in SECRET_PATTERNS])
def test_every_secret_pattern_has_a_sample_that_trips_it(label, tmp_path):
    """Seven of the eight patterns were previously never exercised, so a broken
    regex was undetectable. Parametrizing over the tuple also fails loudly when
    a pattern is added without a sample."""
    assert label in SECRET_SAMPLES, f"no sample for pattern {label!r}"
    (tmp_path / "planted.txt").write_text(SECRET_SAMPLES[label], encoding="utf-8")
    findings = scan_for_secrets(tmp_path)
    assert any(f.startswith(label) for f in findings), f"{label} did not trip"


def test_derived_database_sidecars_never_reach_an_export(store, tmp_path):
    """half.db was excluded by exact name, so half.db-wal shipped — and the WAL
    holds uncheckpointed belief text."""
    store.record(Op.ASSERT, "b_1", "2026-08-01T00:00Z", claim="uncheckpointed text")
    for sidecar in ("half.db-wal", "half.db-shm"):
        (store.root / sidecar).write_text("derived", encoding="utf-8")
    out = export(store.root, tmp_path / "export")
    assert [p.name for p in out.rglob("half.db*")] == []


# -- a bad record can never become durable -----------------------------------

def test_a_field_the_derived_view_cannot_materialize_is_rejected_before_append(store):
    """It used to append first and rebuild second, so the bad line was durable
    and every later rebuild raised forever."""
    with pytest.raises(ValueError):
        store.record(Op.ASSERT, "b_1", "2026-08-01T00:00Z", claim="x", independent="many")
    assert store.log.shards() == []
    assert store.state().beliefs == {}


def test_a_non_string_claim_is_rejected_rather_than_silently_unindexed(store):
    with pytest.raises(ValueError):
        store.record(Op.ASSERT, "b_1", "2026-08-01T00:00Z", claim={"nested": "value"})


def test_reserved_fields_cannot_be_passed_through(store):
    with pytest.raises(ValueError):
        make(Op.ASSERT, "b_1", "2026-08-01T00:00Z", id="different")


# -- ranking and limit are actually observed ---------------------------------

def test_better_matches_rank_above_worse_ones(store):
    store.record(Op.ASSERT, "b_dense", "2026-08-01T00:00Z",
                 claim="paraglider paraglider paraglider season")
    store.record(Op.ASSERT, "b_sparse", "2026-08-01T00:01Z",
                 claim="a paraglider once, long ago, among many other unrelated words")
    hits = store.search("paraglider")
    assert [h["id"] for h in hits] == ["b_dense", "b_sparse"]


def test_limit_bounds_the_result_set(store):
    for i in range(5):
        store.record(Op.ASSERT, f"b_{i}", "2026-08-01T00:00Z", claim="shared term here")
    assert len(store.search("shared", limit=2)) == 2
    assert store.search("shared", limit=0) == []


def test_a_malformed_query_raises_a_domain_error_not_a_sqlite_one(store):
    """FTS5 operators are ordinary characters in a main's own words."""
    store.record(Op.ASSERT, "b_1", "2026-08-01T00:00Z", claim="ok")
    assert store.search('"unbalanced') == []
    assert store.search("NEAR(") == []
    assert store.search("   ") == []


# -- correction ops must name what they correct ------------------------------

@pytest.mark.parametrize("op", [Op.RETRACT, Op.REVISE, Op.EXPUNGE])
def test_a_correction_without_a_target_raises_rather_than_no_opping(store, op):
    store.record(Op.ASSERT, "b_x", "2026-08-01T00:00Z", claim="still here")
    store.log.append(make(op, "c_1", "2026-08-02T00:00Z"))
    with pytest.raises(CorruptLogError):
        store.rebuild()


def test_expunge_removes_a_loop_from_the_derived_view(store):
    """An expunge that names the loop *as a loop* still erases it.

    Story 8 narrowed this: ``target`` alone reaches beliefs and tensions, and it
    takes the second explicit ``loop`` field to reach a wanting, so a belief's
    removal can never take a loop with it (CAP-6, the refutation firewall). The
    main's own erasure is unaffected, which is what this asserts; that the
    narrow form no longer reaches a loop is asserted in ``test_loops.py``.
    """
    store.record(Op.LOOP_TRANSITION, "l_1", "2026-08-01T00:00Z",
                 loop="buy-farmland", state="stalled")
    assert "buy-farmland" in store.state().loops
    store.record(Op.EXPUNGE, "x_1", "2026-08-02T00:00Z",
                 **ledger.expunged("buy-farmland"))
    assert "buy-farmland" not in store.state().loops


# -- unicode line separators -------------------------------------------------

def test_a_claim_containing_a_unicode_line_separator_can_still_be_expunged(store):
    """str.splitlines() breaks on U+2028, which encode() writes raw, so the
    rewrite used to split one record into two corrupt lines."""
    store.record(Op.ASSERT, "b_x", "2026-08-01T00:00Z", claim="line one line two")
    store.expunge("b_x", t="2026-08-02T00:00Z")
    assert "b_x" in store.state().expunged
    assert "line two" not in (store.log.root / "2026-08.jsonl").read_text(encoding="utf-8")


def test_expunge_aborts_before_mutating_anything_when_a_later_shard_is_bad(store):
    """Partial erasure has no repair path, so validation happens first."""
    store.record(Op.ASSERT, "b_x", "2026-08-01T00:00Z", claim="target text")
    store.record(Op.ASSERT, "b_y", "2026-09-01T00:00Z", claim="later shard")
    with (store.log.root / "2026-09.jsonl").open("a", encoding="utf-8") as fh:
        fh.write("{broken\n")
    with pytest.raises(CorruptLogError):
        store.log.expunge_bodies({"b_x"})
    assert "target text" in (store.log.root / "2026-08.jsonl").read_text(encoding="utf-8")


def test_expunge_is_idempotent_so_a_resume_completes(store):
    store.record(Op.ASSERT, "b_x", "2026-08-01T00:00Z", claim="gone")
    assert store.log.expunge_bodies({"b_x"}) == 1
    assert store.log.expunge_bodies({"b_x"}) == 0


# -- encoder and decoder agree ----------------------------------------------

def test_encode_refuses_to_write_a_token_its_own_decoder_rejects():
    record = make(Op.ASSERT, "b_1", "2026-08-01T00:00Z")
    object.__setattr__(record, "data", {**record.data, "n": float("nan")})
    with pytest.raises(ValueError):
        encode(record)


# -- privacy posture ---------------------------------------------------------

def test_store_directories_and_database_are_not_world_readable(store):
    store.record(Op.ASSERT, "b_1", "2026-08-01T00:00Z", claim="private")
    for path in (store.root, store.log.root, store.db_path):
        mode = path.stat().st_mode & 0o077
        assert mode == 0, f"{path} is group/world accessible ({oct(path.stat().st_mode)})"
