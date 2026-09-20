"""Worker 侧媒体访问（A 包骨架，无业务使用；B/C/D 接线）。

- :func``get_media``：media_objects 单表读（无 JOIN，多表 = 分别单查询）。
- :class``FilesystemStorageDouble``：与 Java 侧存储替身相同的目录布局
  ``${MVP_A_STORAGE_DEV_DIR:-/tmp/mvp-a-storage}``，对象 key 规范
  ``environment/purpose/random-media-id``（DD 10.1，不含姓名/手机号）。
真实 OSS 凭据走环境变量注入，绝不写入代码/日志。
"""
from __future__ import annotations

from .repository import get_media
from .storage import FilesystemStorageDouble, StoragePort, build_object_key

__all__ = ["get_media", "StoragePort", "FilesystemStorageDouble", "build_object_key"]
