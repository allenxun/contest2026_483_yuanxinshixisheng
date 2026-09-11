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


def test_registered_types_are_exactly_the_six_implemented_job_types(engine: Engine) -> None:
    """注册表**恰好**等于六种已实现 job_type（精确集合相等，不是白名单子集）。

    合并集成基线 8afd0e5（含 C+D）后，A 的 ``system.echo``、B 的
    ``notification.deliver``、D 的 ``assessment.analyze``/``identity.enroll``/
    ``plan.generate``/``media.cleanup`` 均已注册，故由"⊆ 白名单"收紧为 ``==``：
    既能发现**漏注册**（例如 B/D 的条目在合并中被丢掉），也能发现未知/拼错类型。
    同时删除 D 侧 ``assert "notification.deliver" not in types`` 这句在合并后
    **事实上已不成立**的过时断言（它写于 B 尚未合入时）。
    未知 job_type 的 UNSUPPORTED_CONTRACT 隔离由下方用例独立验证，不因此放宽。
    """
    assert set(registered_job_types()) == {
        "system.echo",
        "notification.deliver",
        "assessment.analyze",
        "identity.enroll",
        "plan.generate",
        "media.cleanup",
    }


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
    """业务 job_type 配违反契约的 payload → claimed 即 failed（UNSUPPORTED），不重试循环。

    合并集成基线后这五种类型**均已注册**（见上方精确集合断言），故本用例证明的不再是
    "未注册扩展点"，而是更强的性质：即使 handler 已注册，payload 违反其契约 schema
    （此处 ``{"schema_version": 1}`` 缺各类型必填字段）也必须在领取后立即
    ``failed`` + ``UNSUPPORTED_CONTRACT``（retryable=false），绝不进入重试循环、
    绝不静默成功。未知 job_type 的隔离由 ``test_unknown_job_type_fails_without_retry_loop``
    独立覆盖。
    """
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
