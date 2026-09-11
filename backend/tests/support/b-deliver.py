#!/usr/bin/env python3
"""L6 验收辅助：在进程内以真实 handler 语义处理一条 notification.deliver T12，
用记录型 dev 推送替身捕获"实际发送内容/调用次数"，输出 JSON。

仅用于无法从外部进程观测的内存态断言（推送调用次数、推送正文）。真实端到端
投递由脚本用 `python -m mvp_worker` 驱动。

用法：
  MVP_WORKER_PG_DSN=... b-deliver.py <notification_id> [--mode accepted] [--receipt not_found]
输出（单行 JSON）：
  {"calls":N,"calls_detail":[{"key":..,"text":..,"registration":{..}}],
   "status":"submitted","attempt_count":1,"job_id":"..","job_status":"succeeded"}
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import threading

from sqlalchemy import text

from mvp_worker.config import WorkerConfig
from mvp_worker.db import create_db_engine
from mvp_worker.handlers import HandlerContext, JobFailed
from mvp_worker.handlers.notification_deliver import NotificationDeliverHandler
from mvp_worker.notifications.push import DevTestDoublePushProvider
from mvp_worker.notifications.session_probe import DevDbSessionProbe
from mvp_worker.runtime.claim import claim_batch
from mvp_worker.runtime.complete import complete_failure, complete_success
from mvp_worker.runtime.expire import release_claim


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="b-deliver.py")
    parser.add_argument("notification_id")
    parser.add_argument("--mode", default="accepted")
    parser.add_argument("--receipt", default="not_found")
    parser.add_argument("--worker", default="b-accept-inproc")
    args = parser.parse_args(argv)

    dsn = os.environ["MVP_WORKER_PG_DSN"]
    engine = create_db_engine(dsn, pool_size=2, max_overflow=0)
    try:
        claims = claim_batch(engine, worker_id=args.worker, lease_seconds=60, batch_size=5)
        job = None
        for claim in claims:
            if str(claim.payload.get("notification_id")) == args.notification_id:
                job = claim
            else:
                # 交还非目标任务，避免辅助进程替验收“吞掉”其他待投递作业。
                release_claim(engine, claim, worker_id=args.worker)
        if job is None:
            print(json.dumps({"error": "job not claimed",
                              "claimed": [c.id for c in claims]}))
            return 1

        provider = DevTestDoublePushProvider(mode=args.mode, receipt_mode=args.receipt)
        handler = NotificationDeliverHandler(
            push_provider=provider, session_probe=DevDbSessionProbe(engine)
        )
        ctx = HandlerContext(
            engine=engine, config=WorkerConfig(), job=job,
            abort_event=threading.Event(), extras={},
        )
        failure = None
        try:
            result = handler.handle(ctx, job)
        except JobFailed as exc:
            failure = exc
            complete_failure(
                engine, job, code=exc.code, message=exc.message, retryable=exc.retryable,
                backoff_base_seconds=5, backoff_cap_seconds=300,
            )
        else:
            complete_success(
                engine, job,
                handler_result_tx=result.business_tx if result is not None else None,
            )

        with engine.connect() as conn:
            row = conn.execute(
                text("SELECT status, attempt_count, provider_message_id, last_error::text AS last_error"
                     " FROM notifications WHERE id = :id"),
                {"id": args.notification_id},
            ).mappings().first()
            jrow = conn.execute(
                text("SELECT status FROM async_jobs WHERE id = :id"), {"id": job.id}
            ).mappings().first()
        out = {
            "calls": len(provider.calls),
            "calls_detail": [
                {"key": c.provider_message_key, "text": c.text,
                 "registration": dict(c.registration)}
                for c in provider.calls
            ],
            "receipt_queries": list(provider.receipt_queries),
            "status": None if row is None else row["status"],
            "attempt_count": None if row is None else row["attempt_count"],
            "provider_message_id": None if row is None else row["provider_message_id"],
            "last_error": None if row is None else row["last_error"],
            "job_id": job.id,
            "job_status": None if jrow is None else jrow["status"],
            "failure": None if failure is None else failure.code,
        }
        print(json.dumps(out, ensure_ascii=False))
        return 0
    finally:
        engine.dispose()


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
