"""The crisis-line directory: refresh, degrade, and say which version (CAP-12).

Build requirement 5 is one sentence with three clauses, and this file is one
section per clause: the file is *data*, it is *versioned*, and it is
*refreshable without a release*. The fourth section is the one the story cares
about most — every way the file can be wrong ends in the generic line and a
completed turn, never in an exception on the path where an exception is a main
in crisis receiving nothing.

**A green run here is not clinical review.** The companion's build requirement
6 covers the *contents* of ``data/crisis-lines.json`` as much as it covers the
code that reads it: a number that is right in shape and wrong in fact passes
every assertion below and fails the only test that matters.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from half.crisis import directory
from half.crisis.directory import UNKNOWN_VERSION, Directory, Listing

pytestmark = [pytest.mark.cap12, pytest.mark.cap12_handoff]

ROOT = Path(__file__).resolve().parents[1]

GOOD = {
    "version": "2026-09-01",
    # Every fixture below is signed off, because every fixture below is testing
    # something other than the review gate. The gate itself gets its own
    # section, and the *shipped* file is deliberately unreviewed.
    "reviewed": True,
    "aliases": {"first place": "aa", "second place": "bb"},
    "regions": {
        "aa": [
            {"id": "aa-one", "name": "First Line", "reach": "111"},
            {"id": "aa-two", "name": "Second Line", "reach": "text WORD to 222"},
        ],
        "bb": [{"id": "bb-one", "name": "Другая линия", "reach": "333"}],
    },
}


def doc(**overrides) -> dict:
    """A signed-off document with ``overrides`` applied."""
    return {"version": "v", "reviewed": True, **overrides}


def write(tmp_path: Path, document: object, *, name: str = "crisis-lines.json") -> Path:
    path = tmp_path / name
    path.write_text(
        document if isinstance(document, str) else json.dumps(document),
        encoding="utf-8",
    )
    return path


# =============================================================================
# it is data, and the shipped file is that data
# =============================================================================


def test_the_shipped_directory_parses_whole_and_names_no_region_first():
    """The file that actually ships. A flat table with no default and no
    privileged region: Half ships world-wide, and a directory with a fallback
    country is a directory that hands somebody the wrong continent whenever the
    lookup misses.

    Every entry must survive the guard — a name carrying a separator or a
    control character is dropped silently in production, so a shipped file that
    loses rows on load is a shipped file that quietly holds fewer lines than it
    appears to."""
    raw = json.loads((ROOT / "data" / "crisis-lines.json").read_text("utf-8"))
    found = directory.load()
    assert found.version != UNKNOWN_VERSION
    assert len(found.entries) > 1
    assert directory.EMPTY.listings_for(None) == ()

    written = sum(len(rows) for rows in raw["regions"].values())
    parsed = sum(len(listings) for listings in found.entries.values())
    assert parsed == written, (
        f"{written - parsed} shipped entries were dropped on load — a name or "
        "a reach carrying a separator or a control character"
    )
    for place, listings in found.entries.items():
        assert place == place.strip().casefold()
        assert listings, place
        for listing in listings:
            assert listing.name.strip() and listing.reach.strip(), listing


def test_the_shipped_directory_names_nothing_until_it_is_reviewed():
    """**The launch gate, asserted rather than remembered.**

    These entries were written from memory. A helpline number that is right in
    shape and wrong in fact is the most dangerous artefact this repository can
    produce, so the shipped file is marked unreviewed and Half names no line at
    all until a qualified reviewer signs it off (companion build requirement
    6). Flipping the flag makes this test fail, which is the point: it is a
    deliberate act with a name on it, not a default that shipped.
    """
    found = directory.load()
    assert found.reviewed is False, (
        "data/crisis-lines.json is marked reviewed. If a qualified reviewer "
        "has verified every entry against the operator's own source, update "
        "this test and say who, in the commit message. If not, set it back."
    )
    assert not found.usable
    for place in found.entries:
        assert found.listings_for(place) == (), place


def test_no_shipped_region_offers_the_same_organisation_twice():
    """A duplicate is not a choice. Three regions used to meet the two-line
    rule by listing one organisation's two phone numbers, which reads as two
    doors and is one."""
    for place, listings in directory.load().entries.items():
        names = [listing.name.casefold() for listing in listings]
        assert len(set(names)) == len(names), f"{place} lists a duplicate: {names}"
        # A second entry that is the first entry's name plus a parenthetical is
        # the same trick spelled differently.
        for i, name in enumerate(names):
            for other in names[i + 1:]:
                assert not other.startswith(name.split("(")[0].strip()), (
                    f"{place}: {other!r} is {name!r} again"
                )


#: Regions the shipped file holds exactly one line for. A main there who has
#: confirmed nobody gets one door, and one door is not a choice — so they get
#: 6a's generic wording instead. That is the right refusal and thin data;
#: pinned so the set can only shrink deliberately, and so nobody pads it with a
#: second number from memory.
THIN_REGIONS = frozenset({"br", "de", "nl", "sg"})


def test_the_regions_that_cannot_make_a_choice_alone_are_the_ones_we_know_about():
    from half.crisis.contacts import OFFER_MIN

    thin = {
        place for place, listings in directory.load().entries.items()
        if len(listings) < OFFER_MIN
    }
    assert thin == THIN_REGIONS, (
        f"the thin set moved: {sorted(thin)}. A main in one of these with "
        "nobody confirmed gets the generic wording. Do not pad this file from "
        "memory — that increases the surface without increasing the truth."
    )


def test_the_shipped_directory_is_found_from_the_module_rather_than_the_cwd():
    """``default_path`` walks up from the module, so the same code finds the
    file in the repository and inside an installed wheel. A fixed
    ``parents[n]`` works in exactly one of the two and degrades silently in the
    other — which for this file means production quietly offering no lines
    while every test passes."""
    assert directory.default_path() == ROOT / "data" / "crisis-lines.json"
    assert directory.default_path().is_file()


def test_the_directory_is_a_file_and_not_a_literal():
    """The whole point of build requirement 5. If the lines were in the source
    they would be a release, and the number that changed on Tuesday would ship
    on Thursday."""
    source = (ROOT / "half/crisis/directory.py").read_text(encoding="utf-8")
    for shipped in ("14416", "988", "116 123"):
        assert shipped not in source, "a crisis line is hardcoded in the reader"


# =============================================================================
# it is versioned, and the version is what gets recorded
# =============================================================================


def test_the_version_comes_from_the_file(tmp_path):
    assert directory.load(write(tmp_path, GOOD)).version == "2026-09-01"


def test_a_directory_with_no_version_is_refused_whole(tmp_path):
    """Refused rather than defaulted. A file this build cannot name is a file
    it cannot answer *"which lines was this person handed?"* about, and
    guessing at its shape is how a number ends up beside the wrong place."""
    document = {"regions": GOOD["regions"]}
    assert directory.load(write(tmp_path, document)) is directory.EMPTY


@pytest.mark.parametrize("version", [None, "", "   ", 3, 2026, True, ["v1"]])
def test_a_version_that_is_not_a_stated_string_is_refused(tmp_path, version):
    document = {"version": version, "reviewed": True, "regions": GOOD["regions"]}
    assert not directory.load(write(tmp_path, document)).usable


def test_an_unreadable_directory_still_names_a_version(tmp_path):
    """*"We could not read the file"* is an answer to the reviewer's question;
    a blank is not."""
    assert directory.load(tmp_path / "absent.json").version == UNKNOWN_VERSION
    assert directory.EMPTY.version == UNKNOWN_VERSION


# =============================================================================
# it refreshes without a release
# =============================================================================


def test_a_replaced_directory_is_used_with_no_code_change(tmp_path):
    """Matrix: directory refresh. Acceptance: *given a replaced directory file,
    the new entries are used with no code change, and the version used is
    recorded.*"""
    path = write(tmp_path, GOOD)
    before = directory.load(path)
    assert [l.name for l in before.listings_for("aa")] == ["First Line", "Second Line"]

    write(tmp_path, doc(
        version="2026-10-14",
        regions={"aa": [{"id": "aa-new", "name": "Renamed Line", "reach": "999"}]},
    ))
    after = directory.load(path)
    assert [l.name for l in after.listings_for("aa")] == ["Renamed Line"]
    assert after.version == "2026-10-14"


def test_a_new_region_arrives_without_a_release(tmp_path):
    path = write(tmp_path, GOOD)
    assert directory.load(path).listings_for("cc") == ()
    document = json.loads(path.read_text(encoding="utf-8"))
    document["regions"]["cc"] = [{"id": "cc-one", "name": "New Line", "reach": "444"}]
    write(tmp_path, document)
    assert directory.load(path).listings_for("cc")[0].name == "New Line"


def test_nothing_is_cached_between_loads(tmp_path):
    """A cache is a window in which a number somebody just corrected is still
    being handed out. The read is small and the path is rare; the window is
    not worth it."""
    path = write(tmp_path, GOOD)
    directory.load(path)
    write(tmp_path, doc(version="v2", regions={
        "aa": [{"id": "aa-x", "name": "Corrected", "reach": "555"}]}))
    assert directory.load(path).listings_for("aa")[0].reach == "555"


def test_the_lookup_folds_case_and_whitespace_but_invents_nothing(tmp_path):
    found = directory.load(write(tmp_path, GOOD))
    assert found.listings_for("AA") == found.listings_for(" aa ")
    assert found.listings_for("zz") == ()
    assert found.listings_for(None) == ()
    assert found.listings_for(42) == ()  # type: ignore[arg-type]


def test_file_order_is_the_curators_order(tmp_path):
    """Not sorted. The order in the file is somebody's judgement about which
    line to put in front of a person, and this module has no better one."""
    document = {"version": "v", "reviewed": True, "regions": {"aa": [
        {"id": "z", "name": "Zebra", "reach": "1"},
        {"id": "a", "name": "Aardvark", "reach": "2"},
    ]}}
    names = [l.name for l in directory.load(write(tmp_path, document)).listings_for("aa")]
    assert names == ["Zebra", "Aardvark"]


# =============================================================================
# it degrades, and degrading never costs the turn
# =============================================================================


@pytest.mark.parametrize(
    "document",
    [
        "",
        "   ",
        "{",
        "not json at all",
        '["a", "list"]',
        '"a string"',
        "null",
        '{"version": "v"}',
        '{"version": "v", "reviewed": True, "regions": []}',
        '{"version": "v", "reviewed": True, "regions": "aa"}',
        '{"version": "v", "reviewed": True, "regions": {}}',
        '{"version": "v", "reviewed": True, "regions": {"aa": {"id": "x"}}}',
        '{"version": "v", "reviewed": True, "regions": {"": [{"id":"x","name":"n","reach":"1"}]}}',
    ],
    ids=["empty", "blank", "truncated", "prose", "list-root", "string-root",
         "null-root", "no-regions", "regions-list", "regions-string",
         "regions-empty", "region-not-a-list", "blank-key"],
)
def test_a_malformed_directory_degrades_to_no_lines_and_never_raises(
    tmp_path, document
):
    """Matrix: directory malformed. Every one of these is *no lines*, logged
    without content, and the turn continues — because the alternative is a
    traceback where a reply should be."""
    found = directory.load(write(tmp_path, document))
    assert found is directory.EMPTY or not found.usable
    assert found.listings_for("aa") == ()


def test_a_missing_directory_degrades(tmp_path):
    """Matrix: directory missing."""
    assert directory.load(tmp_path / "nope" / "crisis-lines.json") is directory.EMPTY


def test_a_directory_that_is_a_folder_degrades(tmp_path):
    (tmp_path / "crisis-lines.json").mkdir()
    assert directory.load(tmp_path / "crisis-lines.json") is directory.EMPTY


def test_a_directory_that_is_not_utf8_degrades(tmp_path):
    path = tmp_path / "crisis-lines.json"
    path.write_bytes(b"\xff\xfe{\x00")
    assert directory.load(path) is directory.EMPTY


def test_an_enormous_directory_is_refused_rather_than_read(tmp_path):
    """A file that is huge by accident or on purpose costs a degraded offer,
    never a stalled crisis turn."""
    path = tmp_path / "crisis-lines.json"
    padding = "x" * (directory.MAX_BYTES + 1)
    path.write_text(json.dumps(doc(note=padding, regions={})), encoding="utf-8")
    assert directory.load(path) is directory.EMPTY


@pytest.mark.parametrize(
    "row",
    [
        {"name": "No id", "reach": "1"},
        {"id": "x", "reach": "1"},
        {"id": "x", "name": "No reach"},
        {"id": "x", "name": "", "reach": "1"},
        {"id": "x", "name": "n", "reach": "   "},
        {"id": 7, "name": "n", "reach": "1"},
        {"id": "x", "name": ["n"], "reach": "1"},
        {"id": "x", "name": "n", "reach": 111},
        "a bare string",
        None,
        42,
    ],
    ids=["no-id", "no-name", "no-reach", "blank-name", "blank-reach", "id-int",
         "name-list", "reach-int", "string-row", "null-row", "int-row"],
)
def test_one_bad_row_costs_one_row_and_never_a_region(tmp_path, row):
    """A malformed entry is dropped on its own. One bad row must not cost a
    continent its lines."""
    document = doc(regions={"aa": [
        row, {"id": "ok", "name": "Good Line", "reach": "1"},
    ]})
    listings = directory.load(write(tmp_path, document)).listings_for("aa")
    assert [l.name for l in listings] == ["Good Line"]


def test_a_region_whose_every_row_is_bad_is_dropped_rather_than_empty(tmp_path):
    document = {"version": "v", "reviewed": True, "regions": {
        "aa": [{"id": "x"}],
        "bb": [{"id": "y", "name": "Kept", "reach": "1"}],
    }}
    found = directory.load(write(tmp_path, document))
    assert found.listings_for("aa") == ()
    assert set(found.entries) == {"bb"}


def test_a_duplicate_id_keeps_the_first(tmp_path):
    document = {"version": "v", "reviewed": True, "regions": {"aa": [
        {"id": "same", "name": "First", "reach": "1"},
        {"id": "same", "name": "Second", "reach": "2"},
    ]}}
    listings = directory.load(write(tmp_path, document)).listings_for("aa")
    assert [l.name for l in listings] == ["First"]


def test_unknown_keys_are_ignored_rather_than_fatal(tmp_path):
    """The shipped file carries a note and a description of its own shape, and
    a later one will carry something this build has not met."""
    document = doc(note="hello", future={"anything": 1},
                   regions={"aa": [
                       {"id": "x", "name": "n", "reach": "1", "tomorrow": True}]})
    assert directory.load(write(tmp_path, document)).listings_for("aa")[0].name == "n"


def test_parse_is_reachable_without_a_filesystem():
    """Split from ``load`` so the validation is testable without writing bytes
    down, and so a caller holding the document already need not."""
    assert directory.parse(json.dumps(GOOD)).version == "2026-09-01"
    assert directory.parse("{{{") is directory.EMPTY


def test_a_listing_carries_its_note_when_there_is_one(tmp_path):
    document = {"version": "v", "reviewed": True, "regions": {"aa": [
        {"id": "x", "name": "n", "reach": "1", "note": "24/7"}]}}
    assert directory.load(write(tmp_path, document)).listings_for("aa")[0].note == "24/7"
    assert Listing(id="x", name="n", reach="1").note is None


def test_the_empty_directory_is_a_value_and_not_none():
    """A caller that has to check for ``None`` is a caller that can forget to,
    on the path where forgetting is an exception instead of a reply."""
    assert isinstance(directory.EMPTY, Directory)
    assert not directory.EMPTY.usable
    assert directory.EMPTY.listings_for("aa") == ()


def test_nothing_in_the_directory_module_reaches_a_clock_or_the_network():
    """The read is the only impurity, and it is the point of the module. AD-19
    and AD-30 hold otherwise: two loads of one file agree, always.

    Scanned as imports rather than as substrings, so that the module may
    explain in prose what it does not do."""
    import ast

    tree = ast.parse((ROOT / "half/crisis/directory.py").read_text(encoding="utf-8"))
    roots: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            roots.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            roots.add(node.module.split(".")[0])
    forbidden = {"time", "datetime", "random", "os", "httpx", "urllib",
                 "requests", "socket", "http", "anthropic", "openai"}
    assert not roots & forbidden, f"directory.py reaches {sorted(roots & forbidden)}"


def test_loading_twice_gives_the_same_answer(tmp_path):
    path = write(tmp_path, GOOD)
    assert directory.load(path) == directory.load(path)


# =============================================================================
# it names nothing until somebody has checked it
# =============================================================================


@pytest.mark.parametrize(
    "reviewed",
    [None, False, "true", "yes", 1, "reviewed", [], {}, "2026-09-01"],
    ids=["absent", "false", "true-str", "yes", "one", "word", "list", "dict",
         "date"],
)
def test_only_an_explicit_true_counts_as_a_review(tmp_path, reviewed):
    """Read strictly for the reason ``known_to_main`` is: this field grants a
    permission — to put an unverified phone number in front of somebody in
    crisis — so anything that is not an explicit ``True`` is not a review."""
    document = {"version": "v", "regions": GOOD["regions"]}
    if reviewed is not None:
        document["reviewed"] = reviewed
    found = directory.load(write(tmp_path, document))
    assert found.reviewed is False
    assert found.listings_for("aa") == ()
    assert not found.usable


def test_an_unreviewed_directory_still_says_which_version_it_declined(tmp_path):
    """Declining is an answer to *which set of lines was this person handed*,
    and a blank is not. The entries are parsed too, so the file can be
    inspected without being offered."""
    document = {"version": "2026-09-01", "regions": GOOD["regions"]}
    found = directory.load(write(tmp_path, document))
    assert found.version == "2026-09-01"
    assert found.entries, "an unreviewed file should still parse"
    assert found.listings_for("aa") == ()


def test_a_review_is_what_turns_the_lines_on(tmp_path):
    unreviewed = directory.load(write(tmp_path, {
        "version": "v", "regions": GOOD["regions"]}))
    reviewed = directory.load(write(tmp_path, {
        "version": "v", "reviewed": True, "regions": GOOD["regions"]}))
    assert unreviewed.entries == reviewed.entries
    assert unreviewed.listings_for("aa") == ()
    assert len(reviewed.listings_for("aa")) == 2


# =============================================================================
# what a person calls where they live
# =============================================================================


def test_an_alias_reaches_the_region_it_names(tmp_path):
    """Matrix: told region vocabulary. "uk", "england", "usa" match nothing as
    keys, and a main who answered the question deserves better than silently
    nothing."""
    found = directory.load(write(tmp_path, GOOD))
    assert found.key_for("first place") == "aa"
    assert found.listings_for("first place") == found.listings_for("aa")
    assert found.listings_for("FIRST PLACE ") == found.listings_for("aa")


def test_the_shipped_aliases_cover_the_spellings_people_actually_use():
    found = directory.load()
    for spelling, expected in [
        ("uk", "gb"), ("england", "gb"), ("United Kingdom", "gb"),
        ("usa", "us"), ("america", "us"), ("United States", "us"),
        ("india", "in"), ("australia", "au"), ("new zealand", "nz"),
        ("deutschland", "de"), ("brasil", "br"), ("españa", "es"),
    ]:
        assert found.key_for(spelling) == expected, spelling


def test_every_shipped_alias_names_a_region_the_file_holds():
    found = directory.load()
    for alias, place in found.aliases.items():
        assert place in found.entries, f"{alias} points at nothing: {place}"


def test_an_alias_pointing_nowhere_is_dropped(tmp_path):
    """Kept, it would turn *"nothing listed for there"* into the same answer by
    a longer route, and hide a typo in the file while doing it."""
    document = doc(aliases={"somewhere": "zz", "shadow": "aa"},
                   regions={"aa": [{"id": "x", "name": "n", "reach": "1"}]})
    found = directory.load(write(tmp_path, document))
    assert found.aliases == {"shadow": "aa"}
    assert found.key_for("somewhere") == "somewhere"
    assert found.listings_for("somewhere") == ()


def test_an_alias_never_shadows_a_real_region(tmp_path):
    document = doc(aliases={"aa": "bb"}, regions={
        "aa": [{"id": "x", "name": "A", "reach": "1"}],
        "bb": [{"id": "y", "name": "B", "reach": "2"}],
    })
    found = directory.load(write(tmp_path, document))
    assert found.listings_for("aa")[0].name == "A"


@pytest.mark.parametrize("aliases", ["nope", 42, [], None, {"a": 1}],
                         ids=["str", "int", "list", "none", "int-target"])
def test_an_unreadable_alias_table_costs_the_aliases_and_nothing_else(
    tmp_path, aliases
):
    document = doc(aliases=aliases,
                   regions={"aa": [{"id": "x", "name": "n", "reach": "1"}]})
    found = directory.load(write(tmp_path, document))
    assert found.aliases == {}
    assert found.listings_for("aa")


def test_key_for_separates_nothing_told_from_nothing_listed(tmp_path):
    """The two absences a caller has to tell apart: a main who never answered,
    and a main who answered and got nowhere. Both are no lines and they are
    very different things to say."""
    found = directory.load(write(tmp_path, GOOD))
    assert found.key_for(None) is None
    assert found.key_for("   ") is None
    assert found.key_for("zz") == "zz"
    assert found.listings_for("zz") == ()


# =============================================================================
# nothing unrenderable gets in
# =============================================================================


@pytest.mark.parametrize(
    "name",
    ["Line\nTake thirty of them", "Line\rmore", "Line\tmore", "Line\x00",
     "Line more", "Line‮more", "First — Second", "A · B",
     "x" * 200],
    ids=["newline", "carriage-return", "tab", "nul", "line-separator",
         "bidi-override", "join", "note-join", "too-long"],
)
def test_an_entry_that_could_not_be_rendered_as_one_line_is_dropped(
    tmp_path, name
):
    """A directory is a file an operator edits, so it is the second way a
    control character reaches a crisis reply. The first was a contact's name,
    and that one shipped."""
    document = doc(regions={"aa": [
        {"id": "bad", "name": name, "reach": "1"},
        {"id": "ok", "name": "Good Line", "reach": "2"},
    ]})
    listings = directory.load(write(tmp_path, document)).listings_for("aa")
    assert [listing.name for listing in listings] == ["Good Line"]


@pytest.mark.parametrize("field_name", ["reach", "note"],
                         ids=["reach", "note"])
def test_a_separator_in_any_rendered_field_costs_the_entry(tmp_path, field_name):
    entry = {"id": "bad", "name": "Line", "reach": "1", field_name: "a — b"}
    document = doc(regions={"aa": [
        entry, {"id": "ok", "name": "Good Line", "reach": "2"}]})
    listings = directory.load(write(tmp_path, document)).listings_for("aa")
    names = [listing.name for listing in listings]
    if field_name == "reach":
        assert names == ["Good Line"]
    else:
        # A note is optional, so a bad one costs the note rather than the line.
        assert names == ["Line", "Good Line"]
        assert listings[0].note is None


def test_no_shipped_value_carries_a_separator_or_a_control_character():
    """The shipped file, held to the same rule its readers are. A value that
    fails is dropped in production without anybody noticing."""
    from half.crisis import rows

    raw = json.loads((ROOT / "data" / "crisis-lines.json").read_text("utf-8"))
    for place, entries in raw["regions"].items():
        for entry in entries:
            for key in ("id", "name", "reach", "note"):
                if key not in entry:
                    continue
                assert rows.plain(entry[key], limit=rows.MAX_NOTE) == entry[key], (
                    f"{place}/{entry.get('id')}: {key} would be dropped on load"
                )


def test_shipped_names_keep_their_diacritics():
    """A name is carried in whatever script it is, unchanged — and these had
    been flattened to ASCII while the em dash in the same strings survived, so
    it was never an encoding limit."""
    names = {
        listing.name
        for listings in directory.load().entries.values()
        for listing in listings
    }
    for expected in ("Línea de la Vida", "SOS Amitié", "Numéro national de "
                     "prévention du suicide", "Teléfono de la Esperanza",
                     "CVV (Centro de Valorização da Vida)"):
        assert expected in names, expected


# =============================================================================
# the read path
# =============================================================================


def test_a_byte_order_mark_does_not_cost_the_whole_file(tmp_path):
    """An editor that writes a BOM would otherwise take the directory with it:
    the mark lands in front of the opening brace and JSON refuses it."""
    path = tmp_path / "crisis-lines.json"
    path.write_bytes(b"\xef\xbb\xbf" + json.dumps(GOOD).encode("utf-8"))
    assert directory.load(path).listings_for("aa")


def test_a_file_that_grew_after_a_stat_is_still_bounded(tmp_path):
    """The size check reads a bounded prefix and then decides. A check made
    against a prior ``stat`` is a check a file can grow past between the two."""
    path = tmp_path / "crisis-lines.json"
    path.write_text(json.dumps(doc(note="x" * (directory.MAX_BYTES + 10),
                                   regions=GOOD["regions"])), encoding="utf-8")
    assert directory.load(path) is directory.EMPTY


def test_the_search_for_the_file_is_bounded(tmp_path):
    """An unbounded walk climbs to the filesystem root and adopts any
    ancestor's ``data/crisis-lines.json`` — a home directory, a shared volume.
    A stranger's file is not this product's directory."""
    deep = tmp_path / "one" / "two" / "three" / "four" / "five"
    deep.mkdir(parents=True)
    planted = tmp_path / "data"
    planted.mkdir()
    (planted / "crisis-lines.json").write_text(json.dumps(GOOD), encoding="utf-8")
    found = directory.search_from(deep / "directory.py")
    assert not found.is_file(), f"the walk reached {found}"


def test_the_file_is_found_in_a_source_tree_layout(tmp_path):
    """``<project>/half/crisis/directory.py`` beside ``<project>/data/``."""
    module = tmp_path / "half" / "crisis" / "directory.py"
    module.parent.mkdir(parents=True)
    (tmp_path / "data").mkdir()
    target = tmp_path / "data" / "crisis-lines.json"
    target.write_text(json.dumps(GOOD), encoding="utf-8")
    assert directory.search_from(module) == target


def test_the_file_is_found_in_an_installed_layout(tmp_path):
    """``<site-packages>/half/crisis/directory.py`` beside
    ``<site-packages>/half/data/``. This is the layout the wheel produces, and
    the one no test observed: deleting the packaging line that puts the file
    there left every test green and every deployment with no directory at
    all."""
    package = tmp_path / "site-packages" / "half"
    module = package / "crisis" / "directory.py"
    module.parent.mkdir(parents=True)
    (package / "data").mkdir()
    target = package / "data" / "crisis-lines.json"
    target.write_text(json.dumps(GOOD), encoding="utf-8")
    assert directory.search_from(module) == target
    assert directory.load(directory.search_from(module)).listings_for("aa")


def test_the_installed_layout_needs_the_packaging_line_that_creates_it():
    """The other half of the same failure: the search is right and the file is
    only there because ``pyproject.toml`` puts it there. Deleting two lines
    lost the whole feature in every installed deployment, silently."""
    import tomllib

    meta = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    include = (
        meta["tool"]["hatch"]["build"]["targets"]["wheel"].get("force-include", {})
    )
    assert include.get("data/crisis-lines.json") == "half/data/crisis-lines.json", (
        "the wheel no longer ships the crisis directory. In an installed "
        "layout default_path() then resolves to a file that does not exist, "
        "and every deployment loses every line with the suite still green."
    )


def test_a_layout_with_no_data_directory_resolves_somewhere_nameable(tmp_path):
    module = tmp_path / "half" / "crisis" / "directory.py"
    module.parent.mkdir(parents=True)
    found = directory.search_from(module)
    assert found.name == directory.FILE_NAME
    assert not found.is_file()
    assert directory.load(found) is directory.EMPTY
