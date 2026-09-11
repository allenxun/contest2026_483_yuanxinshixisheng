"""B3 并发归档证据：同 (task, photo_version, provider_ref) 恰一行 T11 / 一个对象。

oracle round-1 BLOCKER：load-or-create 无唯一约束（迁移禁改），旧租约 worker 与新
worker 并发归档同一结果图会各建一行 + 各写一个对象（且旧 worker 的 T11/存储副作用
不被报告写回围栏覆盖）。本文件用 barrier 同步两线程调用 ``archive_result_images``，
证明 advisory lock 串行后两调用者拿到同一 media_id、恰一行 available、仅一个对象。
"""
from __future__ import annotations

import threading
from typing import Any

import pytest
from sqlalchemy import Engine

from d_support import PNG_BYTES, clean_d_tables, fetch_result_media, seed_assessment
from mvp_worker.handlers.dshared.dmedia import archive_result_images
from mvp_worker.media.storage import FilesystemStorageDouble


@pytest.fixture(autouse=True)
def _clean_d(engine: Engine) -> Any:
    clean_d_tables(engine)
    yield
    clean_d_tables(engine)


def test_archive_concurrent_same_ref_single_row_and_object(
    engine: Engine, tmp_path: Any
) -> None:
    storage = FilesystemStorageDouble(tmp_path / "arch")
    aid = seed_assessment(
        engine, status="analyzing", current_photo_version=1, processing_revision=2
    )
    result_images = [{"ref": "skin-result-1", "caption": "c1", "bytes": PNG_BYTES}]

    barrier = threading.Barrier(2)
    media_ids: list[str] = []
    errors: list[BaseException] = []

    def worker() -> None:
        try:
            barrier.wait(timeout=15)
            archived = archive_result_images(
                engine,
                storage,
                environment="dev",
                assessment_id=aid,
                photo_version=1,
                result_images=result_images,
                max_bytes=10_000_000,
            )
            media_ids.append(str(archived[0]["media_id"]))
        except BaseException as exc:  # noqa: BLE001 - 记录并断言为空
            errors.append(exc)

    threads = [threading.Thread(target=worker) for _ in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=30)

    assert errors == []
    assert len(media_ids) == 2
    # 双方拿到同一 media_id（复用而非各自新建）
    assert media_ids[0] == media_ids[1]

    rows = fetch_result_media(engine, aid, 1)
    assert len(rows) == 1
    assert rows[0]["state"] == "available"
    assert str(rows[0]["id"]) == media_ids[0]

    files = [p for p in (tmp_path / "arch").rglob("*") if p.is_file()]
    assert len(files) == 1  # 恰一个存储对象（无 .tmp 残留、无重复对象）
