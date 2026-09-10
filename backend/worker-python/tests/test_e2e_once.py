"""E2E（进程内）：完全按 Java lane 入队形状写一行 system.echo → --once → succeeded。"""
from __future__ import annotations

import json
import uuid

from sqlalchemy import Engine, text

from conftest import FIXED_NS
from mvp_worker.__main__ import main


def _seed_java_shape_echo(engine: Engine, sample: dict) -> str:
    """镜像 Java JobEnqueuer 的插入（RV-5 创建者归属）：
    owner_type='app_account', owner_id=创建者 accountUuid（测试用随机 UUID），
    input_revision=0（bigint）, payload=契约样例原文。worker 领取不看 owner。"""
    dedup_key = f"system:echo:{uuid.uuid4()}"
    owner_id = uuid.uuid4()
    with engine.begin() as conn:
        row = conn.execute(
            text(
                "INSERT INTO async_jobs (job_type, dedup_key, owner_type, owner_id,"
                " input_revision, payload, status, available_at, attempt_count, max_attempts)"
                " VALUES ('system.echo', :k, 'app_account', :o, 0, CAST(:p AS jsonb),"
                " 'queued', CURRENT_TIMESTAMP, 0, 5) RETURNING id"
            ),
            {
                "k": dedup_key,
                "o": str(owner_id),
                "p": json.dumps(sample, ensure_ascii=False),
            },
        ).first()
    assert row is not None
    return str(row[0])


def test_owner_id_uuid5_matches_contract_note() -> None:
    """复现 contracts/decisions-notes.md #4 的示例 owner_id。"""
    got = uuid.uuid5(FIXED_NS, "system:echo:2f6a2b0e-3c1e-4d2b-9b57-1f4c3a5b6d78")
    assert str(got) == "b13b43dc-cfb1-5e89-8be2-72564704de79"


def test_once_completes_java_shaped_echo_job(
    engine: Engine, test_dsn: str, monkeypatch, capsys
) -> None:
    import pathlib

    sample_path = (
        pathlib.Path(__file__).resolve().parents[2]
        / "contracts" / "samples" / "jobs" / "system-echo.json"
    )
    sample = json.loads(sample_path.read_text(encoding="utf-8"))
    jid = _seed_java_shape_echo(engine, sample)

    monkeypatch.setenv("MVP_WORKER_PG_DSN", test_dsn)
    rc = main(["--once"])
    out = capsys.readouterr().out
    assert rc == 0
    assert "once_cycle_processed_jobs: 1" in out

    with engine.connect() as conn:
        row = conn.execute(
            text("SELECT status, finished_at, lease_owner, lease_revision, last_error"
                 " FROM async_jobs WHERE id = CAST(:id AS uuid)"),
            {"id": jid},
        ).mappings().one()
    assert row["status"] == "succeeded"
    assert row["finished_at"] is not None
    assert int(row["lease_revision"]) == 1
    assert row["last_error"] is None


def test_check_flag_still_works(test_dsn: str, monkeypatch, capsys) -> None:
    """--check 行为保持：连 PostgreSQL 打印服务端版本，退出 0。"""
    monkeypatch.setenv("MVP_A_PG_DSN", test_dsn)
    rc = main(["--check"])
    out = capsys.readouterr().out
    assert rc == 0
    assert out.startswith("PostgreSQL server_version: 16")


def test_recover_flag_prints_count(engine: Engine, test_dsn: str, monkeypatch, capsys) -> None:
    from conftest import enqueue

    jid, _ = enqueue(engine)
    with engine.begin() as conn:
        conn.execute(
            text("UPDATE async_jobs SET status='running', lease_owner='ghost',"
                 " lease_revision = 1, lease_until = CURRENT_TIMESTAMP"
                 " - interval '1 second' WHERE id = :id"),
            {"id": jid},
        )
    monkeypatch.setenv("MVP_WORKER_PG_DSN", test_dsn)
    rc = main(["--recover"])
    out = capsys.readouterr().out
    assert rc == 0
    assert "recovered_expired_jobs: 1" in out
