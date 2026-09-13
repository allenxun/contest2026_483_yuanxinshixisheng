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
    PRIMARY KEY (namespace, subject_id),
    FOREIGN KEY (namespace) REFERENCES namespaces(namespace)
);
CREATE TABLE IF NOT EXISTS library_meta (
    key     TEXT PRIMARY KEY,
    value   TEXT NOT NULL
);
INSERT OR IGNORE INTO library_meta(key, value) VALUES ('revision', '0');
"""

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
    ) -> RegisterResult:
        """Create or replace a subject.  Scoped to ``namespace``."""
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
                    "SELECT created_at FROM subjects WHERE namespace = ? AND subject_id = ?",
                    (namespace, subject_id),
                ).fetchone()

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
                            bbox_json, created_at, updated_at)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
                        ),
                    )
                else:
                    conn.execute(
                        """
                        UPDATE subjects
                           SET embedding = ?, embedding_dim = ?, model_version = ?,
                               quality_json = ?, det_score = ?, bbox_json = ?,
                               updated_at = ?
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
    )


__all__ = ["FaceStore", "SubjectRecord", "RegisterResult"]
