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


def test_registered_handlers_are_only_contract_job_types(engine: Engine) -> None:
    """注册表只含契约声明的 job_type（无未知/拼错类型）。

    A 交付时只注册 ``system.echo``；任务书与 backend/doc/tasks/README.md 明确
    授权 B/D "对 Worker handler 注册表仅做本包条目的必要新增"。B 包已新增
    ``notification.deliver``，故原 ``== ("system.echo",)`` 断言改为契约白名单：
    必须仍含 ``system.echo``，且不得出现白名单外类型。白名单 = backend/contracts/
    schemas/payload-*.json 声明的全部 job_type，因此 C/D 后续各自新增条目时本
    断言依然成立（未知 job_type 的 UNSUPPORTED_CONTRACT 隔离由下方用例独立验证）。
    """
    types = registered_job_types()
    assert "system.echo" in types
    assert set(types) <= {
        "system.echo",
        "notification.deliver",
        "assessment.analyze",
        "identity.enroll",
        "plan.generate",
        "media.cleanup",
    }, types


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
