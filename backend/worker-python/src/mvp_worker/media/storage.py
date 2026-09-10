"""StoragePort + 文件系统替身（本地开发/测试双端共用布局）。

镜像 Java 侧存储适配端口的最小面：put/get/delete/exists。生产由真实 OSS
适配器替换（凭据只走环境变量）。本替身仅用于 A 包骨架与 B/C/D 测试。
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Protocol


class StorageError(RuntimeError):
    pass


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
