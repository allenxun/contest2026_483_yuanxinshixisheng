"""In-place SQLite schema upgrade (contract §6.3).

The reconciliation columns were added after the first released schema, and a
**deployed** database already holds real subjects.  Dropping and recreating it
would be an unacceptable destructive operation, so ``initialize()`` must upgrade
in place: detect missing columns with ``PRAGMA table_info`` and issue
``ALTER TABLE ... ADD COLUMN``, idempotently.

These tests build a genuine *legacy* database (old ``subjects`` DDL, no
reconciliation columns, one pre-existing row) and then assert the upgrade adds
the columns, preserves the row and its embedding, creates the index, and can be
run repeatedly.
"""

from __future__ import annotations

import sqlite3

import pytest
from conftest import make_image, synthetic_embedding

from face_service.errors import ErrorCode, FaceServiceError
from face_service.store import FaceStore, _ADDED_SUBJECT_COLUMNS, _CORRELATION_INDEX

#: The subjects DDL as first released — no reconciliation columns.
_LEGACY_SUBJECTS_DDL = """
CREATE TABLE subjects (
    namespace       TEXT NOT NULL,
    subject_id      TEXT NOT NULL,
    embedding       BLOB NOT NULL,
    embedding_dim   INTEGER NOT NULL,
    model_version   TEXT NOT NULL,
    quality_json    TEXT NOT NULL,
    det_score       REAL,
    bbox_json       TEXT,
    created_at      TEXT NOT NULL,
    updated_at      TEXT NOT NULL,
    PRIMARY KEY (namespace, subject_id),
    FOREIGN KEY (namespace) REFERENCES namespaces(namespace)
);
"""


def _make_legacy_db(path) -> tuple[str, bytes]:
    """Create a legacy-schema DB holding one real subject row.

    Returns ``(subject_id, embedding_blob)`` so the caller can assert the row and
    its embedding survived the upgrade byte-for-byte.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    try:
        conn.execute(
            "CREATE TABLE namespaces (namespace TEXT PRIMARY KEY, created_at TEXT NOT NULL)"
        )
        conn.execute(
            "CREATE TABLE library_meta (key TEXT PRIMARY KEY, value TEXT NOT NULL)"
        )
        conn.execute("INSERT INTO library_meta(key, value) VALUES ('revision', '7')")
        conn.execute(_LEGACY_SUBJECTS_DDL)
        conn.execute(
            "INSERT INTO namespaces(namespace, created_at) VALUES ('legacy-ns', '2026-01-01T00:00:00Z')"
        )
        embedding = synthetic_embedding(make_image(seed=500))
        import array
        import json

        buf = array.array("f", embedding)
        blob = buf.tobytes()
        conn.execute(
            "INSERT INTO subjects(namespace, subject_id, embedding, embedding_dim,"
            " model_version, quality_json, det_score, bbox_json, created_at, updated_at)"
            " VALUES ('legacy-ns', 'legacy-subject', ?, ?, 'legacy-model@1', ?, 0.9,"
            " NULL, '2026-01-02T00:00:00Z', '2026-01-02T00:00:00Z')",
            (blob, len(embedding), json.dumps({"min_acceptable": True})),
        )
        conn.commit()
    finally:
        conn.close()
    return "legacy-subject", blob


def _columns(path) -> list[str]:
    conn = sqlite3.connect(path)
    try:
        return [str(r[1]) for r in conn.execute("PRAGMA table_info(subjects)")]
    finally:
        conn.close()


def _indexes(path) -> list[str]:
    conn = sqlite3.connect(path)
    try:
        return [
            str(r[0])
            for r in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='index' AND tbl_name='subjects'"
            )
        ]
    finally:
        conn.close()


@pytest.fixture
def legacy_db(settings):
    subject_id, blob = _make_legacy_db(settings.db_path)
    return settings.db_path, subject_id, blob


# --------------------------------------------------------------------------
# 1. the legacy database really is legacy (guards the test's own premise)
# --------------------------------------------------------------------------
def test_legacy_db_starts_without_the_new_columns(legacy_db):
    path, _, _ = legacy_db
    cols = _columns(path)
    for name, _decl in _ADDED_SUBJECT_COLUMNS:
        assert name not in cols, f"premise broken: {name} already present"
    assert "idx_subjects_namespace_correlation" not in _indexes(path)


# --------------------------------------------------------------------------
# 2. in-place upgrade
# --------------------------------------------------------------------------
def test_initialize_adds_missing_columns_and_preserves_the_existing_row(legacy_db):
    path, subject_id, blob = legacy_db
    store = FaceStore(path)
    store.initialize()

    cols = _columns(path)
    for name, _decl in _ADDED_SUBJECT_COLUMNS:
        assert name in cols, f"{name} was not added"
    assert "idx_subjects_namespace_correlation" in _indexes(path)

    # The pre-existing row survived, and its embedding is byte-identical.
    conn = sqlite3.connect(path)
    try:
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            "SELECT * FROM subjects WHERE namespace = 'legacy-ns' AND subject_id = ?",
            (subject_id,),
        ).fetchone()
    finally:
        conn.close()
    assert row is not None, "the legacy row was dropped — upgrade must never recreate the DB"
    assert bytes(row["embedding"]) == blob
    assert int(row["embedding_dim"]) == len(synthetic_embedding(make_image(seed=500)))
    assert row["model_version"] == "legacy-model@1"
    assert row["created_at"] == "2026-01-02T00:00:00Z"
    # New columns read as NULL on a pre-existing row (nullable by design).
    assert row["correlation_id"] is None
    assert row["provider_request_id"] is None
    assert row["registered_at"] is None


def test_upgrade_preserves_library_revision(legacy_db):
    path, _, _ = legacy_db
    store = FaceStore(path)
    assert store.revision() == 7
    store.initialize()
    # Upgrading the schema is not a library change.
    assert store.revision() == 7


def test_upgrade_is_idempotent(legacy_db):
    path, subject_id, blob = legacy_db
    store = FaceStore(path)
    for _ in range(3):
        store.initialize()
    # Re-running must not duplicate columns (SQLite would error) nor lose data.
    cols = _columns(path)
    assert len(cols) == len(set(cols)), f"duplicate columns after re-upgrade: {cols}"
    for name, _decl in _ADDED_SUBJECT_COLUMNS:
        assert cols.count(name) == 1
    conn = sqlite3.connect(path)
    try:
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            "SELECT embedding FROM subjects WHERE namespace='legacy-ns' AND subject_id=?",
            (subject_id,),
        ).fetchone()
    finally:
        conn.close()
    assert bytes(row["embedding"]) == blob


def test_upgraded_legacy_store_serves_the_new_endpoints(legacy_db, make_client, settings):
    """After the upgrade a legacy DB must be fully usable, old and new alike."""
    path, _, _ = legacy_db
    FaceStore(path).initialize()
    client = make_client()

    # The legacy subject is still readable and searchable.
    got = client.get("/v1/namespaces/legacy-ns/subjects/legacy-subject")
    assert got.status_code == 200
    assert got.json()["model_version"] == "legacy-model@1"
    assert client.get("/v1/namespaces/legacy-ns/info").json()["subject_count"] == 1

    # A legacy row has no correlation id, so reconciliation reports not_found
    # rather than inventing one.
    recon = client.get("/v1/namespaces/legacy-ns/registrations/corr-unknown")
    assert recon.status_code == 200
    assert recon.json()["status"] == "not_found"

    # New registrations on the upgraded DB persist and reconcile normally.
    reg = client.post(
        "/v1/namespaces/legacy-ns/subjects",
        files={"image": ("f.png", make_image(seed=501), "image/png")},
        data={"subject_id": "new-one", "correlation_id": "corr-new",
              "provider_request_id": "prr-new"},
    )
    assert reg.status_code == 201
    found = client.get("/v1/namespaces/legacy-ns/registrations/corr-new").json()
    assert found["status"] == "registered"
    assert found["subject_id"] == "new-one"
    assert found["provider_request_id"] == "prr-new"
    # The legacy row is untouched by the new write.
    assert client.get("/v1/namespaces/legacy-ns/info").json()["subject_count"] == 2


# --------------------------------------------------------------------------
# 3. a fresh database needs no ALTER (the DDL already has the columns)
# --------------------------------------------------------------------------
def test_fresh_database_is_created_complete(settings):
    store = FaceStore(settings.db_path)
    store.initialize()
    cols = _columns(settings.db_path)
    for name, _decl in _ADDED_SUBJECT_COLUMNS:
        assert name in cols
    assert "idx_subjects_namespace_correlation" in _indexes(settings.db_path)
    assert store.revision() == 0


def test_correlation_index_is_usable_for_the_lookup(settings):
    """The index exists on the columns the reconciliation query filters by."""
    store = FaceStore(settings.db_path)
    store.initialize()
    conn = sqlite3.connect(settings.db_path)
    try:
        plan = " ".join(
            str(r[3])
            for r in conn.execute(
                "EXPLAIN QUERY PLAN SELECT subject_id FROM subjects "
                "WHERE namespace = 'n' AND correlation_id = 'c'"
            )
        )
    finally:
        conn.close()
    assert "idx_subjects_namespace_correlation" in plan, plan


# ==========================================================================
# Oracle r30 IMPORTANT — upgrading the DIRECT PREDECESSOR schema
# ==========================================================================
# The previous release created a *non-unique* index with the same name:
#     CREATE INDEX IF NOT EXISTS idx_subjects_namespace_correlation ...
# ``CREATE UNIQUE INDEX IF NOT EXISTS`` matches on the NAME only, so it silently
# skips and the database keeps a non-unique index while the code and the contract
# claim uniqueness.  These tests build exactly that predecessor shape.

_PREDECESSOR_SUBJECTS_DDL = """
CREATE TABLE subjects (
    namespace       TEXT NOT NULL,
    subject_id      TEXT NOT NULL,
    embedding       BLOB NOT NULL,
    embedding_dim   INTEGER NOT NULL,
    model_version   TEXT NOT NULL,
    quality_json    TEXT NOT NULL,
    det_score       REAL,
    bbox_json       TEXT,
    created_at      TEXT NOT NULL,
    updated_at      TEXT NOT NULL,
    correlation_id       TEXT,
    provider_request_id  TEXT,
    registered_at        TEXT,
    PRIMARY KEY (namespace, subject_id),
    FOREIGN KEY (namespace) REFERENCES namespaces(namespace)
);
"""


def _unique_flag(path) -> int | None:
    """``PRAGMA index_list`` unique flag for the correlation index (None if absent)."""
    conn = sqlite3.connect(path)
    try:
        for row in conn.execute("PRAGMA index_list(subjects)"):
            if str(row[1]) == "idx_subjects_namespace_correlation":
                return int(row[2])
        return None
    finally:
        conn.close()


def _make_predecessor_db(path, *, duplicate: bool = False) -> bytes:
    """Build a database in the *immediately preceding* released shape.

    Three reconciliation columns already exist, plus a **non-unique** index of the
    same name.  Optionally insert two rows sharing one correlation id (only
    possible while the index is non-unique).
    """
    import array
    import json as _json

    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path, isolation_level=None)
    try:
        conn.execute(
            "CREATE TABLE namespaces (namespace TEXT PRIMARY KEY, created_at TEXT NOT NULL)"
        )
        conn.execute("CREATE TABLE library_meta (key TEXT PRIMARY KEY, value TEXT NOT NULL)")
        conn.execute("INSERT INTO library_meta(key, value) VALUES ('revision', '5')")
        conn.execute(_PREDECESSOR_SUBJECTS_DDL)
        # The predecessor's NON-unique index — the whole point of these tests.
        conn.execute(
            "CREATE INDEX idx_subjects_namespace_correlation "
            "ON subjects(namespace, correlation_id)"
        )
        conn.execute(
            "INSERT INTO namespaces(namespace, created_at) "
            "VALUES ('ns-pred', '2026-01-01T00:00:00Z')"
        )
        embedding = synthetic_embedding(make_image(seed=560))
        blob = array.array("f", embedding).tobytes()
        ids = ("pred-1", "pred-2") if duplicate else ("pred-1",)
        for i, sid in enumerate(ids):
            conn.execute(
                "INSERT INTO subjects(namespace, subject_id, embedding, embedding_dim,"
                " model_version, quality_json, det_score, bbox_json, created_at, updated_at,"
                " correlation_id) VALUES ('ns-pred', ?, ?, 64, 'legacy-model@1', ?, 0.9, NULL,"
                " '2026-01-02T00:00:00Z', '2026-01-02T00:00:00Z', ?)",
                (sid, blob, _json.dumps({"min_acceptable": True}),
                 "corr-DUP" if duplicate else f"corr-{i}"),
            )
        return blob
    finally:
        conn.close()


def test_predecessor_db_starts_with_a_non_unique_index(tmp_path, settings):
    """Guard the premise: the fixture really is the non-unique predecessor shape."""
    path = tmp_path / "pred.sqlite3"
    _make_predecessor_db(path)
    assert _unique_flag(path) == 0, "premise broken: index should start NON-unique"
    assert "correlation_id" in _columns(path), "premise broken: columns should already exist"


def test_predecessor_index_is_upgraded_to_unique_preserving_data(tmp_path):
    path = tmp_path / "pred-up.sqlite3"
    blob = _make_predecessor_db(path)
    assert _unique_flag(path) == 0

    FaceStore(path).initialize()

    assert _unique_flag(path) == 1, "the same-named index was not upgraded to UNIQUE"
    conn = sqlite3.connect(path)
    try:
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            "SELECT * FROM subjects WHERE namespace='ns-pred' AND subject_id='pred-1'"
        ).fetchone()
        revision = conn.execute(
            "SELECT value FROM library_meta WHERE key='revision'"
        ).fetchone()[0]
    finally:
        conn.close()
    # The upgrade must never rewrite or drop existing data.
    assert bytes(row["embedding"]) == blob
    assert row["model_version"] == "legacy-model@1"
    assert row["correlation_id"] == "corr-0"
    assert int(revision) == 5, "a schema upgrade is not a library change"


def test_upgraded_predecessor_db_rejects_a_duplicate_correlation(tmp_path):
    """The DB-level guarantee, not just the application-level 409."""
    path = tmp_path / "pred-dupwrite.sqlite3"
    _make_predecessor_db(path)
    FaceStore(path).initialize()
    conn = sqlite3.connect(path, isolation_level=None)
    try:
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                "INSERT INTO subjects(namespace, subject_id, embedding, embedding_dim,"
                " model_version, quality_json, det_score, bbox_json, created_at, updated_at,"
                " correlation_id) VALUES ('ns-pred', 'pred-9', x'00', 64, 'm@1', '{}', 0.9,"
                " NULL, 't', 't', 'corr-0')"
            )
    finally:
        conn.close()


def test_predecessor_upgrade_is_idempotent(tmp_path):
    path = tmp_path / "pred-idem.sqlite3"
    _make_predecessor_db(path)
    store = FaceStore(path)
    for _ in range(3):
        store.initialize()
    assert _unique_flag(path) == 1
    conn = sqlite3.connect(path)
    try:
        rows = conn.execute("SELECT COUNT(*) FROM subjects").fetchone()[0]
        indexes = [
            str(r[0])
            for r in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='index' "
                "AND tbl_name='subjects' AND name='idx_subjects_namespace_correlation'"
            )
        ]
    finally:
        conn.close()
    assert rows == 1
    assert len(indexes) == 1, "re-running must not create a second index"


def test_predecessor_with_duplicates_refuses_and_leaves_the_database_intact(tmp_path):
    """A duplicate pair must stop startup — and must NOT destroy the index or rows.

    ``CREATE UNIQUE INDEX`` over existing duplicates raises *after* the old index
    is dropped, so the scan has to happen first and the whole thing has to run in
    one transaction; otherwise a failed startup would leave the table unindexed.
    """
    path = tmp_path / "pred-dup.sqlite3"
    _make_predecessor_db(path, duplicate=True)
    assert _unique_flag(path) == 0

    with pytest.raises(FaceServiceError) as exc:
        FaceStore(path).initialize()
    assert exc.value.code is ErrorCode.STORE_UNAVAILABLE
    message = str(exc.value.message)
    assert "1 (namespace, correlation_id) pair(s) are duplicated" in message
    # Never disclose the ids themselves.
    for secret in ("corr-DUP", "pred-1", "pred-2", "ns-pred"):
        assert secret not in message, secret

    # The rollback must have restored the previous index and every row.
    assert _unique_flag(path) == 0, "refusing to start must not leave the table unindexed"
    conn = sqlite3.connect(path)
    try:
        rows = conn.execute("SELECT COUNT(*) FROM subjects").fetchone()[0]
    finally:
        conn.close()
    assert rows == 2
