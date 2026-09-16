"""Isolated SQLite subject store.

Design notes
------------
* **Independent data.**  Plain stdlib ``sqlite3`` in a service-owned file.  No
  PostgreSQL, no ``face_cache.pkl``, no import of any pre-existing library.
* **Namespace isolation.**  Every query is scoped by ``namespace``; there is no
  cross-namespace read path.
* **Audit trail.**  A single monotonic ``library_revision`` is incremented on
  every successful write (register/overwrite/delete) and returned in every
  response so callers can record which library state a decision used.
* **No embedding leakage.**  Embeddings are only ever returned to the internal
  ``verify`` path; the public projection (:meth:`SubjectRecord.to_meta`) omits
  them.
"""

from __future__ import annotations

import array
import json
import sqlite3
import threading
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator

from .errors import ErrorCode, FaceServiceError

_SCHEMA = """
CREATE TABLE IF NOT EXISTS namespaces (
    namespace   TEXT PRIMARY KEY,
    created_at  TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS subjects (
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
CREATE TABLE IF NOT EXISTS library_meta (
    key     TEXT PRIMARY KEY,
    value   TEXT NOT NULL
);
INSERT OR IGNORE INTO library_meta(key, value) VALUES ('revision', '0');
"""

#: Columns added after the first released schema.  They are nullable so existing
#: rows stay valid; ``initialize`` adds any that are missing (in-place upgrade).
_ADDED_SUBJECT_COLUMNS: tuple[tuple[str, str], ...] = (
    ("correlation_id", "TEXT"),
    ("provider_request_id", "TEXT"),
    ("registered_at", "TEXT"),
)

#: Created *after* the columns exist (so an in-place upgrade of a legacy DB does
#: not fail on a missing column).
_CORRELATION_INDEX = (
    "CREATE INDEX IF NOT EXISTS idx_subjects_namespace_correlation "
    "ON subjects(namespace, correlation_id)"
)

def _migrate_subjects(conn: sqlite3.Connection) -> None:
    """In-place, idempotent upgrade of the ``subjects`` table.

    The reconciliation columns were added after the first released schema.  They
    are **nullable**, so pre-existing rows stay valid.  A deployed database
    already holds real subjects, so it must be upgradeable *without* dropping it:
    ``initialize`` therefore detects missing columns with ``PRAGMA table_info``
    and issues ``ALTER TABLE ... ADD COLUMN``.  Running this repeatedly is a
    no-op.

    The correlation index is created **after** the columns exist, so upgrading a
    legacy database cannot fail on a missing column.

    ``name``/``decl`` come from the module-level ``_ADDED_SUBJECT_COLUMNS``
    constant (never from a request), so interpolating them into DDL is safe;
    values are still bound as parameters everywhere else.
    """
    existing = {str(row["name"]) for row in conn.execute("PRAGMA table_info(subjects)")}
    for name, decl in _ADDED_SUBJECT_COLUMNS:
        if name not in existing:
            conn.execute(f"ALTER TABLE subjects ADD COLUMN {name} {decl}")
    conn.execute(_CORRELATION_INDEX)


_REVISION_KEY = "revision"


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@dataclass(frozen=True)
class SubjectRecord:
    namespace: str
    subject_id: str
    embedding: tuple[float, ...]
    embedding_dim: int
    model_version: str
    quality: dict[str, Any]
    det_score: float | None
    bbox: list[float] | None
    created_at: str
    updated_at: str
    # Reconciliation keys (added by the in-place schema upgrade; nullable).
    correlation_id: str | None = None
    provider_request_id: str | None = None
    registered_at: str | None = None

    def to_meta(self) -> dict[str, Any]:
        """Public projection: deliberately excludes the embedding."""
        return {
            "subject_id": self.subject_id,
            "namespace": self.namespace,
            "embedding_dim": self.embedding_dim,
            "model_version": self.model_version,
            "det_score": self.det_score,
            "bbox": self.bbox,
            "quality": self.quality,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }


@dataclass(frozen=True)
class RegisterResult:
    created: bool
    record: SubjectRecord
    library_revision: int
    #: True when an existing subject was returned because the incoming
    #: ``correlation_id`` matched the stored one (idempotent replay: no
    #: overwrite, no revision bump).
    replayed: bool = False


@dataclass(frozen=True)
class RegistrationRecord:
    """Read-only projection for the registration reconciliation lookup."""

    subject_id: str
    correlation_id: str | None
    provider_request_id: str | None
    registered_at: str | None
    library_revision: int


@dataclass(frozen=True)
class SearchSnapshot:
    """One consistent read snapshot for 1:N search.

    ``revision``, ``subject_count`` and ``candidates`` are read in a single
    read transaction so a decision can be attributed to one library state.
    """

    revision: int
    subject_count: int
    candidates: tuple[tuple[str, tuple[float, ...]], ...]


class FaceStore:
    def __init__(self, path: Path, *, timeout: float = 10.0) -> None:
        self.path = Path(path)
        self._timeout = timeout
        self._init_lock = threading.Lock()
        self._initialised = False

    # -- lifecycle --------------------------------------------------------
    def initialize(self) -> None:
        with self._init_lock:
            if self._initialised:
                return
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with self._connect() as conn:
                conn.executescript(_SCHEMA)
                _migrate_subjects(conn)
                conn.commit()
            self._initialised = True

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        conn = sqlite3.connect(self.path, timeout=self._timeout)
        conn.row_factory = sqlite3.Row
        try:
            conn.execute("PRAGMA foreign_keys = ON")
            conn.execute("PRAGMA journal_mode = WAL")
            yield conn
        finally:
            conn.close()

    # -- reads ------------------------------------------------------------
    def revision(self) -> int:
        self.initialize()
        with self._connect() as conn:
            row = conn.execute(
                "SELECT value FROM library_meta WHERE key = ?", (_REVISION_KEY,)
            ).fetchone()
        return int(row["value"]) if row else 0

    def namespace_exists(self, namespace: str) -> bool:
        self.initialize()
        with self._connect() as conn:
            row = conn.execute(
                "SELECT 1 FROM namespaces WHERE namespace = ?", (namespace,)
            ).fetchone()
        return row is not None

    def count_subjects(self, namespace: str) -> int:
        self.initialize()
        with self._connect() as conn:
            row = conn.execute(
                "SELECT COUNT(*) AS n FROM subjects WHERE namespace = ?", (namespace,)
            ).fetchone()
        return int(row["n"])

    def get(self, namespace: str, subject_id: str) -> SubjectRecord | None:
        self.initialize()
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM subjects WHERE namespace = ? AND subject_id = ?",
                (namespace, subject_id),
            ).fetchone()
        return _row_to_record(row) if row is not None else None

    def find_registration(
        self,
        *,
        namespace: str,
        correlation_id: str,
        provider_request_id: str | None = None,
        entity_id: str | None = None,
    ) -> RegistrationRecord | None:
        """Read-only reconciliation lookup by ``correlation_id``.

        Namespace-scoped, zero writes: never creates a namespace and never bumps
        ``library_revision``.  When the caller supplies ``provider_request_id`` or
        ``entity_id`` they must agree with the stored row; a disagreement is
        reported as "not found" rather than returning a subject that does not
        correspond to the caller's own enrollment attempt.

        Returns ``None`` when there is no such registration — the API maps that to
        ``status="not_found"``.  ``unknown`` is deliberately **never** produced
        here: it is a client-side transport state, and a service that fabricated
        it would mask real failures.
        """
        self.initialize()
        sql = (
            "SELECT subject_id, correlation_id, provider_request_id, registered_at "
            "FROM subjects WHERE namespace = ? AND correlation_id = ?"
        )
        args: list[Any] = [namespace, correlation_id]
        if provider_request_id is not None:
            sql += " AND provider_request_id = ?"
            args.append(provider_request_id)
        if entity_id is not None:
            sql += " AND subject_id = ?"
            args.append(entity_id)
        with self._connect() as conn:
            row = conn.execute(sql, tuple(args)).fetchone()
            revision = _read_revision(conn)
        if row is None:
            return None
        return RegistrationRecord(
            subject_id=str(row["subject_id"]),
            correlation_id=row["correlation_id"],
            provider_request_id=row["provider_request_id"],
            registered_at=row["registered_at"],
            library_revision=revision,
        )

    def search_candidates(
        self, namespace: str, limit: int | None = None
    ) -> SearchSnapshot:
        """Read-only candidate snapshot for 1:N search.

        **Namespace is in the WHERE clause**: this is the only cross-subject read
        path and it must never span namespaces.  ``library_revision`` is read in
        the same transaction and is **never** bumped here (only register/delete
        advance it).

        ``limit`` bounds how many rows are materialised; ``None`` returns every
        subject in the namespace (the API needs the global top-2 for the margin
        rule, so it passes ``None``).  Rows are ordered by ``subject_id`` so
        equal-similarity ties are reproducible at the caller.
        """
        self.initialize()
        with self._connect() as conn:
            revision = _read_revision(conn)
            count_row = conn.execute(
                "SELECT COUNT(*) AS n FROM subjects WHERE namespace = ?", (namespace,)
            ).fetchone()
            subject_count = int(count_row["n"]) if count_row else 0
            sql = (
                "SELECT subject_id, embedding, embedding_dim FROM subjects "
                "WHERE namespace = ? ORDER BY subject_id ASC"
            )
            if limit is not None:
                rows = conn.execute(sql + " LIMIT ?", (namespace, int(limit))).fetchall()
            else:
                rows = conn.execute(sql, (namespace,)).fetchall()
        candidates = tuple(
            (str(row["subject_id"]), _decode_embedding(row["embedding"], int(row["embedding_dim"])))
            for row in rows
        )
        return SearchSnapshot(
            revision=revision, subject_count=subject_count, candidates=candidates
        )

    # -- writes -----------------------------------------------------------
    def register(
        self,
        *,
        namespace: str,
        subject_id: str,
        embedding: tuple[float, ...],
        model_version: str,
        quality: dict[str, Any],
        det_score: float | None,
        bbox: list[float] | None,
        on_exists: str = "conflict",
        correlation_id: str | None = None,
        provider_request_id: str | None = None,
    ) -> RegisterResult:
        """Create or replace a subject.  Scoped to ``namespace``.

        ``correlation_id`` makes registration **idempotent across retries**.  The
        Worker calls this outside its lease and may lose the response (timeout,
        crash); it then reconciles with the *same* correlation id instead of
        minting another one.  Replaying the same correlation id therefore returns
        the stored subject without overwriting its embedding and without bumping
        ``library_revision``.  A *different* correlation id on an existing subject
        is a genuinely distinct enrollment attempt and stays a conflict — the
        stored reference image is never silently replaced.
        """
        self.initialize()
        now = _utcnow()
        emb_blob = _encode_embedding(embedding)
        quality_json = json.dumps(quality, separators=(",", ":"), sort_keys=True)
        bbox_json = json.dumps(bbox) if bbox is not None else None

        with self._connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            try:
                conn.execute(
                    "INSERT OR IGNORE INTO namespaces(namespace, created_at) VALUES (?, ?)",
                    (namespace, now),
                )
                existing = conn.execute(
                    "SELECT created_at, correlation_id FROM subjects "
                    "WHERE namespace = ? AND subject_id = ?",
                    (namespace, subject_id),
                ).fetchone()

                if (
                    existing is not None
                    and correlation_id is not None
                    and _row_value(existing, "correlation_id") == correlation_id
                ):
                    # Idempotent replay of the same logical enrollment: return
                    # what is already stored.  No write, no overwrite, no revision
                    # bump — otherwise a retry would look like a library change.
                    stored = conn.execute(
                        "SELECT * FROM subjects WHERE namespace = ? AND subject_id = ?",
                        (namespace, subject_id),
                    ).fetchone()
                    revision = _read_revision(conn)
                    conn.rollback()
                    return RegisterResult(
                        created=False,
                        record=_row_to_record(stored),
                        library_revision=revision,
                        replayed=True,
                    )

                if existing is not None and on_exists == "conflict":
                    conn.rollback()
                    raise FaceServiceError(
                        ErrorCode.SUBJECT_ALREADY_EXISTS,
                        details={"namespace": namespace, "subject_id": subject_id},
                    )

                created = existing is None
                created_at = existing["created_at"] if existing is not None else now

                if created:
                    conn.execute(
                        """
                        INSERT INTO subjects(namespace, subject_id, embedding,
                            embedding_dim, model_version, quality_json, det_score,
                            bbox_json, created_at, updated_at,
                            correlation_id, provider_request_id, registered_at)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            namespace,
                            subject_id,
                            emb_blob,
                            len(embedding),
                            model_version,
                            quality_json,
                            det_score,
                            bbox_json,
                            created_at,
                            now,
                            correlation_id,
                            provider_request_id,
                            now,
                        ),
                    )
                else:
                    conn.execute(
                        """
                        UPDATE subjects
                           SET embedding = ?, embedding_dim = ?, model_version = ?,
                               quality_json = ?, det_score = ?, bbox_json = ?,
                               updated_at = ?,
                               correlation_id = ?, provider_request_id = ?,
                               registered_at = ?
                         WHERE namespace = ? AND subject_id = ?
                        """,
                        (
                            emb_blob,
                            len(embedding),
                            model_version,
                            quality_json,
                            det_score,
                            bbox_json,
                            now,
                            correlation_id,
                            provider_request_id,
                            now,
                            namespace,
                            subject_id,
                        ),
                    )

                revision = _bump_revision(conn)
                conn.commit()
            except FaceServiceError:
                raise
            except Exception:
                conn.rollback()
                raise

        record = SubjectRecord(
            namespace=namespace,
            subject_id=subject_id,
            embedding=tuple(embedding),
            embedding_dim=len(embedding),
            model_version=model_version,
            quality=quality,
            det_score=det_score,
            bbox=bbox,
            created_at=created_at,
            updated_at=now,
            correlation_id=correlation_id,
            provider_request_id=provider_request_id,
            registered_at=now,
        )
        return RegisterResult(created=created, record=record, library_revision=revision)

    def delete(self, *, namespace: str, subject_id: str) -> tuple[bool, int]:
        """Delete a subject.  Returns ``(deleted, library_revision)``.

        A missing subject is not an error here; the API maps it to
        ``SUBJECT_NOT_FOUND``.  Deleting a non-existent row does not bump the
        revision (no state changed).
        """
        self.initialize()
        with self._connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            try:
                cur = conn.execute(
                    "DELETE FROM subjects WHERE namespace = ? AND subject_id = ?",
                    (namespace, subject_id),
                )
                deleted = cur.rowcount > 0
                revision = _bump_revision(conn) if deleted else _read_revision(conn)
                conn.commit()
            except Exception:
                conn.rollback()
                raise
        return deleted, revision


def _encode_embedding(embedding: tuple[float, ...]) -> bytes:
    arr = array.array("f", [float(v) for v in embedding])
    return arr.tobytes()


def _decode_embedding(blob: bytes, dim: int) -> tuple[float, ...]:
    arr = array.array("f")
    arr.frombytes(blob)
    values = tuple(float(v) for v in arr)
    if len(values) != dim:  # pragma: no cover - corrupt row guard
        raise FaceServiceError(ErrorCode.INTERNAL_ERROR, "corrupt embedding row")
    return values


def _bump_revision(conn: sqlite3.Connection) -> int:
    conn.execute(
        "UPDATE library_meta SET value = CAST(CAST(value AS INTEGER) + 1 AS TEXT) "
        "WHERE key = ?",
        (_REVISION_KEY,),
    )
    return _read_revision(conn)


def _read_revision(conn: sqlite3.Connection) -> int:
    row = conn.execute(
        "SELECT value FROM library_meta WHERE key = ?", (_REVISION_KEY,)
    ).fetchone()
    return int(row["value"]) if row else 0


def _row_value(row: sqlite3.Row, key: str) -> Any:
    """Read an optional column.

    Defensive on purpose: a row shape produced before the in-place upgrade (or a
    hand-built row in a test) may not carry the reconciliation columns.  A
    missing column reads as ``None`` rather than raising ``IndexError``.
    """
    return row[key] if key in row.keys() else None


def _row_to_record(row: sqlite3.Row) -> SubjectRecord:
    quality_raw = row["quality_json"]
    bbox_raw = row["bbox_json"]
    return SubjectRecord(
        namespace=row["namespace"],
        subject_id=row["subject_id"],
        embedding=_decode_embedding(row["embedding"], int(row["embedding_dim"])),
        embedding_dim=int(row["embedding_dim"]),
        model_version=row["model_version"],
        quality=json.loads(quality_raw) if quality_raw else {},
        det_score=row["det_score"],
        bbox=json.loads(bbox_raw) if bbox_raw else None,
        created_at=row["created_at"],
        updated_at=row["updated_at"],
        correlation_id=_row_value(row, "correlation_id"),
        provider_request_id=_row_value(row, "provider_request_id"),
        registered_at=_row_value(row, "registered_at"),
    )


__all__ = [
    "FaceStore",
    "SubjectRecord",
    "RegisterResult",
    "RegistrationRecord",
    "SearchSnapshot",
]
