"""Config decides who counts as a main, and had no coverage at all."""

from __future__ import annotations

from pathlib import Path

import pytest

from half.config import MAINS_ENV, ROOT_ENV, load
from half.errors import StoreError


def test_a_well_formed_mapping_parses():
    config = load({ROOT_ENV: "/tmp/h", MAINS_ENV: "123:vidit, 789:asha"})
    assert config.mains == {"123": "vidit", "789": "asha"}
    assert config.root == Path("/tmp/h")


def test_the_root_expands_a_tilde():
    assert "~" not in str(load({ROOT_ENV: "~/.half"}).root)


def test_an_empty_environment_yields_no_mains():
    assert load({}).mains == {}


def test_lookups_work_both_ways():
    config = load({MAINS_ENV: "123:vidit"})
    assert config.main_for("123") == "vidit"
    assert config.main_for("999") is None
    assert config.address_for("vidit") == "123"
    assert config.address_for("nobody") is None


@pytest.mark.parametrize("raw", ["broken", ":vidit", "123:", "  :  "])
def test_a_malformed_entry_is_rejected(raw):
    with pytest.raises(ValueError):
        load({MAINS_ENV: raw})


def test_a_duplicate_address_is_rejected():
    """Silently overwriting meant one of two mappings vanished."""
    with pytest.raises(ValueError):
        load({MAINS_ENV: "123:vidit, 123:asha"})


def test_two_addresses_for_one_main_are_rejected():
    with pytest.raises(ValueError):
        load({MAINS_ENV: "123:vidit, 456:vidit"})


@pytest.mark.parametrize("bad", ["../escape", "a/b", ".", "with space"])
def test_an_unsafe_main_id_is_rejected_at_configuration_time(bad):
    """main_id becomes a directory name, and this is operator input."""
    with pytest.raises(StoreError):
        load({MAINS_ENV: f"123:{bad}"})


def test_an_address_containing_a_colon_keeps_only_the_first_split():
    config = load({MAINS_ENV: "123:vidit"})
    assert config.mains == {"123": "vidit"}
