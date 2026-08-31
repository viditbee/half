"""Retrieval: ranking, degradation, the disabled path, determinism (CAP-9).

Every assertion here corresponds to a row of the story's I/O matrix.

**On the ordering tests.** Each one varies exactly one factor and holds the
other three constant, *and* arranges the identifiers so that the score tie-break
(`-score`, then `id`) would give the opposite answer. Without that second half
the tests are decoration: an earlier version of this file had every expected
winner sorted first alphabetically, so replacing the bm25 or recency multiplier
with the constant `1.0` left the whole suite green — the tie-break was quietly
producing the right answer for the wrong reason.
"""

from __future__ import annotations

import ast
import sqlite3
from pathlib import Path

import pytest

from half.errors import RetrievalDisabled, RetrievalError, StoreError
from half.retrieval.port import Candidate, Ranked, Reranker, RerankSource
from half.retrieval.prefix import build_prefix
from half.retrieval.rank import Retriever, RetrievalSwitch
from half.retrieval.salience import salience
from half.store.ops import Op
from half.store.store import Store

ROOT = Path(__file__).resolve().parents[1]
NOW = "2026-08-31T09:00:00Z"

#: Every module under half/retrieval, at any depth. ``glob`` would scan only
#: the top level — and the first real reranker will live in a subpackage,
#: which is exactly where a clock, a network call or a write would land.
RETRIEVAL_MODULES = sorted(
    str(p.relative_to(ROOT)) for p in (ROOT / "half/retrieval").rglob("*.py")
)


@pytest.fixture
def beliefs(tmp_path):
    """A store wired the way the running product wires it: prefixes indexed."""
    with Store(tmp_path / "main", prefix=build_prefix) as store:
        yield store


def assert_belief(store, ident, claim, **fields):
    """A belief whose every ranking input is pinned unless a test varies it."""
    fields.setdefault("subject", "self")
    fields.setdefault("ledger", "revealed")
    fields.setdefault("independent", 0)
    t = fields.pop("t", "2026-08-01T00:00:00Z")
    store.record(Op.ASSERT, ident, t, claim=claim, **fields)


def retrieve(store, query, **kw):
    return Retriever(store=store).retrieve(query, now=kw.pop("now", NOW), **kw)


# -- one factor at a time, with the tie-break pointing the other way ---------

def test_bm25_alone_decides_when_nothing_else_differs(beliefs):
    """Replacing the bm25 multiplier with 1.0 must fail here."""
    assert_belief(beliefs, "b_zzz", "paraglider paraglider paraglider season")
    assert_belief(beliefs, "b_aaa", "a paraglider once long ago among other words")

    assert retrieve(beliefs, "paraglider").ids == ("b_zzz", "b_aaa")


def test_recency_alone_decides_when_nothing_else_differs(beliefs):
    """Replacing the recency multiplier with 1.0 must fail here.

    Identical claims and identical prefixes, so the FTS documents are the same
    and bm25 cannot break the tie; only ``t`` differs.
    """
    assert_belief(beliefs, "b_zzz", "runs on tuesdays", t="2026-08-30T00:00:00Z")
    assert_belief(beliefs, "b_aaa", "runs on tuesdays", t="2024-01-01T00:00:00Z")

    assert retrieve(beliefs, "runs").ids == ("b_zzz", "b_aaa")


def test_corroboration_freshness_alone_decides(beliefs):
    assert_belief(beliefs, "b_zzz", "runs on tuesdays",
                  last_corroborated="2026-08-30T00:00:00Z")
    assert_belief(beliefs, "b_aaa", "runs on tuesdays",
                  last_corroborated="2024-01-01T00:00:00Z")

    assert retrieve(beliefs, "runs").ids == ("b_zzz", "b_aaa")


def test_independence_alone_decides(beliefs):
    assert_belief(beliefs, "b_zzz", "cooks on sundays", independent=6)
    assert_belief(beliefs, "b_aaa", "cooks on sundays", independent=1)

    assert retrieve(beliefs, "cooks").ids == ("b_zzz", "b_aaa")


def test_loop_state_alone_decides(beliefs):
    """Two loops of equal word length, so the indexed prefixes are the same
    size and bm25 stays neutral. Only one of them is advancing."""
    assert_belief(beliefs, "b_zzz", "thinks about it often", loop="fly-again")
    assert_belief(beliefs, "b_aaa", "thinks about it often", loop="learn-tabla")
    beliefs.record(Op.LOOP_TRANSITION, "l_1", "2026-08-02T00:00:00Z",
                   loop="fly-again", state="advancing", timescale="months")

    assert retrieve(beliefs, "thinks").ids == ("b_zzz", "b_aaa")


# -- the salience components must actually compete --------------------------
#
# Each single-factor test above still passes under a 0.9/0.05/0.05 weight skew,
# because a component worth almost nothing still breaks a tie nothing else can.
# These two put the components against each other, where only a balanced split
# gives the stated answer.

def test_fresh_corroboration_outweighs_a_large_support_count(beliefs):
    """Confirmed last week beats "ten sources agreed, once, years ago"."""
    assert_belief(beliefs, "b_zzz", "runs on tuesdays", independent=0,
                  last_corroborated="2026-08-30T00:00:00Z")
    assert_belief(beliefs, "b_aaa", "runs on tuesdays", independent=10)

    assert retrieve(beliefs, "runs").ids == ("b_zzz", "b_aaa")


def test_an_advancing_loop_outweighs_a_thin_support_count(beliefs):
    """The open-loop ledger is the ranking function for everything Half does,
    so a live wanting outranks a lightly-supported fact."""
    assert_belief(beliefs, "b_zzz", "thinks about it often", independent=0,
                  loop="fly-again")
    assert_belief(beliefs, "b_aaa", "thinks about it often", independent=1,
                  loop="learn-tabla")
    beliefs.record(Op.LOOP_TRANSITION, "l_1", "2026-08-02T00:00:00Z",
                   loop="fly-again", state="advancing", timescale="months")

    assert retrieve(beliefs, "thinks").ids == ("b_zzz", "b_aaa")


@pytest.mark.ad24
def test_every_weight_is_strictly_positive(beliefs):
    """AD-24 as arithmetic. A zero anywhere in the product removes a belief."""
    assert_belief(beliefs, "b_1", "nothing corroborates this")
    candidate = retrieve(beliefs, "nothing")[0]
    assert set(candidate.weights) == {"bm25", "strand", "recency", "salience"}
    assert all(value > 0.0 for value in candidate.weights.values())
    assert candidate.score > 0.0


# -- the prefix is indexed and structural ------------------------------------

def test_a_query_matching_the_prefix_and_not_the_claim_still_retrieves(beliefs):
    assert_belief(beliefs, "b_1", "has not been up since the accident",
                  loop="buy-farmland")
    assert "farmland" not in beliefs.state().beliefs["b_1"]["claim"]

    hits = retrieve(beliefs, "farmland")
    assert hits.ids == ("b_1",)
    assert hits[0].bm25 is not None, "matched on a term, not through the backstop"


def test_the_prefix_carries_field_values_and_no_template_words():
    """Template vocabulary is shared by every document, so it can only add
    matches that mean nothing. An earlier version emitted "about {subject}.
    {ledger} ledger. open loop {loop}", which made any message containing the
    word "about" term-match the entire belief set."""
    record = {"subject": "self", "ledger": "revealed", "loop": "buy-farmland"}
    assert build_prefix(record) == build_prefix(record)
    assert build_prefix(record) == "self. revealed. buy farmland"
    for template_word in ("about", "ledger ", "open", "loop"):
        assert template_word not in build_prefix(record)


def test_a_common_english_word_does_not_match_every_belief(beliefs):
    """The consequence of the template words, asserted at the query level."""
    assert_belief(beliefs, "b_1", "flies paragliders", loop="buy-farmland")
    assert_belief(beliefs, "b_2", "replies to his mother quickly")

    for filler in ("about", "open", "loop", "ledger"):
        result = retrieve(beliefs, filler)
        assert all(c.bm25 is None for c in result), (
            f"{filler!r} term-matched a belief through the indexed prefix"
        )


def test_the_prefix_survives_fields_it_does_not_recognise():
    assert build_prefix({"subject": 7, "ledger": None, "loop": ["x"]}) == ""


def test_rebuild_regenerates_the_prefix(beliefs):
    assert_belief(beliefs, "b_1", "has not been up in years", loop="fly-again")
    beliefs.close()
    beliefs.db_path.unlink()
    beliefs.rebuild()
    assert retrieve(beliefs, "fly again").ids == ("b_1",)


def test_a_store_with_no_prefix_builder_still_searches_claims(tmp_path):
    """The prefix is injected, so its absence must degrade, not break."""
    with Store(tmp_path / "plain") as store:
        assert_belief(store, "b_1", "flies paragliders", loop="fly-again")
        assert [h["id"] for h in store.search("paragliders")] == ["b_1"]
        assert store.search("fly again") == []


def test_a_prefix_builder_that_raises_cannot_brick_the_store(tmp_path):
    """It runs inside the rebuild that follows an append, and the append has
    already made the log line durable. A raise would abort every rebuild and
    every later append forever, with the offending line unremovable."""
    def hostile(_belief):
        raise RuntimeError("third-party prefix builder")

    with Store(tmp_path / "main", prefix=hostile) as store:
        assert_belief(store, "b_1", "flies paragliders")
        assert "b_1" in store.state().beliefs
        assert [h["id"] for h in store.search("paragliders")] == ["b_1"]


def test_a_prefix_builder_returning_a_non_string_degrades(tmp_path):
    with Store(tmp_path / "main", prefix=lambda _b: 7) as store:
        assert_belief(store, "b_1", "flies paragliders")
        assert "b_1" in store.state().beliefs


# -- non-ASCII: this product targets India ----------------------------------

def test_a_devanagari_field_is_indexed_and_findable(beliefs):
    """``[A-Za-z0-9]`` splitting dropped the field entirely, so the belief was
    permanently unreachable by the word it was named after."""
    assert_belief(beliefs, "b_1", "keeps putting it off", loop="आशा-project")
    assert build_prefix(beliefs.state().beliefs["b_1"]) != "self. revealed"
    assert retrieve(beliefs, "आशा").ids == ("b_1",)


def test_an_accented_field_folds_the_way_fts5_folds_a_query(beliefs):
    """``café-plans`` used to be indexed as ``caf plans`` while FTS5 folds a
    query for ``café`` to ``cafe`` — so it could never match."""
    assert_belief(beliefs, "b_1", "keeps putting it off", loop="café-plans")
    assert retrieve(beliefs, "café").ids == ("b_1",)
    assert retrieve(beliefs, "cafe").ids == ("b_1",)


# -- degradation -------------------------------------------------------------

class ReverseReranker:
    def rerank(self, query, candidates):
        return list(reversed(candidates))


class BrokenReranker:
    def rerank(self, query, candidates):
        raise RuntimeError("the optional stage fell over")


class InventingReranker:
    """The HippoRAG mis-mapping risk, made concrete: a returned item that was
    never offered. Mapping by fuzzy similarity would silently accept it."""

    def rerank(self, query, candidates):
        return [*candidates, Candidate(id="b_hallucinated", claim="", prefix="",
                                       bm25=None)]


class PruningReranker:
    def rerank(self, query, candidates):
        return list(candidates)[:1]


@pytest.fixture
def two(beliefs):
    assert_belief(beliefs, "b_1", "shared term here alpha")
    assert_belief(beliefs, "b_2", "shared term here beta")
    return beliefs


def test_no_reranker_returns_bm25_order_annotated_as_a_noop(two):
    result = Retriever(store=two).retrieve("shared", now=NOW)
    assert result.rerank is RerankSource.ABSENT
    assert result.degraded
    assert len(result) == 2


def test_a_reranker_that_raises_degrades_to_bm25_order_and_no_error_escapes(two):
    base = Retriever(store=two).retrieve("shared", now=NOW)
    result = Retriever(store=two, reranker=BrokenReranker()).retrieve("shared", now=NOW)

    assert result.rerank is RerankSource.FAILED
    assert result.ids == base.ids, "a failed reranker must not perturb the order"


def test_a_working_reranker_reorders_and_is_annotated(two):
    base = Retriever(store=two).retrieve("shared", now=NOW)
    result = Retriever(store=two, reranker=ReverseReranker()).retrieve("shared", now=NOW)

    assert result.rerank is RerankSource.RERANKED
    assert not result.degraded
    assert result.ids == tuple(reversed(base.ids))


@pytest.mark.parametrize("reranker", [InventingReranker(), PruningReranker()])
def test_a_reranker_that_invents_or_drops_a_candidate_is_rejected(two, reranker):
    """Reordering is the contract. Mapping back is by exact id, never by the
    nearest string — HippoRAG's ``difflib`` cutoff of 0.0 always matches
    something, and something is not the same as the right one."""
    base = Retriever(store=two).retrieve("shared", now=NOW)
    result = Retriever(store=two, reranker=reranker).retrieve("shared", now=NOW)

    assert result.rerank is RerankSource.FAILED
    assert result.ids == base.ids


def test_the_reranker_port_has_exactly_one_method():
    """gbrain's lesson, as a test. A second method needs human sign-off."""
    methods = [
        name for name in vars(Reranker)
        if callable(getattr(Reranker, name, None)) and not name.startswith("_")
    ]
    assert methods == ["rerank"]


def test_the_reranker_sees_only_the_pruned_set(beliefs):
    """HippoRAG prunes before the expensive stage, not after."""
    seen: list[int] = []

    class Counting:
        def rerank(self, query, candidates):
            seen.append(len(candidates))
            return candidates

    for i in range(8):
        assert_belief(beliefs, f"b_{i}", "shared term here")
    Retriever(store=beliefs, reranker=Counting()).retrieve("shared", now=NOW, limit=3)
    assert seen == [3]


# -- disabled, empty, bounded, and the sentence Half may never say -----------

def test_a_disabled_retriever_raises_rather_than_returning_empty(two):
    switch = RetrievalSwitch()
    retriever = Retriever(store=two, switch=switch)
    assert len(retriever.retrieve("shared", now=NOW)) == 2

    switch.disable()
    with pytest.raises(RetrievalDisabled):
        retriever.retrieve("shared", now=NOW)

    switch.enable()
    assert len(retriever.retrieve("shared", now=NOW)) == 2


@pytest.mark.ad24
def test_an_empty_store_returns_an_empty_result_and_not_an_error(beliefs):
    result = Retriever(store=beliefs).retrieve("anything", now=NOW)
    assert isinstance(result, Ranked)
    assert len(result) == 0
    assert result.rerank is RerankSource.ABSENT, "the annotation survives emptiness"
    assert not result.truncated, "nothing was cut; the store is simply empty"


@pytest.mark.ad24
def test_a_query_matching_no_term_still_returns_the_belief_set(beliefs):
    """"No results" and "no beliefs" must not be the same answer — the first is
    one paraphrase away from "I don't have access to that" (AD-24)."""
    assert_belief(beliefs, "b_1", "flies paragliders")
    assert_belief(beliefs, "b_2", "replies to his mother quickly")

    result = retrieve(beliefs, "zzzz nothing here matches at all")
    assert sorted(result.ids) == ["b_1", "b_2"]
    assert all(c.bm25 is None for c in result), "backstop, not a term match"


@pytest.mark.ad24
def test_a_blank_query_still_reaches_the_belief_set(beliefs):
    assert_belief(beliefs, "b_1", "flies paragliders")
    assert retrieve(beliefs, "   ").ids == ("b_1",)


@pytest.mark.ad24
@pytest.mark.parametrize(
    "query", ["shared term here", "no relevant vocabulary"],
    ids=["term-matched", "backstop"],
)
def test_a_bounded_scan_keeps_the_most_salient_and_says_it_truncated(beliefs, query):
    """The bound is ordered by salience, never by id — on both paths.

    The term path had its own silent cap: ``ORDER BY score, b.id LIMIT ?`` in
    SQL, which is a bm25-ordered cut that no result mentions. Both paths now
    hand the whole matching set up and are bounded here.

    The high-salience beliefs are given the *last* identifiers, so the
    ``ORDER BY id LIMIT`` this replaced would drop exactly the ones that matter
    and report nothing.
    """
    for ident in ("b_aaa1", "b_aaa2"):
        assert_belief(beliefs, ident, "shared term here", independent=0)
    for ident in ("b_zzz1", "b_zzz2"):
        assert_belief(beliefs, ident, "shared term here", independent=8,
                      last_corroborated="2026-08-30T00:00:00Z")

    result = Retriever(store=beliefs, max_scored=2).retrieve(query, now=NOW)
    assert result.truncated, "a cap must never be silent"
    assert sorted(result.ids) == ["b_zzz1", "b_zzz2"]


def test_an_unbounded_scan_is_not_reported_as_truncated(beliefs):
    for ident in ("b_1", "b_2"):
        assert_belief(beliefs, ident, "shared term here")
    assert not Retriever(store=beliefs, max_scored=50).retrieve(
        "shared", now=NOW
    ).truncated


def test_asking_for_no_results_is_distinguishable_from_an_empty_ledger(beliefs):
    assert_belief(beliefs, "b_1", "flies paragliders")
    result = retrieve(beliefs, "paragliders", limit=0)
    assert len(result) == 0
    assert result.truncated, "'you asked for none' must not look like 'there are none'"


@pytest.mark.ad24
def test_the_store_backstop_is_unbounded(beliefs):
    """The cap belongs where salience can order it, not in SQL ordered by id."""
    for i in range(30):
        assert_belief(beliefs, f"b_{i:03d}", "shared term here")
    assert len(beliefs.all_candidates()) == 30


# -- determinism, purity, and the corpus ------------------------------------

def test_the_same_store_and_now_rank_identically_twice(beliefs):
    for i in range(6):
        assert_belief(beliefs, f"b_{i}", f"shared term here variant {i}",
                      independent=i, t=f"2026-0{i + 1}-01T00:00:00Z")

    first = retrieve(beliefs, "shared term")
    second = retrieve(beliefs, "shared term")
    assert first.ids == second.ids
    assert [c.score for c in first] == [c.score for c in second]


def test_an_injected_now_actually_moves_the_ranking(beliefs):
    """Proof that ``now`` is read rather than ignored — otherwise the
    determinism test above would pass on a retriever that never looked."""
    assert_belief(beliefs, "b_1", "same words",
                  last_corroborated="2026-08-30T00:00:00Z")
    near = retrieve(beliefs, "same", now="2026-08-31T00:00:00Z")[0]
    far = retrieve(beliefs, "same", now="2030-08-31T00:00:00Z")[0]
    assert near.score > far.score


def test_a_malformed_now_raises_rather_than_ranking_on_a_guess(beliefs):
    assert_belief(beliefs, "b_1", "anything")
    with pytest.raises(RetrievalError):
        Retriever(store=beliefs).retrieve("anything", now="last tuesday")


#: Calls that would make retrieval depend on something other than its inputs.
_AMBIENT_CALLS = {
    "now", "utcnow", "today", "time", "monotonic", "perf_counter",
    "random", "getenv", "urandom", "uuid4",
}


@pytest.mark.parametrize("relative", RETRIEVAL_MODULES)
def test_retrieval_reads_no_clock_and_no_ambient_state(relative):
    """``now`` is injected. A clock here would break determinism and, through
    the fold it feeds, the replay invariant.

    A behavioural test cannot catch this: a retriever that reads the clock
    still returns identical results twice inside one second.
    """
    tree = ast.parse((ROOT / relative).read_text(encoding="utf-8"))
    called = {
        node.func.attr if isinstance(node.func, ast.Attribute) else
        node.func.id if isinstance(node.func, ast.Name) else ""
        for node in ast.walk(tree) if isinstance(node, ast.Call)
    }
    assert not called & _AMBIENT_CALLS, (
        f"{relative} calls {sorted(called & _AMBIENT_CALLS)} — 'now' is injected"
    )


@pytest.mark.parametrize("relative", RETRIEVAL_MODULES)
def test_retrieval_never_writes(relative):
    """AD-26: ranking weights are volatile and never enter the log. The way
    that gets violated is a retrieval module appending a record, so nothing
    here may reach the write path at all."""
    source = (ROOT / relative).read_text(encoding="utf-8")
    for forbidden in ("store.record(", "store.append(", "log.append(", "Op."):
        assert forbidden not in source, f"{relative} reaches the write path"


@pytest.mark.parametrize("relative", RETRIEVAL_MODULES)
def test_no_retrieval_module_mentions_the_source_corpus(relative):
    assert "sources" not in (ROOT / relative).read_text(encoding="utf-8"), (
        f"{relative} references the source corpus; retrieval targets beliefs"
    )


def test_retrieval_leaves_the_log_byte_identical(beliefs):
    assert_belief(beliefs, "b_1", "flies paragliders", loop="fly-again")
    shards = sorted((beliefs.root / "beliefs").glob("*.jsonl"))
    before = {p: p.read_bytes() for p in shards}

    for _ in range(3):
        retrieve(beliefs, "paragliders")

    assert {p: p.read_bytes() for p in shards} == before


def test_salience_is_derived_and_not_bumped_by_reading(beliefs):
    """The mistake AD-30 exists to prevent: a use-counter makes materialized
    state a function of read traffic rather than of the log."""
    from half.retrieval.salience import parse_time

    assert_belief(beliefs, "b_1", "flies paragliders", independent=3)
    record = beliefs.state().beliefs["b_1"]
    before = salience(record, now=parse_time(NOW), loops={})

    for _ in range(20):
        retrieve(beliefs, "paragliders")

    after = beliefs.state().beliefs["b_1"]
    assert after == record, "reading changed a belief"
    assert salience(after, now=parse_time(NOW), loops={}) == before


def test_growing_the_source_corpus_tenfold_changes_neither_results_nor_work(beliefs):
    """CAP-9: retrieval targets the belief set, so the corpus is irrelevant to
    both the answer and the cost of getting it."""
    for i in range(4):
        assert_belief(beliefs, f"b_{i}", f"shared term here number {i}")

    statements: list[int] = []

    def measure():
        seen: list[str] = []
        beliefs.conn.set_trace_callback(seen.append)
        try:
            result = retrieve(beliefs, "shared term")
        finally:
            beliefs.conn.set_trace_callback(None)
        statements.append(len(seen))
        return result

    # One warm-up: FTS5 primes an internal cache on its first query of a
    # connection, which is a property of the connection and not of the corpus.
    retrieve(beliefs, "shared term")

    sources = beliefs.root / "sources"
    sources.mkdir(parents=True, exist_ok=True)
    for i in range(10):
        (sources / f"s_{i}.json").write_text('{"digest": "x"}', encoding="utf-8")
    before = measure()

    for i in range(10, 110):  # ten times the corpus
        (sources / f"s_{i}.json").write_text('{"digest": "x"}', encoding="utf-8")
    after = measure()

    assert before.ids == after.ids
    assert [c.score for c in before] == [c.score for c in after]
    assert statements[0] == statements[1], "the corpus changed the work done"


# -- an already-deployed main's database -------------------------------------

#: `half/store/db.py` as story 3 shipped it: no prefix column, single-column
#: FTS. Reproduced verbatim rather than derived from the current SCHEMA, because
#: a fixture that derives from the code under test cannot detect the code
#: changing shape — which is precisely what this is here to catch.
STORY_3_SCHEMA = """
CREATE TABLE IF NOT EXISTS beliefs (
    id          TEXT PRIMARY KEY,
    t           TEXT NOT NULL,
    subject     TEXT,
    claim       TEXT,
    ledger      TEXT,
    license     TEXT NOT NULL DEFAULT 'behave',
    independent INTEGER NOT NULL DEFAULT 0,
    data        TEXT NOT NULL
) STRICT;

CREATE TABLE IF NOT EXISTS tensions (id TEXT PRIMARY KEY, data TEXT NOT NULL) STRICT;
CREATE TABLE IF NOT EXISTS loops    (id TEXT PRIMARY KEY, data TEXT NOT NULL) STRICT;
CREATE TABLE IF NOT EXISTS expunged (id TEXT PRIMARY KEY) STRICT;

CREATE VIRTUAL TABLE IF NOT EXISTS belief_fts USING fts5(
    claim,
    content = 'beliefs',
    content_rowid = 'rowid'
);
"""


@pytest.fixture
def deployed_before_the_prefix(tmp_path):
    """A main's directory exactly as the previous release left it: a log, and
    beside it a derived database written against the older schema."""
    import json

    root = tmp_path / "main"
    with Store(root, prefix=build_prefix) as store:
        assert_belief(store, "b_1", "has not been up since the accident",
                      loop="buy-farmland")
    root.joinpath("half.db").unlink()

    record = next(iter(Store(root).log)).data
    conn = sqlite3.connect(root / "half.db")
    try:
        conn.executescript(STORY_3_SCHEMA)
        conn.execute(
            "INSERT INTO beliefs (id,t,subject,claim,ledger,license,independent,data)"
            " VALUES (?,?,?,?,?,?,?,?)",
            ("b_1", record["t"], "self", record["claim"], "revealed", "behave", 0,
             json.dumps(record, sort_keys=True, separators=(",", ":"))),
        )
        conn.execute("INSERT INTO belief_fts(rowid, claim) SELECT rowid, claim"
                     " FROM beliefs")
        conn.commit()
        assert conn.execute("PRAGMA user_version").fetchone()[0] == 0
    finally:
        conn.close()
    return root


def test_an_older_derived_view_is_discarded_and_replayed(deployed_before_the_prefix):
    """SQLite is disposable (AD-3): an upgrade replays rather than migrating.

    This has to build the *previous* schema and open a Store over it. The
    version this replaced forged staleness with ``PRAGMA user_version`` on a
    database that already had the new shape, so it proved nothing: deleting the
    FTS table from the drop list, or making the discard a no-op entirely, both
    left it green.
    """
    with Store(deployed_before_the_prefix, prefix=build_prefix) as store:
        assert "b_1" in store.state().beliefs
        assert store.state().beliefs["b_1"]["claim"].startswith("has not been up")
        # The prefix column now exists and is populated, so a prefix-only query
        # works — this is the read that used to raise on a stale shape.
        assert Retriever(store=store).retrieve("farmland", now=NOW).ids == ("b_1",)


def test_upgrading_an_older_view_never_leaks_a_raw_sqlite_error(
    deployed_before_the_prefix,
):
    """Errors are typed at the boundary; a main upgrading must not meet
    ``sqlite3.OperationalError: table belief_fts has no column named prefix``."""
    try:
        with Store(deployed_before_the_prefix, prefix=build_prefix) as store:
            store.rebuild()
            store.search("farmland")
    except sqlite3.Error as exc:  # pragma: no cover - the failure this guards
        pytest.fail(f"a raw sqlite error escaped: {exc}")
    except StoreError as exc:  # pragma: no cover - typed, but still a failure
        pytest.fail(f"upgrading raised instead of replaying: {exc}")
