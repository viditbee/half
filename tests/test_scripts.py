"""Retrieval in every script, not just the ones written with spaces (CAP-9).

One case per row of the story's I/O matrix, and the matrix is deliberately
**symmetric**: every script that gets a recall case gets a precision case beside
it. The first version of this file was not, and the asymmetry hid a real defect.
It carried ``रात`` must-not-retrieve for Devanagari but only positive cases for
the unspaced scripts — and the implementation under it OR'd single characters,
so ``search("転職")`` returned a belief about severance pay and
``search("เปลี่ยนงาน")`` returned one about sticky rice. The recall tests passed
on that noise. A precision case is not a nicety here; it is the only thing that
can tell a working mechanism from a broken one.

Two defects are covered, and they fail in opposite directions:

* **Precision.** ``half.text.words`` used to split on Python's ``\\w``, which
  excludes combining marks, so ``यात्रा`` shattered into ``य``, ``त``, ``र``.
  Marks now stay with their letter, and each whole word goes to FTS5 as a
  *phrase* — OR stays between words, so a conversational turn still matches a
  belief sharing one of them.

* **Recall.** Japanese, Chinese, Thai, Lao, Khmer and Korean do not space their
  words, so a whole sentence arrived as one ``unicode61`` token and ``転職``
  retrieved nothing at all. Such a run is now cut into grapheme clusters and
  queried as the phrase of the same clusters — one expansion, both sides.

**Constants are pinned behaviourally.** Every script class, the cluster
expansion and both ceilings are asserted through what retrieval *returns*, with
literal numbers rather than the constants themselves. A test written in terms of
the constant it guards cannot observe that constant being wrong.
"""

from __future__ import annotations

import asyncio
import json
import sqlite3
import unicodedata

import pytest

from half.actor.registry import ActorRegistry
from half.actor.runtime import Runtime
from half.channel.telegram import TelegramChannel
from half.context.build import _units
from half.errors import (
    QueryTooLargeError,
    StoreError,
    TokenGrowthLimitError,
)
from half.retrieval.prefix import build_prefix
from half.retrieval.rank import Retriever
from half.retrieval.strands import Strands, known_strands
from half.store import db
from half.store.ops import Op
from half.store.store import Store
from half.text import (
    UNSPACED_SCRIPTS,
    index_text,
    is_unspaced,
    normalize,
    phrases,
    terms,
    tokens,
    words,
)

from tests.conftest import FakeTransport, a_voice, msg

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
    every precision assertion has to look at the term match itself."""
    return [hit["id"] for hit in store.search(query)]


# -- the two defects this story exists to remove -----------------------------

def test_a_devanagari_word_is_one_word():
    """The verified diagnosis, at the unit that produced it. ``\\w`` excludes
    combining marks, so the matra split the word into bare consonants."""
    assert words("यात्रा") == ["यात्रा"]
    assert words("रात") == ["रात"]
    assert words("आशा से बात हुई") == ["आशा", "से", "बात", "हुई"]


def test_an_unrelated_devanagari_word_does_not_retrieve_a_travel_belief(beliefs):
    """``रात`` is "night" and shares not one word with the belief."""
    assert_belief(beliefs, "b_1", "यात्रा की योजना बना रहा है", loop="यात्रा-plan")

    assert matched(beliefs, "रात") == []
    result = retrieve(beliefs, "रात")
    assert result.ids == ("b_1",), "the backstop still reaches every belief"
    assert all(c.bm25 is None for c in result), "रात term-matched a travel belief"


def test_the_devanagari_word_the_belief_is_about_does_retrieve_it(beliefs):
    assert_belief(beliefs, "b_1", "यात्रा की योजना बना रहा है")
    assert_belief(beliefs, "b_2", "flies paragliders on weekends")

    assert matched(beliefs, "यात्रा") == ["b_1"]


def test_an_unrelated_cjk_word_does_not_retrieve(beliefs):
    """The regression this file's first version shipped. ``転職`` (changing
    jobs) and ``退職金`` (severance pay) share the character 職 and nothing
    else; OR-ing unigrams made one shared character enough."""
    assert_belief(beliefs, "b_sever", "退職金の話をした")

    assert matched(beliefs, "転職") == []
    assert all(c.bm25 is None for c in retrieve(beliefs, "転職"))


def test_an_unrelated_thai_word_does_not_retrieve(beliefs):
    """Same defect, same shape: ``เปลี่ยนงาน`` (change jobs) retrieved a belief
    about sticky rice, on shared characters alone."""
    assert_belief(beliefs, "b_rice", "เขาชอบกินข้าวเหนียว")

    assert matched(beliefs, "เปลี่ยนงาน") == []
    assert all(c.bm25 is None for c in retrieve(beliefs, "เปลี่ยนงาน"))


def test_precision_and_recall_hold_in_one_store(beliefs):
    """Both directions at once, which is the only arrangement that can catch a
    mechanism that matches everything."""
    assert_belief(beliefs, "b_job", "転職を考えている")
    assert_belief(beliefs, "b_sever", "退職金の話をした")

    assert matched(beliefs, "転職") == ["b_job"]
    assert matched(beliefs, "退職") == ["b_sever"]


def test_a_word_inside_an_unspaced_japanese_sentence_is_findable(beliefs):
    """The sentence is one ``unicode61`` token, so before the clusters this
    retrieved nothing at all."""
    assert_belief(beliefs, "b_1", "転職を考えている")

    assert matched(beliefs, "転職") == ["b_1"]


def test_a_two_character_cjk_word_retrieves(beliefs):
    """The case ``trigram`` cannot serve: it returns nothing under three
    characters, and two-character words are the ordinary shape here."""
    assert_belief(beliefs, "b_1", "来年は旅行に行きたい")
    assert_belief(beliefs, "b_2", "退職金の話をした")

    assert matched(beliefs, "旅行") == ["b_1"]


def test_a_one_character_query_retrieves(beliefs):
    """The recall case that forbids "just drop the unigrams" as the fix for the
    precision defect. A single character is a whole word in Chinese and
    Japanese, and a phrase of one token still matches."""
    assert_belief(beliefs, "b_1", "愛について考えている")
    assert_belief(beliefs, "b_2", "退職金の話をした")

    assert matched(beliefs, "愛") == ["b_1"]


def test_a_word_inside_an_unspaced_thai_sentence_is_findable(beliefs):
    assert_belief(beliefs, "b_1", "ผมกำลังคิดจะเปลี่ยนงาน")
    assert_belief(beliefs, "b_2", "เขาชอบกินข้าวเหนียว")

    assert matched(beliefs, "เปลี่ยนงาน") == ["b_1"]
    assert matched(beliefs, "ข้าวเหนียว") == ["b_2"]


# -- grapheme integrity ------------------------------------------------------

#: Words whose graphemes span several codepoints: Khmer coeng-subjoined
#: consonants and dependent vowels, Thai vowel signs and tone marks.
GRAPHEME_WORDS = ("ភាសាខ្មែរ", "គាត់ចង់ប្តូរការងារ", "เปลี่ยนงาน", "ข้าวเหนียว")


@pytest.mark.parametrize("word", GRAPHEME_WORDS)
def test_no_index_term_begins_on_a_bare_mark(word):
    """Slicing at raw codepoint offsets undid the mark-preserving fix one layer
    below it: ``terms("ភាសាខ្មែរ")`` began ``['ភ','ស','ខ','ម','រ','ភា','ាស',...]``
    — dependent vowels stripped off and bigrams starting mid-grapheme."""
    for term in terms(word):
        first = term[0]
        assert not unicodedata.category(first).startswith("M"), (
            f"term {term!r} of {word!r} begins on a combining mark"
        )


@pytest.mark.parametrize("word", GRAPHEME_WORDS + ("あ゙い",))
def test_cutting_a_word_into_clusters_loses_no_character(word):
    """The expansion re-joins to the word it came from.

    This is what keeps a combining mark with the letter it modifies once the
    word is cut up. ``U+3099``, the voiced sound mark, is named ``COMBINING
    KATAKANA-HIRAGANA VOICED SOUND MARK`` — so classifying it on its own name
    rather than letting it inherit the run it sits in ends the kana run at the
    dakuten, and the mark is then dropped on the floor.

    Pinned here rather than through retrieval because ``unicode61`` treats every
    combining mark as a separator, so it flattens ``あ゙`` and ``あ`` to one token
    at match time and no query can tell the two apart. The invariant still has
    to hold: the tokenizer is what a future index change would rest on.
    """
    assert "".join(terms(word)) == word


@pytest.mark.parametrize("word", GRAPHEME_WORDS + ("่งาน",))
def test_no_term_is_a_bare_mark(word):
    """A term with no letter in it matches nothing on either side while still
    spending the growth budget. A word can begin with an orphan mark — a Thai
    tone mark leading a paste — and that mark is its own cluster."""
    for term in terms(word):
        assert any(ch.isalnum() for ch in term), f"{term!r} carries no letter"


def test_a_khmer_cluster_keeps_its_vowel_and_its_subjoined_consonant():
    """A coeng binds the letter after it into the same grapheme, so ``ខ្មែ`` is
    one cluster rather than ``ខ្`` and ``មែ``."""
    assert terms("ភាសាខ្មែរ") == ["ភា", "សា", "ខ្មែ", "រ"]


def test_a_khmer_word_retrieves_from_an_unspaced_khmer_sentence(beliefs):
    assert_belief(beliefs, "b_1", "គាត់ចង់ប្តូរការងារ")
    assert_belief(beliefs, "b_2", "ភាសាខ្មែរពិបាករៀន")

    assert matched(beliefs, "ការងារ") == ["b_1"]
    assert matched(beliefs, "ភាសា") == ["b_2"]


# -- every script class, pinned by what retrieval returns --------------------

#: One sample per entry of ``half.text.UNSPACED_SCRIPTS``, plus a halfwidth form
#: to pin the width-prefix stripping. Six characters each: the first three
#: become one belief, the last three an unrelated belief in the *same* script,
#: and the query is the first two — so recall and precision are both asserted
#: from disjoint character sets rather than from language knowledge.
#:
#: Deliberately not derived from ``half.text``: a fixture built by the code
#: under test cannot notice that code changing shape. ``test_every_sample_is_the
#: _script_it_claims`` checks them against ``unicodedata`` instead.
SCRIPT_SAMPLES: dict[str, str] = {
    "CJK": "㐀㐁㐂㐃㐄㐅",
    "IDEOGRAPHIC": "々〆〇㆒㆓㆔",
    "HIRAGANA": "ぁあぃいぅう",
    "KATAKANA": "ァアィイゥウ",
    "HANGUL": "ᄀᄁᄂᄃᄄᄅ",
    "BOPOMOFO": "ㄅㄆㄇㄈㄉㄊ",
    "THAI": "กขฃคฅฆ",
    "LAO": "ກຂຄຆງຈ",
    "KHMER": "កខគឃងច",
    "MYANMAR": "ကခဂဃငစ",
    "TIBETAN": "ༀ༠༡༢༣༤",
    "JAVANESE": "ꦄꦅꦆꦇꦈꦉ",
    "BALINESE": "ᬅᬆᬇᬈᬉᬊ",
    "SUNDANESE": "ᮃᮄᮅᮆᮇᮈ",
    "TAI THAM": "ᨠᨡᨢᨣᨤᨥ",
    "TAI LE": "ᥐᥑᥒᥓᥔᥕ",
    "TAI VIET": "ꪀꪁꪂꪃꪄꪅ",
    "NEW TAI LUE": "ᦀᦁᦂᦃᦄᦅ",
    # Halfwidth katakana: the same script under a width prefix in its name.
    "KATAKANA (halfwidth)": "ｦｧｨｩｪｫ",
}


def _script_of(char: str) -> str:
    """The character's script, read off its Unicode name by this test itself."""
    name = unicodedata.name(char, "")
    for prefix in ("HALFWIDTH ", "FULLWIDTH "):
        if name.startswith(prefix):
            return name[len(prefix):]
    return name


def test_every_unspaced_script_class_has_a_retrieval_case():
    """The rule that keeps the table honest: a class no test can remove is a
    class that will be removed. Eleven of the twenty codepoint ranges this
    replaced could each be deleted with the whole suite green."""
    covered = {script.split(" (")[0] for script in SCRIPT_SAMPLES}
    assert covered == set(UNSPACED_SCRIPTS), (
        "every entry of UNSPACED_SCRIPTS needs a sample, and every sample needs "
        "an entry"
    )


@pytest.mark.parametrize("script", sorted(SCRIPT_SAMPLES))
def test_every_sample_is_the_script_it_claims(script):
    sample = SCRIPT_SAMPLES[script]
    expected = script.split(" (")[0]
    assert len(sample) == 6
    assert unicodedata.normalize("NFC", sample) == sample, "sample must be NFC"
    for char in sample:
        assert _script_of(char).startswith(expected), (
            f"{char!r} is {_script_of(char)!r}, not {expected}"
        )
        assert is_unspaced(char), f"{char!r} is not classified as unspaced"


@pytest.fixture(scope="module")
def every_script(tmp_path_factory):
    """One store holding every script at once.

    Per-script stores were the earlier arrangement and they cannot catch a
    cross-script collision — each query only ever had its own belief and a Latin
    decoy to choose between. Here every query has every other script's beliefs
    to wrongly match, which is the arrangement that would have caught the
    unigram defect on the day it was written.
    """
    root = tmp_path_factory.mktemp("scripts") / "main"
    with Store(root, prefix=build_prefix) as store:
        for index, sample in enumerate(SCRIPT_SAMPLES.values()):
            assert_belief(store, f"b_{index:02d}_a", sample[:3])
            assert_belief(store, f"b_{index:02d}_b", sample[3:])
        assert_belief(store, "b_99_latin", "flies paragliders on weekends")
        yield store


@pytest.mark.parametrize("script", sorted(SCRIPT_SAMPLES))
def test_each_script_retrieves_only_its_own_belief(every_script, script):
    index = list(SCRIPT_SAMPLES).index(script)
    sample = SCRIPT_SAMPLES[script]

    assert matched(every_script, sample[:2]) == [f"b_{index:02d}_a"], (
        f"{script}: a query drawn only from this script must retrieve this "
        "script's belief and nothing else"
    )


# -- the other scripts in the matrix -----------------------------------------

#: A belief and a matching query in each. Korean is here rather than with the
#: unspaced cases because it *is* spaced — but it glues its particles onto the
#: noun, so ``이직을`` is one token and a query for ``이직`` would miss it
#: without the same cluster treatment.
SCRIPTS = {
    "korean": ("이직을 고민하고 있다", "이직", "직업을 바꾸고 싶다"),
    "cyrillic": ("думает о смене работы", "смене", "любит гулять вечером"),
    "hebrew": ("חושב על החלפת עבודה", "החלפת", "אוהב לשחק כדורגל"),
    "arabic": ("يفكر في تغيير وظيفته", "تغيير", "يحب القهوة كثيرا"),
    "greek": ("σκέφτεται να αλλάξει δουλειά", "αλλάξει", "αγαπάει τη θάλασσα"),
    "tamil": ("வேலையை மாற்ற நினைக்கிறார்", "மாற்ற", "காபி மிகவும் பிடிக்கும்"),
    "chinese": ("正在考虑换工作", "工作", "喜欢吃辣的东西"),
    "lao": ("ລາວຢາກປ່ຽນວຽກ", "ປ່ຽນ", "ມັກກິນເຂົ້າໜຽວ"),
    "myanmar": ("အလုပ်ပြောင်းချင်တယ်", "အလုပ်", "ကော်ဖီကြိုက်တယ်"),
}


@pytest.mark.parametrize("script", sorted(SCRIPTS))
def test_a_belief_is_retrieved_by_a_matching_query_in_its_own_script(
    beliefs, script
):
    """Recall and precision together: the query word belongs to the first
    belief, and the second belief is an unrelated one in the same script."""
    claim, query, unrelated = SCRIPTS[script]
    assert_belief(beliefs, "b_1", claim)
    assert_belief(beliefs, "b_2", unrelated)
    assert_belief(beliefs, "b_3", "flies paragliders on weekends")

    assert matched(beliefs, query) == ["b_1"], f"{script} retrieved wrongly"


def test_both_halves_of_a_mixed_script_claim_are_findable(beliefs):
    assert_belief(beliefs, "b_1", "planning a 転職 next spring")
    assert_belief(beliefs, "b_2", "退職金の話をした")

    assert matched(beliefs, "転職") == ["b_1"]
    assert matched(beliefs, "planning") == ["b_1"]


def test_a_script_transition_inside_one_word_splits_into_runs(beliefs):
    """``転職plan`` is one ``\\w`` run and two scripts. The CJK half is cut into
    clusters and the Latin half is left whole."""
    assert_belief(beliefs, "b_1", "keeps putting it off", loop="転職plan")

    assert matched(beliefs, "転職") == ["b_1"]
    assert matched(beliefs, "plan") == ["b_1"]


# -- Latin must not regress --------------------------------------------------

LATIN = (
    "flies paragliders on weekends",
    "replies to his mother within three minutes",
    "café-plans",
    "well-formed user_name 2026",
)


@pytest.mark.parametrize("text", LATIN)
def test_a_spaced_script_is_never_cut_up(text):
    """A Latin word is one term and one phrase, exactly as before. If this
    drifts, every ranking test in the suite is measuring a different
    tokenizer."""
    assert terms(text) == words(text)
    assert phrases(text) == words(text)
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


def test_a_bare_operator_word_is_searched_as_an_ordinary_word(beliefs):
    """``AND``, ``OR`` and ``NOT`` in capitals are fts5 operators and an
    ordinary thing for a main to type. Unquoted, ``NOT sure about the
    paragliders`` is a syntax error that reaches the main as silence — the
    existing ``NEAR(`` test cannot catch it, because the tokenizer strips the
    bracket and leaves the harmless bareword ``NEAR``."""
    assert_belief(beliefs, "b_1", "flies paragliders on weekends")

    for turn in (
        "NOT sure about the paragliders",
        "paragliders AND weekends",
        "weekends OR paragliders",
        "AND",
        "NOT",
    ):
        assert matched(beliefs, turn) in ([], ["b_1"]), turn
    assert matched(beliefs, "NOT sure about the paragliders") == ["b_1"]


# -- a result carries the belief's own words ---------------------------------

def test_a_retrieved_claim_is_byte_identical_to_what_was_recorded(beliefs):
    """The index text and the belief's words live in adjacent columns, and the
    wrong one reaching the main is n-gram soup arriving as quotable content.
    Latin cannot catch this: the two are identical there."""
    claim = "転職を考えている"
    assert_belief(beliefs, "b_1", claim)
    assert index_text(claim) != claim, "the fixture must distinguish the two"

    assert beliefs.search("転職")[0]["claim"] == claim
    rows = db.search_beliefs(beliefs.conn, "転職")
    assert rows[0]["claim"] == claim
    assert rows[0]["belief"]["claim"] == claim
    # The one that reaches a main: the context builder quotes Candidate.claim.
    assert retrieve(beliefs, "転職")[0].claim == claim


def test_the_index_holds_one_term_per_cluster_and_no_n_grams():
    """N-grams in the index inflated an unspaced claim's length about
    thirteenfold, which systematically penalised it against Latin under bm25 and
    made nearly every CJK belief match nearly every CJK query. The phrase does
    that job now, so the index carries clusters and nothing more."""
    claim = "転職を考えている"
    assert index_text(claim) == "転 職 を 考 え て い る"
    assert len(terms(claim)) == len(claim)
    assert len(set(terms("転職転職"))) == len(set("転職")), "no duplicate inflation"


def test_the_backstop_still_fires_for_an_unspaced_script(beliefs):
    """AD-24's "no term matched, so rank the whole set" path stopped firing for
    unspaced scripts when nearly everything matched everything."""
    assert_belief(beliefs, "b_1", "退職金の話をした")
    assert_belief(beliefs, "b_2", "来年は旅行に行きたい")

    result = retrieve(beliefs, "転職")
    assert set(result.ids) == {"b_1", "b_2"}
    assert all(c.bm25 is None for c in result), "these should be backstop hits"


# -- emoji, invisible characters, normalization ------------------------------

def test_emoji_is_ordinary_input_in_a_claim_and_in_a_query(beliefs):
    assert_belief(beliefs, "b_1", "loves 😀 sunsets")

    assert terms("😀") == [], "an emoji carries no term for either side"
    assert matched(beliefs, "sunsets") == ["b_1"]
    assert matched(beliefs, "😀") == []
    assert retrieve(beliefs, "😀 😀").ids == ("b_1",)


def test_a_claim_that_is_only_emoji_neither_crashes_nor_disappears(beliefs):
    assert_belief(beliefs, "b_1", "😀🎈")

    assert "b_1" in beliefs.state().beliefs
    assert retrieve(beliefs, "anything at all").ids == ("b_1",)


def test_an_invisible_character_neither_splits_a_word_nor_joins_two(beliefs):
    """A soft hyphen from a paste, or a ZWJ controlling an Indic ligature, must
    not make one word into two. The AD-18 drop rule already worked this way."""
    assert words("cafe­plans") == ["cafeplans"]
    assert words("क्‍ष") == ["क्ष"]
    assert words("one‍two three") == ["onetwo", "three"]

    assert_belief(beliefs, "b_1", "les plans du cafe­plans")
    assert matched(beliefs, "cafeplans") == ["b_1"]


def test_a_decomposed_query_finds_a_composed_belief(beliefs):
    """macOS, several IMEs and cross-platform paste all produce NFD. Without
    normalizing both sides, an NFD query returns nothing at all."""
    composed = unicodedata.normalize("NFC", "이직을 고민하고 있다")
    decomposed = unicodedata.normalize("NFD", "이직")
    assert decomposed != unicodedata.normalize("NFC", "이직")

    assert_belief(beliefs, "b_1", composed)
    assert matched(beliefs, decomposed) == ["b_1"]
    assert matched(beliefs, unicodedata.normalize("NFD", "café")) == []


def test_a_decomposed_latin_query_finds_a_composed_belief(beliefs):
    assert_belief(beliefs, "b_1", "keeps putting it off",
                  loop=unicodedata.normalize("NFC", "café-plans"))

    assert matched(beliefs, unicodedata.normalize("NFD", "café")) == ["b_1"]
    assert matched(beliefs, "cafe") == ["b_1"]


# -- the ceilings, pinned from both sides with literals ----------------------

def test_an_unspaced_run_past_the_term_ceiling_raises(beliefs):
    """The term ceiling. Literal numbers, not the constant: a test written in
    terms of ``MAX_TERMS`` cannot observe ``MAX_TERMS`` being wrong."""
    with pytest.raises(TokenGrowthLimitError):
        terms("転" * 6_500)
    with pytest.raises(TokenGrowthLimitError):
        assert_belief(beliefs, "b_1", "転" * 6_500)

    assert list(beliefs.log) == [], "the refused record reached the log"
    assert beliefs.state().beliefs == {}


def test_an_unspaced_run_below_the_term_ceiling_is_indexed(beliefs):
    """The other side of the same bound. Lowering the ceiling must fail here."""
    assert len(terms("転" * 5_000)) == 5_000
    assert_belief(beliefs, "b_1", "転" * 5_000)
    assert matched(beliefs, "転転") == ["b_1"]


def test_text_past_the_character_ceiling_raises():
    """The input ceiling, reached by spaced text, which emits one term per word
    and so never meets the term ceiling first."""
    with pytest.raises(TokenGrowthLimitError):
        terms("a" * 9_000)
    with pytest.raises(TokenGrowthLimitError):
        terms("ab " * 3_000)


def test_a_long_spaced_text_below_the_character_ceiling_is_indexed(beliefs):
    """Raising the character ceiling to something enormous must fail the test
    above; lowering it must fail this one."""
    text = " ".join(f"word{i}" for i in range(950))
    assert 7_000 < len(text) < 8_000
    assert len(terms(text)) == 950
    assert_belief(beliefs, "b_1", text)
    assert matched(beliefs, "word949") == ["b_1"]


def test_an_oversized_query_is_a_typed_store_error(beliefs):
    """Never a bare tokenizer exception across the store boundary, and never a
    silently shortened query either."""
    assert_belief(beliefs, "b_1", "flies paragliders")

    with pytest.raises(QueryTooLargeError) as caught:
        beliefs.search("転" * 6_500)
    assert isinstance(caught.value, StoreError)
    assert isinstance(caught.value.__cause__, TokenGrowthLimitError)


# -- no record that passes validation may brick the store --------------------

def test_an_oversized_list_field_is_refused_before_the_append(beliefs):
    """``people`` and ``topics`` are tokenized as strand labels, so an oversized
    one raises on every later turn rather than only at index time. Narrowing the
    pre-append guard to strings, or to the claim field alone, must fail here."""
    with pytest.raises(TokenGrowthLimitError):
        assert_belief(beliefs, "b_1", "ordinary claim",
                      people=["asha", "転" * 6_500])

    assert list(beliefs.log) == []
    assert beliefs.state().beliefs == {}


def test_an_oversized_nested_field_is_refused_before_the_append(beliefs):
    with pytest.raises(TokenGrowthLimitError):
        assert_belief(beliefs, "b_1", "ordinary claim",
                      note={"detail": "転" * 6_500})

    assert list(beliefs.log) == []


def test_an_oversized_non_claim_string_field_is_refused(beliefs):
    with pytest.raises(TokenGrowthLimitError):
        assert_belief(beliefs, "b_1", "ordinary claim", subject="転" * 6_500)

    assert list(beliefs.log) == []


def test_a_prefix_assembled_from_three_legal_fields_cannot_brick_the_store(
    tmp_path,
):
    """Each field passes validation alone; the prefix concatenates them and goes
    over. It is built by an injected callable *after* the append has made the
    log line durable, so a raise there would abort every later rebuild forever
    with the offending line unremovable."""
    root = tmp_path / "main"
    field = "転" * 2_700
    with Store(root, prefix=build_prefix) as store:
        assert_belief(store, "b_1", "転職を考えている",
                      subject=field, ledger=field, loop=field)
        assert "b_1" in store.state().beliefs

    # Reopening replays from the log — this is where it used to raise forever.
    with Store(root, prefix=build_prefix) as reopened:
        assert "b_1" in reopened.state().beliefs
        assert matched(reopened, "転職") == ["b_1"], "the claim is still indexed"
        assert retrieve(reopened, "anything").ids == ("b_1",)


def _legacy_log(root, mutate):
    """A main's log as an older build left it: written through ``Store``, then
    rewritten on disk with a value no current build would accept."""
    with Store(root, prefix=build_prefix) as store:
        assert_belief(store, "b_1", "転職を考えている", people=["asha"])
        assert_belief(store, "b_2", "flies paragliders on weekends")
    root.joinpath("half.db").unlink()

    log_dir = root / "beliefs"
    path = next(iter(sorted(log_dir.glob("*.jsonl"))))
    lines = []
    for line in path.read_text(encoding="utf-8").splitlines():
        record = json.loads(line)
        if record["id"] == "b_1":
            mutate(record)
        lines.append(json.dumps(record, ensure_ascii=False))
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return root


def test_a_log_written_before_the_ceiling_existed_still_opens(tmp_path):
    """It must index what it can rather than being permanently unopenable. The
    schema-change fixture below cannot catch this: the content is what changed,
    and content only arrives by shipping."""
    root = _legacy_log(tmp_path / "main",
                       lambda record: record.update(claim="転" * 7_000))

    with Store(root, prefix=build_prefix) as store:
        assert set(store.state().beliefs) == {"b_1", "b_2"}
        assert store.state().beliefs["b_1"]["claim"] == "転" * 7_000
        # "What it can": the rest of the corpus is still term-indexed.
        assert matched(store, "paragliders") == ["b_2"]
        # The oversized belief is out of the term index, so it is reached the
        # way any belief no term matches is reached — through the backstop
        # (AD-24). That is a real degradation of one pathological legacy
        # record, and it is logged rather than silent; the alternative was a
        # store that could never be opened again.
        assert matched(store, "転") == []
        assert set(retrieve(store, "unrelated words entirely").ids) == {"b_1", "b_2"}


def test_a_legacy_oversized_strand_label_does_not_cost_every_later_turn(
    tmp_path,
):
    """The matrix's "turn survives" row, driven end to end. An oversized
    ``people`` label makes ``strands.observe`` raise on every turn forever; the
    reply must still be sent."""
    root = _legacy_log(tmp_path / "mains" / "vidit",
                       lambda record: record.update(people=["転" * 7_000]))
    mains_root = root.parent

    # ``message_id`` must not collide with a seeded belief id: the pipeline
    # keys idempotency on ``b_<message_id>`` and would read the turn as a
    # redelivery, passing this test for the wrong reason.
    transport = FakeTransport(
        [msg(text="thinking about the paragliders", message_id="900")]
    )
    channel = TelegramChannel(transport=transport, mains={"123": "vidit"})
    registry = ActorRegistry(mains_root)
    voice, _ = a_voice("still turning that over")
    try:
        asyncio.run(
            Runtime(channel=channel, registry=registry, voice=voice).run()
        )
    finally:
        registry.close()

    assert transport.sent, "an unusable strand label cost the main their reply"
    # And the message is durable, which is the half that would otherwise be
    # lost for ever: the idempotency check keys on ``b_<message_id>``, so a
    # turn that died before recording is a turn no redelivery can retry.
    with Store(mains_root / "vidit", prefix=build_prefix) as store:
        assert "b_900" in store.state().beliefs, (
            "an unusable strand label cost the main their message"
        )


def test_a_tokenizer_refusal_on_the_query_still_answers(tmp_path, monkeypatch):
    """``QueryTooLargeError`` degrades the turn's ranking; a general
    ``StoreError`` still fails it loudly, because that one means the index is
    unavailable and the main's message must stay redeliverable.
    ``test_strands.py`` asserts the other half of this pair."""
    root = tmp_path / "mains"
    with Store(root / "vidit", prefix=build_prefix) as store:
        assert_belief(store, "b_seed", "flies paragliders on weekends")

    def boom(*args, **kwargs):
        raise QueryTooLargeError("too much text")

    monkeypatch.setattr(Retriever, "retrieve", boom)
    transport = FakeTransport([msg(text="hello", message_id="900")])
    channel = TelegramChannel(transport=transport, mains={"123": "vidit"})
    registry = ActorRegistry(root)
    voice, _ = a_voice("still here")
    try:
        asyncio.run(
            Runtime(channel=channel, registry=registry, voice=voice).run()
        )
    finally:
        registry.close()

    assert transport.sent, "a query the tokenizer refused cost the main a reply"
    # And the message is durable: a turn that died before recording is a turn
    # the idempotency check makes unredeliverable for ever.
    with Store(root / "vidit", prefix=build_prefix) as store:
        assert "b_900" in store.state().beliefs, (
            "a query the tokenizer refused cost the main their message"
        )


# -- the prefix and the strand matcher, in every script ----------------------

def test_a_non_latin_subject_and_loop_are_indexed_and_findable(beliefs):
    assert_belief(beliefs, "b_1", "keeps putting it off",
                  subject="आशा", loop="転職-plan")
    assert_belief(beliefs, "b_2", "退職金の話をした")

    prefix = build_prefix(beliefs.state().beliefs["b_1"])
    assert "आशा" in prefix and "転職" in prefix
    assert matched(beliefs, "आशा") == ["b_1"]
    assert matched(beliefs, "転職") == ["b_1"]


def test_a_strand_named_in_an_unspaced_script_becomes_live():
    """The label sits inside a sentence that never spaced it, so a matcher
    comparing whole words finds no overlap at all."""
    strands = Strands()
    strands.observe("転職を考えている", {"loop:転職", "person:आशा"})

    assert strands.weights.get("loop:転職", 0.0) > 0.0
    assert "person:आशा" not in strands.weights


def test_an_unspaced_strand_outweighs_one_sharing_a_single_character():
    """The comparison n-grams in ``tokens`` exist for this: a set has no
    adjacency, so without them ``退職`` and ``転職`` score alike."""
    strands = Strands()
    strands.observe("転職を考えている", {"loop:転職", "loop:退職金"})

    assert strands.weights["loop:転職"] > strands.weights.get("loop:退職金", 0.0)


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


def test_comparison_folding_keeps_two_devanagari_words_apart():
    """``normalize`` strips every non-zero combining class, virama included, so
    ``यात्रा`` folded onto ``यातरा`` — the false-positive class the index just
    shed, reappearing in the strand matcher. A virama joins letters; it is not a
    diacritic."""
    assert tokens("यात्रा") != tokens("यातरा")
    assert tokens("Café") == tokens("cafe")
    assert tokens("ज़मीन") == tokens("जमीन")
    assert "転職" in tokens("転職を考えている")


# -- one tokenizer, and the one split that is deliberately separate ----------

#: Strings that separate the two splits if anything ever does: combining marks,
#: invisible characters, mixed scripts, decomposed forms, punctuation.
SPLIT_CORPUS = (
    "flies paragliders on weekends",
    "les plans du Café sont bloqués",
    "यात्रा की योजना बना रहा है",
    "ज़मीन खरीदने की बात",
    "転職を考えている",
    "planning a 転職 next spring",
    "cafe­plans and one‍two",
    unicodedata.normalize("NFD", "café-plans"),
    "well-formed user_name 2026",
    "😀 loves sunsets 🎈",
)


@pytest.mark.parametrize("text", SPLIT_CORPUS)
def test_the_ad18_split_and_the_index_split_stay_identical(text):
    """``half.context.build._units`` is a second hand-written copy of this
    splitter, kept separate on purpose — AD-18 asks a different question and
    must not inherit the clusters or the growth ceiling. Separate is fine;
    silently *diverging* is not, and this module's whole thesis is that three
    splitters disagreeing is what caused all of this. So the two are pinned to
    identical output instead of merged."""
    assert _units(text) == [
        folded for word in words(text) if (folded := normalize(word))
    ]


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
def deployed_before_the_clusters(tmp_path):
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


def test_an_older_derived_view_is_discarded_and_replayed(
    deployed_before_the_clusters,
):
    with Store(deployed_before_the_clusters, prefix=build_prefix) as store:
        assert "b_1" in store.state().beliefs
        # The read the older index could not serve: a word inside an unspaced
        # sentence, findable only through the clusters.
        assert matched(store, "転職") == ["b_1"]


def test_upgrading_an_older_view_never_leaks_a_raw_sqlite_error(
    deployed_before_the_clusters,
):
    """A main upgrading must not meet ``sqlite3.OperationalError: table
    belief_fts has no column named claim_terms``."""
    try:
        with Store(deployed_before_the_clusters, prefix=build_prefix) as store:
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
