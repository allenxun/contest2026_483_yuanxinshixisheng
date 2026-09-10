"""dedup_key 唯一：冲突 = 重放（enqueue helper 镜像 Java JobEnqueuer 语义）。"""
from __future__ import annotations

import json

import pytest
from sqlalchemy import Engine, text
from sqlalchemy.exc import IntegrityError

from conftest import enqueue


def test_enqueue_helper_returns_existing_on_conflict(engine: Engine) -> None:
    key = "system:echo:dedup-test"
    id1, replayed1 = enqueue(engine, dedup_key=key)
    assert replayed1 is False
    id2, replayed2 = enqueue(engine, dedup_key=key)
    assert replayed2 is True
    assert id1 == id2
    with engine.connect() as conn:
        n = conn.execute(
            text("SELECT count(*) FROM async_jobs WHERE dedup_key = :k"), {"k": key}
        ).scalar_one()
    assert n == 1


def test_raw_second_insert_raises_unique_violation(engine: Engine) -> None:
    enqueue(engine, dedup_key="system:echo:raw-conflict")
    with pytest.raises(IntegrityError):
        with engine.begin() as conn:
            conn.execute(
                text(
                    "INSERT INTO async_jobs (job_type, dedup_key, owner_type, owner_id, payload)"
                    " VALUES ('system.echo', 'system:echo:raw-conflict', 'system',"
                    " gen_random_uuid(), CAST(:p AS jsonb))"
                ),
                {"p": json.dumps({"schema_version": 1})},
            )
