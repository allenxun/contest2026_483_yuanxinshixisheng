"""StoragePort + 文件系统替身（本地开发/测试双端共用布局）。

镜像 Java 侧存储适配端口的最小面：put/get/delete/exists。生产由真实 OSS
适配器替换（凭据只走环境变量）。本替身仅用于 A 包骨架与 B/C/D 测试。
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Protocol

#: 受控 put 失败注入开关（测试专用，默认关闭，仅 dev/test 可达；生产由
#: ``dconfig.assert_no_double_injection_in_production`` fail-closed）。
#: 只影响对象 key 用途段为 ``assessment_result`` 的写入（worker 结果图归档），
#: 与 Java 侧上传（``assessment_source`` / 核验等用途）**按用途可区分**。
STORAGE_DOUBLE_FAIL_PUT_ENV = "MVP_D_STORAGE_DOUBLE_FAIL_PUT"


class StorageError(RuntimeError):
    pass


def storage_put_failure_injected() -> bool:
    """读取注入开关的语义值（默认 false；1/true/yes/on 视为开启）。"""
    raw = os.environ.get(STORAGE_DOUBLE_FAIL_PUT_ENV, "").strip().lower()
    return raw in ("1", "true", "yes", "on")


def _object_purpose(object_key: str) -> str:
    parts = object_key.split("/")
    return parts[1] if len(parts) >= 2 else ""


class StoragePort(Protocol):
    def put(self, object_key: str, data: bytes) -> None: ...
    def get(self, object_key: str) -> bytes: ...
    def delete(self, object_key: str) -> None: ...
    def exists(self, object_key: str) -> bool: ...


def build_object_key(environment: str, purpose: str, media_id: str) -> str:
    """对象 key 规范 ``environment/purpose/random-media-id``（DD 10.1）。

    不含姓名/手机号/成员可读名称；media_id 为服务端随机 UUID 文本。
    """
    return f"{environment}/{purpose}/{media_id}"


class FilesystemStorageDouble:
    """根目录 ``${MVP_A_STORAGE_DEV_DIR:-/tmp/mvp-a-storage}`` 下的文件存储替身。

    **跨语言布局约定**：文件路径 = ``<root>/<object_key>`` 原样，与 Java
    ``FileSystemStorageDouble``（app.storage.dev-dir，env APP_STORAGE_DEV_DIR /
    MVP_A_STORAGE_DEV_DIR 双名兼容）字节一致——同 root 同 key 读写同一文件。
    key 视为相对路径；解析后必须仍在根目录内（防 ``..`` 逃逸）。
    """

    def __init__(self, root: str | os.PathLike[str] | None = None) -> None:
        base = root or os.environ.get("MVP_A_STORAGE_DEV_DIR", "/tmp/mvp-a-storage")
        self._root = Path(base).resolve()

    @property
    def root(self) -> Path:
        return self._root

    def _path(self, object_key: str) -> Path:
        candidate = (self._root / object_key).resolve()
        if self._root not in candidate.parents and candidate != self._root:
            raise StorageError(f"object key escapes storage root: {object_key!r}")
        return candidate

    def put(self, object_key: str, data: bytes) -> None:
        if storage_put_failure_injected() and _object_purpose(object_key) == "assessment_result":
            # 受控失败：镜像真实 OSS 结果图写入失败（dmedia 捕获后映射为既有
            # RESULT_ARCHIVE_FAILED，terminal=False → 可重试，绝不伪报成功）。
            raise StorageError(
                "injected result-image storage put failure"
                f" ({STORAGE_DOUBLE_FAIL_PUT_ENV}=true, purpose=assessment_result)"
            )
        path = self._path(object_key)
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(path.suffix + ".tmp")
        tmp.write_bytes(data)
        tmp.replace(path)  # 原子替换，避免读到半写对象

    def get(self, object_key: str) -> bytes:
        path = self._path(object_key)
        if not path.is_file():
            raise StorageError(f"object not found: {object_key!r}")
        return path.read_bytes()

    def delete(self, object_key: str) -> None:
        path = self._path(object_key)
        try:
            path.unlink()
        except FileNotFoundError:
            pass  # 删除幂等（补偿重试友好）

    def exists(self, object_key: str) -> bool:
        return self._path(object_key).is_file()
