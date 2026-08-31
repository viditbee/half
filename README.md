# Half

A second self that lives in your messaging app.

The source of truth for everything Half believes about you is an append-only
JSONL log in a directory on disk. Not a database with an export button — the
log *is* the thing. Everything else is folded from it and can be deleted.

    ~/.half/<main_id>/
      beliefs/YYYY-MM.jsonl   append-only — the only source of truth
      half.db                 SQLite: materialized fold + FTS5 index (disposable)

Your credentials are never in this tree.

Runtime is the Python standard library. `pytest` is the only development
dependency.

    uv run pytest -q

See `_bmad-output/planning-artifacts/architecture/.../ARCHITECTURE-SPINE.md`
for the 33 decisions this implements.
