"""AD-11: the export boundary and the secret boundary must not overlap.

Half's own credentials — the tokens it was *given*, not the ones it finds while
reading — must appear nowhere in the log, a projection, a replay, or an export.
The store is exportable and replayable, so a token inside it would be handed to
the main in an archive and resurrected on every replay.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from half.errors import StoreError
from half.secrets import SECRETS_DIRNAME, FileSecretStore, SecretStore
from half.store.export import export, scan_for_secrets
from half.store.ops import Op
from half.store.store import Store

TOKEN = "1/" + "/0" + "abcdefghijklmnopqrstuvwxyz012345"


@pytest.fixture
def layout(tmp_path):
    store_root = tmp_path / "mains" / "vidit"
    store_root.mkdir(parents=True)
    secrets = FileSecretStore.beside(tmp_path / "mains")
    return tmp_path, store_root, secrets


def all_bytes(root: Path) -> bytes:
    return b"".join(p.read_bytes() for p in root.rglob("*") if p.is_file())


def test_the_file_store_satisfies_the_port(tmp_path):
    store = FileSecretStore(tmp_path / "c", store_root=tmp_path / "mains")
    assert isinstance(store, SecretStore)


def test_store_root_is_required():
    """It was optional, so the nesting invariant went unchecked whenever a
    caller omitted it — a guard you can skip by not passing an argument."""
    with pytest.raises(TypeError):
        FileSecretStore("/tmp/anywhere")


def test_beside_stays_outside_the_tree_holding_every_main(tmp_path):
    """`beside()` takes the parent of all mains. Passing one main's own root
    produced a path that was a sibling of that main but a child of the tree
    holding all of them — and the guard, comparing only against the value
    passed in, approved it."""
    mains = tmp_path / "mains"
    (mains / "vidit").mkdir(parents=True)
    store = FileSecretStore.beside(mains)
    assert not store.root.resolve().is_relative_to(mains.resolve())


def test_an_existing_loose_directory_is_tightened(tmp_path):
    """mkdir's mode is ignored when the directory already exists."""
    loose = tmp_path / "creds"
    loose.mkdir(mode=0o777)
    FileSecretStore(loose, store_root=tmp_path / "mains")
    assert loose.stat().st_mode & 0o077 == 0


def test_a_stale_temp_file_cannot_become_the_credential_file(tmp_path):
    """A pre-existing temp file kept its own mode and was promoted by
    os.replace, putting a live token in a world-readable file."""
    import os

    creds = tmp_path / "creds"
    store = FileSecretStore(creds, store_root=tmp_path / "mains")
    stale = creds / f"vidit.{os.getpid()}.tmp"
    stale.write_text("{}", encoding="utf-8")
    stale.chmod(0o644)
    store.put("vidit", "gmail", TOKEN)
    assert (creds / "vidit.json").stat().st_mode & 0o077 == 0


def test_a_corrupt_credential_file_raises_a_domain_error(tmp_path):
    creds = tmp_path / "creds"
    store = FileSecretStore(creds, store_root=tmp_path / "mains")
    (creds / "vidit.json").write_text("{not json", encoding="utf-8")
    with pytest.raises(StoreError):
        store.get("vidit", "gmail")


def test_the_file_is_removed_when_the_last_credential_goes(tmp_path):
    creds = tmp_path / "creds"
    store = FileSecretStore(creds, store_root=tmp_path / "mains")
    store.put("vidit", "gmail", TOKEN)
    store.delete("vidit", "gmail")
    assert not (creds / "vidit.json").exists()


def test_a_token_round_trips(layout):
    _, _, secrets = layout
    secrets.put("vidit", "gmail", TOKEN)
    assert secrets.get("vidit", "gmail") == TOKEN
    secrets.delete("vidit", "gmail")
    assert secrets.get("vidit", "gmail") is None


def test_credentials_live_outside_the_store_tree(layout):
    tmp, store_root, secrets = layout
    secrets.put("vidit", "gmail", TOKEN)
    assert not secrets.root.resolve().is_relative_to((tmp / "mains").resolve())
    assert secrets.root.name == SECRETS_DIRNAME


def test_the_store_refuses_to_nest_inside_the_store_tree(tmp_path):
    store_root = tmp_path / "mains"
    with pytest.raises(StoreError):
        FileSecretStore(store_root / SECRETS_DIRNAME, store_root=store_root)


def test_source_files_are_not_world_readable(tmp_path):
    """The mailbox archive deserves the same posture as the credential store
    beside it — removing every mode from LocalSourceStore used to ship green."""
    from half.store.sources import LocalSourceStore

    store = LocalSourceStore(tmp_path / "sources")
    address = store.put(b"a captured message")
    assert store.root.stat().st_mode & 0o077 == 0
    assert store._path(address).stat().st_mode & 0o077 == 0


def test_a_token_never_appears_in_the_store_tree(layout):
    tmp, store_root, secrets = layout
    secrets.put("vidit", "gmail", TOKEN)
    with Store(store_root) as store:
        store.record(Op.ASSERT, "b_1", "2026-08-01T00:00:00Z",
                     subject="self", claim="swims on tuesdays")
    assert TOKEN.encode() not in all_bytes(store_root)


def test_a_token_never_appears_in_an_export(layout, tmp_path):
    tmp, store_root, secrets = layout
    secrets.put("vidit", "gmail", TOKEN)
    with Store(store_root) as store:
        store.record(Op.ASSERT, "b_1", "2026-08-01T00:00:00Z",
                     subject="self", claim="swims on tuesdays")
    out = export(store_root, tmp_path / "export")
    assert TOKEN.encode() not in all_bytes(out)
    assert scan_for_secrets(out) == []


def test_a_token_does_not_survive_a_replay(layout):
    tmp, store_root, secrets = layout
    secrets.put("vidit", "gmail", TOKEN)
    with Store(store_root) as store:
        store.record(Op.ASSERT, "b_1", "2026-08-01T00:00:00Z",
                     subject="self", claim="swims")
        store.db_path.unlink(missing_ok=True)
        rebuilt = store.rebuild()
    assert TOKEN not in rebuilt.canonical_json()


def test_credentials_are_not_world_readable(layout):
    _, _, secrets = layout
    secrets.put("vidit", "gmail", TOKEN)
    for path in (secrets.root, secrets.root / "vidit.json"):
        assert path.stat().st_mode & 0o077 == 0, f"{path} is group/world accessible"


@pytest.mark.parametrize("bad", ["../escape", "a/b", "", "."])
def test_an_unsafe_main_id_cannot_place_a_credential_file(layout, bad):
    _, _, secrets = layout
    with pytest.raises(StoreError):
        secrets.put(bad, "gmail", TOKEN)


def test_deleting_an_absent_credential_is_not_an_error(layout):
    _, _, secrets = layout
    secrets.delete("vidit", "never-set")
