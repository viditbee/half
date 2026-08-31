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
    secrets = FileSecretStore.beside(tmp_path / "mains")
    return tmp_path, store_root, secrets


def all_bytes(root: Path) -> bytes:
    return b"".join(p.read_bytes() for p in root.rglob("*") if p.is_file())


def test_the_file_store_satisfies_the_port(tmp_path):
    assert isinstance(FileSecretStore(tmp_path / "c"), SecretStore)


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
