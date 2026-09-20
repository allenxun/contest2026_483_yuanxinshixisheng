"""单元：echo handler 契约校验 + media 骨架（不触业务逻辑）。"""
from __future__ import annotations

import json
import threading
import uuid
from pathlib import Path

import pytest

from conftest import CONTRACTS_DIR, default_echo_payload
from mvp_worker.handlers import UnsupportedPayload
from mvp_worker.handlers.system_echo import EchoHandler
from mvp_worker.media import FilesystemStorageDouble, build_object_key, get_media
from mvp_worker.media.storage import StorageError
from mvp_worker.runtime.rows import JobRow


def _job(payload: dict) -> JobRow:
    return JobRow(
        id=str(uuid.uuid4()), job_type="system.echo", owner_type="app_account",
        owner_id=str(uuid.uuid4()), input_revision=0,
        dedup_key=f"system:echo:{uuid.uuid4()}", payload=payload,
        attempt_count=1, max_attempts=5, lease_revision=1, lease_owner="w",
    )


def test_handler_validates_contract_sample() -> None:
    EchoHandler().validate(default_echo_payload())  # 不抛 = 通过


def test_handler_rejects_violations() -> None:
    h = EchoHandler()
    with pytest.raises(UnsupportedPayload):
        h.validate({"schema_version": 1, "message": "x"})  # 缺 numbers_as_strings
    with pytest.raises(UnsupportedPayload):
        h.validate({"message": "x", "numbers_as_strings": []})  # 缺 schema_version
    with pytest.raises(UnsupportedPayload):
        h.validate("not-a-dict")
    # 错误消息不得包含 payload 值（日志禁内容）
    with pytest.raises(UnsupportedPayload) as ei:
        h.validate({"schema_version": 1, "message": "秘密值-DO-NOT-LOG",
                    "numbers_as_strings": ["1", "bad"]})
    assert "秘密值-DO-NOT-LOG" not in str(ei.value)


def test_echo_sample_matches_contracts_dir() -> None:
    """schema 解析路径正确（相对仓库根，只读）。"""
    p = Path(CONTRACTS_DIR) / "schemas" / "payload-system-echo.json"
    assert p.is_file()
    json.loads(p.read_text("utf-8"))


def test_filesystem_storage_double(tmp_path: Path) -> None:
    store = FilesystemStorageDouble(tmp_path / "storage")
    media_id = str(uuid.uuid4())
    key = build_object_key("test", "assessment_source", media_id)
    assert key == f"test/assessment_source/{media_id}"

    assert store.exists(key) is False
    store.put(key, b"\x00\x01binary")
    assert store.exists(key) is True
    assert store.get(key) == b"\x00\x01binary"
    store.delete(key)
    assert store.exists(key) is False
    store.delete(key)  # 幂等

    with pytest.raises(StorageError):
        store.get("../escape")
    with pytest.raises(StorageError):
        store.put("a/../../b", b"x")


def test_get_media_row_read(engine) -> None:
    from sqlalchemy import text

    media_id = str(uuid.uuid4())
    with engine.begin() as conn:
        conn.execute(
            text("INSERT INTO media_objects (id, bucket, object_key, purpose, state)"
                 " VALUES (CAST(:id AS uuid), 'mvp-a-test', :k, 'assessment_result',"
                 " 'available')"),
            {"id": media_id, "k": f"dev/assessment_result/{media_id}"},
        )
    row = get_media(engine, media_id)
    assert row is not None
    assert row["state"] == "available"
    assert get_media(engine, str(uuid.uuid4())) is None
