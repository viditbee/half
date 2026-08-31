"""Retrieval in every script, not just the ones written with spaces (CAP-9).

One case per row of the story's I/O matrix. Two independent defects are covered
here and they fail in opposite directions:

* **Precision.** ``half.text.words`` used to split on Python's ``\\w``, which
  excludes combining marks, so ``यात्रा`` shattered into ``य``, ``त``, ``र`` and
  the store OR-joined the pieces. A query for ``रात`` ("night") then retrieved a
  belief about travel, because those two consonants appear in almost any
  Devanagari string. Marks now stay with their letter, and the store hands FTS5
  each whole word as a *phrase* — OR stays between words, so a conversational
  turn still matches a belief sharing one of them.

* **Recall.** Japanese, Chinese, Thai, Lao, Khmer and Korean do not space their
  words, so a whole sentence arrived as one ``unicode61`` token and ``転職``
  retrieved nothing at all. Unspaced runs are now n-grammed — at index time and
  at query time, by the same function, because an index n-grammed on one side
  only is worse than the defect it replaces.

The two-character CJK cases are load-bearing rather than decorative: switching
FTS5 to its ``trigram`` tokenizer is the obvious alternative fix, and it returns
nothing for a two-character query, which is the ordinary shape of a Chinese or
Japanese word.
"""

from __future__ import annotations

import json
import sqlite3

import pytest

from half.errors import StoreError, TokenGrowthLimitError
from half.retrieval.prefix import build_prefix
from half.retrieval.rank import Retriever
from half.retrieval.strands import Strands, known_strands
from half.store import db
from half.store.ops import Op
from half.store.store import Store
from half.text import MAX_INPUT_CHARS, MAX_TERMS, index_text, terms, tokens, words

NOW = "2026-08-31T09:00:00Z"


@pytest.fixture
def beliefs(tmp_path):
    """A store wired the way the running product wires it: prefixes indexed."""
    with Store(tmp_path / "main", prefix=build_prefix) as store:
        yield store


def assert_belief(store, ident, claim, **fields):
    fields.setdefault("subject", "self")
    fields.setdefault("ledger", "revealed")
    fields.setdefault("independent", 0)
    t = fields.pop("t", "2026-08-01T00:00:00Z")
    store.record(Op.ASSERT, ident, t, claim=claim, **fields)


def retrieve(store, query, **kw):
    return Retriever(store=store).retrieve(query, now=kw.pop("now", NOW), **kw)


def matched(store, query):
    """The ids a query *term-matched*, as distinct from what the backstop
    supplied. The backstop returns the whole belief set by design (AD-24), so
    any precision assertion has to look at the term match itself."""
    return [hit["id"] for hit in store.search(query)]


# -- the shattering defect ---------------------------------------------------

def test_a_devanagari_word_is_one_word(beliefs):
    """The verified diagnosis, at the unit that produced it. ``\\w`` excludes
    combining marks, so the matra split the word into bare consonants."""
    assert words("यात्रा") == ["यात्रा"]
    assert words("रात") == ["रात"]
    assert words("आशा से बात हुई") == ["आशा", "से", "बात", "हुई"]


def test_an_unrelated_devanagari_word_does_not_retrieve_a_travel_belief(beliefs):
    """``रात`` is "night" and shares not one word with the belief. The shattered
    OR made those two consonants match it anyway."""
    assert_belief(beliefs, "b_1", "यात्रा की योजना बना रहा है", loop="यात्रा-plan")

    assert matched(beliefs, "रात") == []
    result = retrieve(beliefs, "रात")
    assert result.ids == ("b_1",), "the backstop still reaches every belief"
    assert all(c.bm25 is None for c in result), "रात term-matched a travel belief"


def test_the_devanagari_word_the_belief_is_about_does_retrieve_it(beliefs):
    assert_belief(beliefs, "b_1", "यात्रा की योजना बना रहा है")
    assert_belief(beliefs, "b_2", "flies paragliders on weekends")

    assert matched(beliefs, "यात्रा") == ["b_1"]
    assert retrieve(beliefs, "यात्रा")[0].id == "b_1"


# -- Latin must not regress --------------------------------------------------

LATIN = (
    "flies paragliders on weekends",
    "replies to his mother within three minutes",
    "café-plans",
    "well-formed user_name 2026",
)


@pytest.mark.parametrize("text", LATIN)
def test_n_gramming_never_touches_a_spaced_script(text):
    """A Latin word is one term, exactly as before. If this drifts, every
    ranking test in the suite is measuring a different tokenizer."""
    assert terms(text) == words(text)
    assert index_text(text) == " ".join(words(text))


def test_a_latin_corpus_retrieves_in_a_stable_order(beliefs):
    assert_belief(beliefs, "b_z", "flies paragliders on weekends")
    assert_belief(beliefs, "b_a", "flies paragliders every winter")

    assert matched(beliefs, "paragliders") == ["b_a", "b_z"]
    assert matched(beliefs, "weekends") == ["b_z"]


def test_a_conversational_turn_still_matches_a_belief_sharing_one_word(beliefs):
    """OR stays between words. Phrase-quoting a whole turn matched only a
    belief repeating it verbatim — a real story-4 defect that must not return."""
    assert_belief(beliefs, "b_1", "flies paragliders on weekends")

    turn = "been thinking about whether I should sell the paragliders honestly"
    assert matched(beliefs, turn) == ["b_1"]


# -- scriptio continua -------------------------------------------------------

def test_a_word_inside_an_unspaced_japanese_sentence_is_findable(beliefs):
    """The sentence is one ``unicode61`` token, so before the n-grams this
    retrieved nothing at all."""
    assert_belief(beliefs, "b_1", "転職を考えている")

    assert matched(beliefs, "転職") == ["b_1"]


def test_a_two_character_cjk_word_retrieves(beliefs):
    """The case ``trigram`` cannot serve: it returns nothing under three
    characters, and two-character words are the ordinary shape here."""
    assert_belief(beliefs, "b_1", "来年は旅行に行きたい")

    assert matched(beliefs, "旅行") == ["b_1"]


def test_a_word_inside_an_unspaced_thai_sentence_is_findable(beliefs):
    assert_belief(beliefs, "b_1", "ผมกำลังคิดจะเปลี่ยนงาน")

    assert matched(beliefs, "เปลี่ยน") == ["b_1"]


#: A belief and a query in each script, none of them sharing a word with
#: another. Korean is here rather than with the CJK cases because it *is*
#: spaced — but it glues its particles onto the noun, so ``이직을`` is one token
#: and a query for ``이직`` misses it without the same n-gram treatment.
SCRIPTS = {
    "korean": ("이직을 고민하고 있다", "이직"),
    "cyrillic": ("думает о смене работы", "смене"),
    "hebrew": ("חושב על החלפת עבודה", "החלפת"),
    "arabic": ("يفكر في تغيير وظيفته", "تغيير"),
    "greek": ("σκέφτεται να αλλάξει δουλειά", "αλλάξει"),
    "tamil": ("வேலையை மாற்ற நினைக்கிறார்", "மாற்ற"),
}


@pytest.mark.parametrize("script", sorted(SCRIPTS))
def test_a_belief_is_retrieved_by_a_matching_query_in_its_own_script(
    beliefs, script
):
    claim, query = SCRIPTS[script]
    assert_belief(beliefs, "b_1", claim)
    assert_belief(beliefs, "b_2", "flies paragliders on weekends")

    assert matched(beliefs, query) == ["b_1"], f"{script} did not retrieve"


def test_both_halves_of_a_mixed_script_claim_are_findable(beliefs):
    assert_belief(beliefs, "b_1", "planning a 転職 next spring")

    assert matched(beliefs, "転職") == ["b_1"]
    assert matched(beliefs, "planning") == ["b_1"]


def test_a_script_transition_inside_one_word_splits_into_runs(beliefs):
    """``転職plan`` is one ``\\w`` run and two scripts. The CJK half is
    n-grammed and the Latin half is left alone."""
    assert_belief(beliefs, "b_1", "keeps putting it off", loop="転職plan")

    assert matched(beliefs, "転職") == ["b_1"]
    assert matched(beliefs, "plan") == ["b_1"]


# -- emoji is ordinary input -------------------------------------------------

def test_emoji_is_ordinary_input_in_a_claim_and_in_a_query(beliefs):
    assert_belief(beliefs, "b_1", "loves 😀 sunsets")

    assert terms("😀") == [], "an emoji carries no term for either side"
    assert matched(beliefs, "sunsets") == ["b_1"]
    assert matched(beliefs, "😀") == []
    # Never a crash, and never an empty candidate set (AD-24).
    assert retrieve(beliefs, "😀 😀").ids == ("b_1",)


def test_a_claim_that_is_only_emoji_neither_crashes_nor_disappears(beliefs):
    assert_belief(beliefs, "b_1", "😀🎈")

    assert "b_1" in beliefs.state().beliefs
    assert retrieve(beliefs, "anything at all").ids == ("b_1",)


# -- the growth bound --------------------------------------------------------

def test_an_unspaced_run_past_the_term_ceiling_raises(beliefs):
    """N-gramming multiplies term counts, so the bound is explicit and it is an
    error. Silently dropping the tail would leave a belief indexed by its first
    half and unreachable by its second, with nothing saying so."""
    run = "転" * 7_000  # 3n-3 = 20,997 terms

    with pytest.raises(TokenGrowthLimitError):
        terms(run)
    with pytest.raises(TokenGrowthLimitError):
        assert_belief(beliefs, "b_1", run)

    assert list(beliefs.log) == [], "the refused record reached the log"
    assert beliefs.state().beliefs == {}


def test_text_past_the_input_ceiling_raises_before_any_expansion(beliefs):
    with pytest.raises(TokenGrowthLimitError):
        terms("転" * (MAX_INPUT_CHARS + 1))
    with pytest.raises(TokenGrowthLimitError):
        terms("a " * MAX_INPUT_CHARS)


def test_a_long_spaced_run_stays_within_the_ceiling(beliefs):
    """The bound is on growth, not on length: a Latin sentence of the same size
    emits one term per word and must still index."""
    text = " ".join(f"w{i}" for i in range(1_000))
    assert len(text) < MAX_INPUT_CHARS
    assert len(terms(text)) == 1_000 <= MAX_TERMS
    assert_belief(beliefs, "b_1", text)
    assert matched(beliefs, "w999") == ["b_1"]


def test_an_oversized_query_raises_rather_than_searching_a_shortened_one(beliefs):
    assert_belief(beliefs, "b_1", "flies paragliders")

    with pytest.raises(TokenGrowthLimitError):
        beliefs.search("転" * 7_000)


# -- the prefix and the strand matcher, in every script ----------------------

def test_a_non_latin_subject_and_loop_are_indexed_and_findable(beliefs):
    assert_belief(beliefs, "b_1", "keeps putting it off",
                  subject="आशा", loop="転職-plan")

    prefix = build_prefix(beliefs.state().beliefs["b_1"])
    assert "आशा" in prefix and "転職" in prefix
    assert matched(beliefs, "आशा") == ["b_1"]
    assert matched(beliefs, "転職") == ["b_1"]


def test_a_strand_named_in_an_unspaced_script_becomes_live():
    """The label sits inside a sentence that never spaced it, so a matcher
    without n-grams finds no overlap and the strand is never weighted."""
    strands = Strands()
    strands.observe("転職を考えている", {"loop:転職", "person:आशा"})

    assert strands.weights.get("loop:転職", 0.0) > 0.0
    assert "person:आशा" not in strands.weights


def test_a_devanagari_person_named_in_a_message_becomes_live():
    strands = Strands()
    strands.observe("आशा से बात हुई", {"person:आशा", "loop:buy-farmland"})

    assert strands.weights.get("person:आशा", 0.0) > 0.0
    assert "loop:buy-farmland" not in strands.weights


def test_the_live_turn_weights_a_non_latin_loop_it_just_heard(beliefs):
    assert_belief(beliefs, "b_1", "まだ決めていない", loop="転職")
    state = beliefs.state()
    strands = Strands()
    strands.observe("転職を考えている",
                    known_strands(state.beliefs.values(), state.loops))

    assert retrieve(beliefs, "転職", strands=strands).ids == ("b_1",)


def test_tokens_fold_the_way_the_index_folds(beliefs):
    """Half's own comparisons must agree with unicode61's folding, in every
    script — and an unspaced run must fold to the same terms both sides."""
    assert tokens("Café") == tokens("cafe")
    assert tokens("ज़मीन") == tokens("जमीन")
    assert "転職" in tokens("転職を考えている")


# -- an already-deployed main's database -------------------------------------

#: `half/store/db.py` as story 4b shipped it: a ``prefix`` column, and an FTS
#: table indexing the raw ``claim`` and ``prefix`` text rather than their terms.
#: Reproduced verbatim rather than derived from the current SCHEMA, because a
#: fixture that derives from the code under test cannot detect the code changing
#: shape — which is precisely what this is here to catch.
STORY_4B_SCHEMA = """
CREATE TABLE IF NOT EXISTS beliefs (
    id          TEXT PRIMARY KEY,
    t           TEXT NOT NULL,
    subject     TEXT,
    claim       TEXT,
    prefix      TEXT,
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
    prefix,
    content = 'beliefs',
    content_rowid = 'rowid'
);
"""

#: What ``PRAGMA user_version`` held when that schema was the current one.
STORY_4B_VERSION = 2


@pytest.fixture
def deployed_before_the_ngrams(tmp_path):
    """A main's directory as the previous release left it: a log, and beside it
    a derived database written against the schema before this bump."""
    root = tmp_path / "main"
    with Store(root, prefix=build_prefix) as store:
        assert_belief(store, "b_1", "転職を考えている", loop="転職-plan")
    root.joinpath("half.db").unlink()

    record = next(iter(Store(root).log)).data
    conn = sqlite3.connect(root / "half.db")
    try:
        conn.executescript(STORY_4B_SCHEMA)
        conn.execute(
            "INSERT INTO beliefs (id,t,subject,claim,prefix,ledger,license,"
            "independent,data) VALUES (?,?,?,?,?,?,?,?,?)",
            ("b_1", record["t"], "self", record["claim"],
             build_prefix(record), "revealed", "behave", 0,
             json.dumps(record, sort_keys=True, separators=(",", ":"),
                        ensure_ascii=False)),
        )
        conn.execute("INSERT INTO belief_fts(rowid, claim, prefix)"
                     " SELECT rowid, claim, prefix FROM beliefs")
        conn.execute(f"PRAGMA user_version = {STORY_4B_VERSION}")
        conn.commit()
        assert conn.execute("PRAGMA user_version").fetchone()[0] == STORY_4B_VERSION
    finally:
        conn.close()
    return root


def test_the_derived_version_was_bumped_for_the_new_indexed_content():
    """The index holds different text now, so an older view cannot be queried —
    which is what the discard-and-replay path is for (AD-3)."""
    assert db.DERIVED_VERSION > STORY_4B_VERSION


def test_an_older_derived_view_is_discarded_and_replayed(deployed_before_the_ngrams):
    with Store(deployed_before_the_ngrams, prefix=build_prefix) as store:
        assert "b_1" in store.state().beliefs
        # The read that the older index could not serve: the query is a word
        # inside an unspaced sentence, findable only through the n-grams.
        assert matched(store, "転職") == ["b_1"]


def test_upgrading_an_older_view_never_leaks_a_raw_sqlite_error(
    deployed_before_the_ngrams,
):
    """A main upgrading must not meet ``sqlite3.OperationalError: table
    belief_fts has no column named claim_terms``."""
    try:
        with Store(deployed_before_the_ngrams, prefix=build_prefix) as store:
            store.rebuild()
            store.search("転職")
    except sqlite3.Error as exc:  # pragma: no cover - the failure this guards
        pytest.fail(f"a raw sqlite error escaped: {exc}")
    except StoreError as exc:  # pragma: no cover - typed, but still a failure
        pytest.fail(f"upgrading raised instead of replaying: {exc}")


def test_replaying_a_non_latin_log_reproduces_identical_state(beliefs):
    """AD-4 does not care what script the claims are written in."""
    assert_belief(beliefs, "b_1", "転職を考えている", loop="転職-plan")
    assert_belief(beliefs, "b_2", "यात्रा की योजना बना रहा है", subject="आशा")
    assert_belief(beliefs, "b_3", "ผมกำลังคิดจะเปลี่ยนงาน")
    before = beliefs.state().canonical_json()

    beliefs.close()
    beliefs.db_path.unlink()

    assert beliefs.rebuild().canonical_json() == before
    assert matched(beliefs, "転職") == ["b_1"]
