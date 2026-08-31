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
    channel, registry = build(config, token="123:fake-token-for-construction")
    assert channel.mains == {"123": "vidit"}
    assert registry.root == tmp_path
    registry.close()


def test_build_restores_reachability_from_the_log(tmp_path):
    """Without this a restart reports every main as never-contacted."""
    from half.channel.port import Reachability
    from half.store.ops import Op
    from half.store.store import Store

    with Store(tmp_path / "vidit") as store:
        store.record(Op.ASSERT, "b_1", "2026-08-14T09:12:00Z",
                     subject="self", claim="hello", ledger="stated")

    config = load({ROOT_ENV: str(tmp_path), MAINS_ENV: "123:vidit"})
    channel, registry = build(config, token="123:fake")
    assert channel.capability_query("vidit") is Reachability.OPEN
    registry.close()


def test_running_without_mains_exits_with_a_usable_message(capsys):
    assert main([]) == 2
    assert MAINS_ENV in capsys.readouterr().err
