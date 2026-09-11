"""契约不认识 → failed/UNSUPPORTED_CONTRACT，一次写回，绝不重试循环。"""
from __future__ import annotations

import dataclasses
from typing import Any

from sqlalchemy import Engine

from conftest import enqueue, fetch_job
from mvp_worker.config import WorkerConfig
from mvp_worker.handlers import registered_job_types
from mvp_worker.runtime.loop import WorkerRuntime


def _runtime(engine: Engine) -> WorkerRuntime:
    # 注入 engine，DSN 不生效；renew 间隔调小便于快速测试
    cfg = dataclasses.replace(
        WorkerConfig(runtime_dsn="unused"), renew_interval_seconds=1
    )
    return WorkerRuntime(cfg, engine=engine)


def test_registered_types_include_echo_and_d_business_handlers(engine: Engine) -> None:
    """D 包落地后：echo + 四个 D 业务 handler 已注册；B 类型仍为扩展点（未注册）。"""
    types = set(registered_job_types())
    assert "system.echo" in types
    assert {"assessment.analyze", "identity.enroll", "plan.generate",
            "media.cleanup"} <= types
    assert "notification.deliver" not in types


def test_unknown_job_type_fails_without_retry_loop(engine: Engine) -> None:
    jid, _ = enqueue(
        engine,
        job_type="bogus.unknown",
        payload={"schema_version": 1},
    )
    rt = _runtime(engine)
    rt.run_cycle()
    row = fetch_job(engine, jid)
    assert row["status"] == "failed"
    assert row["last_error"]["code"] == "UNSUPPORTED_CONTRACT"
    assert row["last_error"]["retryable"] is False
    assert row["finished_at"] is not None
    # 再跑一轮：failed 不再被领取（无循环）
    rt.run_cycle()
    assert fetch_job(engine, jid)["status"] == "failed"


def test_business_types_are_extension_point_failed(engine: Engine) -> None:
    """B/C/D 类型未注册 → claimed 即 failed（UNSUPPORTED），日志注明扩展点。"""
    ids = set()
    for jt in ("assessment.analyze", "identity.enroll", "plan.generate",
               "notification.deliver", "media.cleanup"):
        jid, _ = enqueue(engine, job_type=jt, dedup_key=f"{jt}:{abs(hash(jt))}",
                         payload={"schema_version": 1})
        ids.add(jid)
    _runtime(engine).run_cycle()
    for jid in ids:
        row = fetch_job(engine, jid)
        assert row["status"] == "failed", jid
        assert row["last_error"]["code"] == "UNSUPPORTED_CONTRACT"


def test_payload_violating_schema_fails_unsupported(engine: Engine) -> None:
    bad_cases: list[dict[str, Any]] = [
        # additionalProperties=false
        {"schema_version": 1, "message": "ok", "numbers_as_strings": ["1"], "extra": 1},
        # schema_version 版本不认识（const 1）
        {"schema_version": 2, "message": "future", "numbers_as_strings": ["1"]},
        # bigint-as-string 违约：数字裸传
        {"schema_version": 1, "message": "ok", "numbers_as_strings": [42]},
        # 缺 message
        {"schema_version": 1, "numbers_as_strings": ["1"]},
    ]
    ids = []
    for i, payload in enumerate(bad_cases):
        jid, _ = enqueue(engine, payload=payload, dedup_key=f"system:echo:bad-{i}")
        ids.append(jid)
    _runtime(engine).run_cycle()
    for jid in ids:
        row = fetch_job(engine, jid)
        assert row["status"] == "failed", jid
        assert row["last_error"]["code"] == "UNSUPPORTED_CONTRACT"


def test_valid_echo_succeeds_through_runtime(engine: Engine) -> None:
    jid, _ = enqueue(engine)
    _runtime(engine).run_cycle()
    row = fetch_job(engine, jid)
    assert row["status"] == "succeeded"
    assert row["finished_at"] is not None
