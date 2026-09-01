"""The composition root — absent entirely until review found nothing could
actually start."""

from __future__ import annotations

import pytest

from half.__main__ import build, main
from pathlib import Path

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


# =============================================================================
# story 6d: the crisis classifier reaches the shipped product
# =============================================================================


def test_build_constructs_the_second_opinion_even_with_nothing_configured(tmp_path):
    """A deployment with no key and no tier is a *supported* shape, not a
    broken one: the phrase table decides alone, offline, exactly as it did in
    story 6a, and the safe word still works. A build that raised here would be
    a crisis subsystem refusing to start because a credential was missing —
    the omission headline arriving at boot time."""
    from half.crisis.classifier import SecondOpinion

    config = load({ROOT_ENV: str(tmp_path), MAINS_ENV: "123:vidit"})
    wiring = build(config, token="123:fake")
    assert isinstance(wiring.second, SecondOpinion)
    assert not wiring.second.holds("vidit")
    wiring.registry.close()


def test_build_equips_a_main_that_has_both_a_tier_and_a_key(tmp_path):
    """The whole point of the story's wiring task: a surface reachable only
    from a test is a surface nobody has run. This constructs the real provider
    from the real secret store — offline, because the SDK builds no client
    until it is asked to send something."""
    from half.config import TIERS_ENV
    from half.model.anthropic_transport import MODEL_KEY
    from half.secrets import FileSecretStore

    root = tmp_path / "mains"
    root.mkdir()
    FileSecretStore.beside(root).put("vidit", MODEL_KEY, "sk-not-a-real-key")

    config = load({ROOT_ENV: str(root), MAINS_ENV: "123:vidit",
                   TIERS_ENV: "vidit:cheap"})
    wiring = build(config, token="123:fake")
    assert wiring.second.holds("vidit")
    wiring.registry.close()


def test_a_main_with_a_tier_but_no_key_is_skipped_rather_than_fatal(tmp_path):
    from half.config import TIERS_ENV

    config = load({ROOT_ENV: str(tmp_path), MAINS_ENV: "123:vidit, 456:asha",
                   TIERS_ENV: "vidit:cheap"})
    wiring = build(config, token="123:fake")
    assert not wiring.second.holds("vidit") and not wiring.second.holds("asha")
    wiring.registry.close()


def test_the_holder_the_wiring_hands_over_cannot_produce_text(tmp_path):
    """AD-19's narrow protocol, checked where the object is actually built.
    ``SecondOpinion`` refuses a holder that can generate, so this passing means
    the composition root handed over ``provider.classifier()`` and not the
    provider."""
    from half.config import TIERS_ENV
    from half.model.anthropic_transport import MODEL_KEY
    from half.secrets import FileSecretStore

    root = tmp_path / "mains"
    root.mkdir()
    FileSecretStore.beside(root).put("vidit", MODEL_KEY, "sk-not-a-real-key")
    config = load({ROOT_ENV: str(root), MAINS_ENV: "123:vidit",
                   TIERS_ENV: "vidit:cheap"})
    wiring = build(config, token="123:fake")

    import half.__main__ as entrypoint

    source = (Path(entrypoint.__file__)).read_text(encoding="utf-8")
    assert "provider.classifier()" in source, (
        "the composition root must hand the crisis path the narrow holder"
    )
    wiring.registry.close()


def test_serve_passes_the_second_opinion_to_the_runtime():
    """The reachability assertion this story exists to make. A classifier built
    in ``build`` and never handed to the runtime would be a crisis classifier
    that ships and never runs."""
    import ast

    import half.__main__ as entrypoint

    tree = ast.parse(Path(entrypoint.__file__).read_text(encoding="utf-8"))
    serve = next(
        node for node in ast.walk(tree)
        if isinstance(node, ast.AsyncFunctionDef) and node.name == "serve"
    )
    runtimes = [
        node for node in ast.walk(serve)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
        and node.func.id == "Runtime"
    ]
    assert runtimes, "serve no longer constructs a Runtime"
    for call in runtimes:
        assert "second" in {kw.arg for kw in call.keywords}, (
            "the runtime is built without the crisis classifier"
        )
