"""Oracle r29 fixes: correlation uniqueness, snapshot consistency, non-finite guards.

Each test here locks a specific finding from the r29 review, and each is written
to be **discriminative** — it fails against the pre-fix implementation:

* IMPORTANT 3 — one ``correlation_id`` may bind at most one subject per namespace
  (unique partial index + an explicit pre-write check that answers 409 instead of
  letting the index raise an opaque ``IntegrityError`` → 500).
* BLOCKER 2 — ``search_candidates`` reads revision, count and rows inside **one**
  explicit read transaction, so a concurrent delete cannot produce
  ``subject_count > 0`` with zero candidate rows (which used to make the caller
  index ``ranked[0]`` and fail with a 500).
* IMPORTANT 5 — a non-finite embedding or similarity must fail closed as a model
  fault and must **never** become an identity classification (NaN compares False
  against every threshold, so it used to fall through to ``reliable_new``).
"""

from __future__ import annotations

import math
import sqlite3
import threading

import numpy as np
import pytest
from conftest import EMBEDDING_DIM, make_image, synthetic_embedding

from face_service.errors import ErrorCode, FaceServiceError
from face_service.model import FakeModel, FaceDetection, cosine_similarity, normalize_embedding
from face_service.store import FaceStore

NS = "ns-r29"


def _register(client, subject_id: str, image: bytes, namespace: str = NS, **data):
    return client.post(
        f"/v1/namespaces/{namespace}/subjects",
        files={"image": ("f.png", image, "image/png")},
        data={"subject_id": subject_id, **{k: str(v) for k, v in data.items()}},
    )


# ==========================================================================
# IMPORTANT 3 — correlation_id uniqueness within a namespace
# ==========================================================================
def test_correlation_index_is_unique_and_partial(settings):
    """The index must be UNIQUE, and must not constrain NULL correlation ids."""
    store = FaceStore(settings.db_path)
    store.initialize()
    conn = sqlite3.connect(settings.db_path)
    try:
        rows = conn.execute(
            "SELECT name, sql FROM sqlite_master WHERE type='index' "
            "AND tbl_name='subjects' AND name='idx_subjects_namespace_correlation'"
        ).fetchall()
    finally:
        conn.close()
    assert len(rows) == 1
    ddl = (rows[0][1] or "").upper()
    assert "UNIQUE" in ddl, ddl
    # Partial: legacy rows and callers that send no correlation id stay unconstrained.
    assert "WHERE CORRELATION_ID IS NOT NULL" in ddl.replace("  ", " "), ddl


def test_same_correlation_cannot_bind_a_second_subject(client, settings):
    """Reusing a correlation id for a DIFFERENT subject is a 409, not a 500.

    Discriminative: before the pre-write check, the unique index raised
    ``sqlite3.IntegrityError``, which surfaced as an opaque 500.
    """
    first = _register(client, "subj-a", make_image(seed=700), correlation_id="corr-dup")
    assert first.status_code == 201
    second = _register(client, "subj-b", make_image(seed=701), correlation_id="corr-dup")
    assert second.status_code == 409
    err = second.json()["error"]
    assert err["code"] == "SUBJECT_ALREADY_EXISTS"
    assert "different subject" in err["message"]
    # The other subject's identity must not be disclosed to this caller.
    assert "subj-a" not in str(err.get("details", {}))
    # Reconciliation stays deterministic: exactly one row carries the id.
    store = FaceStore(settings.db_path)
    assert store.count_subjects(NS) == 1
    recon = client.get(f"/v1/namespaces/{NS}/registrations/corr-dup").json()
    assert recon["status"] == "registered"
    assert recon["subject_id"] == "subj-a"


def test_same_correlation_same_subject_is_still_an_idempotent_replay(client):
    """The uniqueness rule must not break the replay path (regression guard)."""
    image = make_image(seed=702)
    assert _register(client, "subj-c", image, correlation_id="corr-replay").status_code == 201
    replay = _register(client, "subj-c", make_image(seed=703), correlation_id="corr-replay")
    assert replay.status_code == 200
    assert replay.json()["replayed"] is True


def test_null_correlation_ids_are_not_constrained(client, settings):
    """Many subjects may have no correlation id at all (legacy callers)."""
    for i in range(4):
        assert _register(client, f"legacy-{i}", make_image(seed=710 + i)).status_code == 201
    conn = sqlite3.connect(settings.db_path)
    try:
        nulls = conn.execute(
            "SELECT COUNT(*) FROM subjects WHERE namespace=? AND correlation_id IS NULL",
            (NS,),
        ).fetchone()[0]
    finally:
        conn.close()
    assert nulls == 4


def test_same_correlation_in_different_namespaces_is_allowed(client, settings):
    """Uniqueness is per (namespace, correlation_id), not global."""
    assert _register(client, "s1", make_image(seed=720), correlation_id="corr-cross").status_code == 201
    other = _register(client, "s2", make_image(seed=721), namespace="ns-other-r29",
                      correlation_id="corr-cross")
    assert other.status_code == 201
    assert client.get(f"/v1/namespaces/{NS}/registrations/corr-cross").json()["subject_id"] == "s1"
    assert client.get("/v1/namespaces/ns-other-r29/registrations/corr-cross").json()["subject_id"] == "s2"


def test_migration_refuses_a_legacy_db_with_duplicate_correlations(tmp_path):
    """A legacy DB holding duplicates must fail loudly, not silently pick one.

    The unique index cannot be created over duplicates; ``initialize`` reports an
    explicit ``STORE_UNAVAILABLE`` naming only the **count** of duplicate groups
    (never the ids themselves).
    """
    path = tmp_path / "dup.sqlite3"
    conn = sqlite3.connect(path)
    try:
        conn.execute("CREATE TABLE namespaces (namespace TEXT PRIMARY KEY, created_at TEXT NOT NULL)")
        conn.execute("CREATE TABLE library_meta (key TEXT PRIMARY KEY, value TEXT NOT NULL)")
        conn.execute("INSERT INTO library_meta(key, value) VALUES ('revision', '3')")
        # Legacy shape PLUS the new columns, so the duplicate scan actually runs.
        conn.execute("""
            CREATE TABLE subjects (
                namespace TEXT NOT NULL, subject_id TEXT NOT NULL,
                embedding BLOB NOT NULL, embedding_dim INTEGER NOT NULL,
                model_version TEXT NOT NULL, quality_json TEXT NOT NULL,
                det_score REAL, bbox_json TEXT,
                created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
                correlation_id TEXT, provider_request_id TEXT, registered_at TEXT,
                PRIMARY KEY (namespace, subject_id)
            )
        """)
        conn.execute("INSERT INTO namespaces VALUES ('ns-dup', '2026-01-01T00:00:00Z')")
        import array
        blob = array.array("f", synthetic_embedding(make_image(seed=730))).tobytes()
        for sid in ("dup-1", "dup-2"):
            conn.execute(
                "INSERT INTO subjects(namespace, subject_id, embedding, embedding_dim,"
                " model_version, quality_json, det_score, bbox_json, created_at, updated_at,"
                " correlation_id) VALUES ('ns-dup', ?, ?, 64, 'm@1', '{}', 0.9, NULL,"
                " '2026-01-02T00:00:00Z', '2026-01-02T00:00:00Z', 'corr-DUP')",
                (sid, blob),
            )
        conn.commit()
    finally:
        conn.close()

    with pytest.raises(FaceServiceError) as exc:
        FaceStore(path).initialize()
    assert exc.value.code is ErrorCode.STORE_UNAVAILABLE
    message = str(exc.value.message)
    assert "1 (namespace, correlation_id) pair(s) are duplicated" in message
    # Never disclose the ids themselves.
    assert "corr-DUP" not in message
    assert "dup-1" not in message and "dup-2" not in message


# ==========================================================================
# BLOCKER 2 — one consistent read snapshot for search
# ==========================================================================
def test_search_snapshot_reads_revision_count_and_rows_in_one_transaction(settings):
    """The three reads must share a single snapshot.

    Discriminative: with autocommit (three independent snapshots) a delete landing
    between the COUNT and the row SELECT yields ``subject_count > 0`` with zero
    candidates, and the API then indexes ``ranked[0]`` → 500.  Here the store-level
    invariant is asserted directly: for a namespace whose rows are deleted
    concurrently, ``subject_count`` and ``len(candidates)`` can never disagree.
    """
    store = FaceStore(settings.db_path)
    store.initialize()
    image = make_image(seed=740)
    embedding = synthetic_embedding(image)
    for i in range(60):
        store.register(
            namespace=NS, subject_id=f"bulk-{i}", embedding=embedding,
            model_version="fake-model@0", quality={"min_acceptable": True},
            det_score=0.99, bbox=[0.0, 0.0, 64.0, 64.0],
        )

    stop = threading.Event()
    mismatches: list[str] = []
    errors: list[str] = []

    def deleter() -> None:
        try:
            for i in range(60):
                if stop.is_set():
                    return
                store.delete(namespace=NS, subject_id=f"bulk-{i}")
        except Exception as exc:  # pragma: no cover - diagnostic only
            errors.append(f"deleter: {exc!r}")

    def reader() -> None:
        try:
            while not stop.is_set():
                snap = store.search_candidates(NS)
                if snap.subject_count != len(snap.candidates):
                    mismatches.append(
                        f"count={snap.subject_count} rows={len(snap.candidates)}"
                    )
                    return
        except Exception as exc:  # pragma: no cover - diagnostic only
            errors.append(f"reader: {exc!r}")

    t_del = threading.Thread(target=deleter, daemon=True)
    readers = [threading.Thread(target=reader, daemon=True) for _ in range(3)]
    for t in readers:
        t.start()
    t_del.start()
    t_del.join(timeout=30)
    stop.set()
    for t in readers:
        t.join(timeout=30)

    assert errors == []
    assert mismatches == [], f"inconsistent snapshot observed: {mismatches}"


def test_search_api_never_500s_while_the_library_is_being_emptied(client, settings):
    """End-to-end form of the same guarantee: no 500, only valid decisions."""
    image = make_image(seed=741)
    embedding = synthetic_embedding(image)
    store = FaceStore(settings.db_path)
    for i in range(40):
        store.register(
            namespace="ns-drain", subject_id=f"d-{i}", embedding=embedding,
            model_version="fake-model@0", quality={"min_acceptable": True},
            det_score=0.99, bbox=[0.0, 0.0, 64.0, 64.0],
        )

    stop = threading.Event()
    statuses: list[int] = []
    decisions: set[str] = set()

    def deleter() -> None:
        for i in range(40):
            if stop.is_set():
                return
            client.delete(f"/v1/namespaces/ns-drain/subjects/d-{i}")

    def searcher() -> None:
        while not stop.is_set():
            resp = client.post(
                "/v1/namespaces/ns-drain/search",
                files={"image": ("f.png", image, "image/png")},
            )
            statuses.append(resp.status_code)
            if resp.status_code == 200:
                decisions.add(resp.json()["decision"])
            if len(statuses) >= 120:
                return

    t_del = threading.Thread(target=deleter, daemon=True)
    t_search = threading.Thread(target=searcher, daemon=True)
    t_search.start()
    t_del.start()
    t_del.join(timeout=60)
    stop.set()
    t_search.join(timeout=60)

    assert statuses, "no search completed — the test proved nothing"
    assert set(statuses) == {200}, f"non-200 statuses observed: {sorted(set(statuses))}"
    assert decisions <= {"matched", "uncertain", "reliable_new"}, decisions


# ==========================================================================
# IMPORTANT 5 — non-finite embeddings / similarities fail closed
# ==========================================================================
@pytest.mark.parametrize("bad", [float("nan"), float("inf"), float("-inf")])
def test_normalize_embedding_refuses_non_finite(bad):
    vector = np.zeros(8, dtype=np.float64)
    vector[0] = 1.0
    vector[3] = bad
    with pytest.raises(FaceServiceError) as exc:
        normalize_embedding(vector)
    assert exc.value.code is ErrorCode.MODEL_UNAVAILABLE
    # The fault is described without echoing the offending values.
    assert "non-finite" in str(exc.value.message)


@pytest.mark.parametrize("bad", [float("nan"), float("inf"), float("-inf")])
def test_cosine_similarity_refuses_non_finite_input(bad):
    good = (1.0, 0.0, 0.0, 0.0)
    polluted = (1.0, bad, 0.0, 0.0)
    for a, b in ((polluted, good), (good, polluted)):
        with pytest.raises(FaceServiceError) as exc:
            cosine_similarity(a, b)
        assert exc.value.code is ErrorCode.MODEL_UNAVAILABLE


def test_cosine_similarity_still_works_for_finite_input():
    assert cosine_similarity((1.0, 0.0), (1.0, 0.0)) == pytest.approx(1.0)
    assert cosine_similarity((1.0, 0.0), (0.0, 1.0)) == pytest.approx(0.0)
    assert math.isfinite(cosine_similarity((0.3, 0.4), (0.4, 0.3)))


def test_zero_norm_similarity_is_still_zero_not_an_error():
    """Pre-existing behaviour preserved: a zero vector compares as 0.0."""
    assert cosine_similarity((0.0, 0.0), (1.0, 0.0)) == 0.0


def test_search_fails_closed_when_the_model_returns_nan(make_client):
    """The decisive case: NaN must NOT become ``reliable_new``.

    Before the guard, ``NaN >= threshold`` and ``NaN >= threshold - band`` were
    both False, so the decision fell through to the final ``else`` branch and a
    numerical model fault was reported as a new person.
    """
    probe = make_image(seed=750)

    def nan_model(image_bytes: bytes) -> list[FaceDetection]:
        return [
            FaceDetection(
                bbox=(0.0, 0.0, 64.0, 64.0),
                det_score=0.99,
                embedding=(float("nan"),) * EMBEDDING_DIM,
            )
        ]

    c = make_client(model=FakeModel(detect_fn=nan_model))
    resp = c.post(
        "/v1/namespaces/ns-nan/search",
        files={"image": ("f.png", probe, "image/png")},
    )
    assert resp.status_code == 503, resp.text
    body = resp.json()["error"]
    assert body["code"] == "MODEL_UNAVAILABLE"
    assert body["retryable"] is True
    # No identity classification may be produced from a numerical fault.
    assert "decision" not in resp.json()


def test_compare_fails_closed_when_a_probe_embedding_is_nan(make_client):
    probe = make_image(seed=751)

    def nan_model(image_bytes: bytes) -> list[FaceDetection]:
        return [
            FaceDetection(
                bbox=(0.0, 0.0, 64.0, 64.0),
                det_score=0.99,
                embedding=(float("inf"),) * EMBEDDING_DIM,
            )
        ]

    c = make_client(model=FakeModel(detect_fn=nan_model))
    resp = c.post(
        "/v1/compare",
        files={"image_a": ("a.png", probe, "image/png"),
               "image_b": ("b.png", probe, "image/png")},
    )
    assert resp.status_code == 503
    assert resp.json()["error"]["code"] == "MODEL_UNAVAILABLE"
    assert "matched" not in resp.json()


def test_verify_fails_closed_on_a_nan_embedding(make_client, settings):
    """A stored/derived NaN must not silently become ``matched=false`` either."""
    probe = make_image(seed=752)
    good = make_client()
    assert _register(good, "alice", probe, namespace="ns-nan-verify").status_code == 201

    def nan_model(image_bytes: bytes) -> list[FaceDetection]:
        return [
            FaceDetection(
                bbox=(0.0, 0.0, 64.0, 64.0),
                det_score=0.99,
                embedding=(float("nan"),) * EMBEDDING_DIM,
            )
        ]

    broken = make_client(
        model=FakeModel(detect_fn=nan_model),
        settings_override=settings,
    )
    resp = broken.post(
        "/v1/verify",
        files={"image": ("f.png", probe, "image/png")},
        data={"namespace": "ns-nan-verify", "subject_id": "alice"},
    )
    assert resp.status_code == 503
    assert resp.json()["error"]["code"] == "MODEL_UNAVAILABLE"
    assert "matched" not in resp.json()
