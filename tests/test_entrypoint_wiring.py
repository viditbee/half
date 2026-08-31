"""The composition root — absent entirely until review found nothing could
actually start."""

from __future__ import annotations

import pytest

from half.__main__ import build, main
from half.config import MAINS_ENV, ROOT_ENV, load


def test_the_package_exposes_a_console_entrypoint():
    import tomllib
    from pathlib import Path

    meta = tomllib.loads((Path(__file__).resolve().parents[1] / "pyproject.toml").read_text())
    assert meta["project"]["scripts"]["half"] == "half.__main__:main"


def test_build_wires_the_graph_without_touching_the_network(tmp_path):
    config = load({ROOT_ENV: str(tmp_path), MAINS_ENV: "123:vidit"})
    wiring = build(config, token="123:fake-token-for-construction")
    assert wiring.channel.mains == {"123": "vidit"}
    assert wiring.registry.root == tmp_path
    wiring.registry.close()


def test_build_constructs_the_credential_store_outside_the_store_tree(tmp_path):
    """AD-11, wired rather than merely available. Three stories shipped a
    surface reachable only from tests before this was asserted."""
    config = load({ROOT_ENV: str(tmp_path / "mains"), MAINS_ENV: "123:vidit"})
    wiring = build(config, token="123:fake")
    assert not wiring.secrets.root.resolve().is_relative_to(
        (tmp_path / "mains").resolve()
    )
    wiring.registry.close()


def test_build_constructs_a_source_store_per_main(tmp_path):
    config = load({ROOT_ENV: str(tmp_path), MAINS_ENV: "123:vidit, 456:asha"})
    wiring = build(config, token="123:fake")
    assert set(wiring.sources) == {"vidit", "asha"}
    assert wiring.sources["vidit"].root == tmp_path / "vidit" / "sources"
    wiring.registry.close()


def test_the_ingestion_surface_is_reachable_from_the_wiring(tmp_path):
    """A Pipeline can be constructed from what build() produces, without
    reaching into internals."""
    from half.ingest.pipeline import Pipeline

    config = load({ROOT_ENV: str(tmp_path), MAINS_ENV: "123:vidit"})
    wiring = build(config, token="123:fake")
    pipeline = Pipeline(source=None, store=wiring.sources["vidit"])
    assert pipeline.store is wiring.sources["vidit"]
    wiring.registry.close()


def test_build_restores_reachability_from_the_log(tmp_path):
    """Without this a restart reports every main as never-contacted."""
    from half.channel.port import Reachability
    from half.store.ops import Op
    from half.store.store import Store

    with Store(tmp_path / "vidit") as store:
        store.record(Op.ASSERT, "b_1", "2026-08-14T09:12:00Z",
                     subject="self", claim="hello", ledger="stated")

    config = load({ROOT_ENV: str(tmp_path), MAINS_ENV: "123:vidit"})
    wiring = build(config, token="123:fake")
    assert wiring.channel.capability_query("vidit") is Reachability.OPEN
    wiring.registry.close()


def test_running_without_mains_exits_with_a_usable_message(capsys):
    assert main([]) == 2
    assert MAINS_ENV in capsys.readouterr().err
