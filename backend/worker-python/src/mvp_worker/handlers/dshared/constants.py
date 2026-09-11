"""D 包跨语言常量（与 backend/contracts/decisions-notes.md #4 的 FIXED_NS 一致）。"""
from __future__ import annotations

import uuid

# 跨语言固定 UUIDv5 命名空间（conftest.FIXED_NS / contracts 决策记录同一值）。
# candidate_entity_id / correlation_id / namespace owner / provider_request_id 均由它派生，
# 保证 Worker 至少一次重跑得到稳定标识。
FIXED_NS = uuid.UUID("f988d041-6031-5120-8075-f90b6b05553e")

# T11 结果图默认桶名（对象 key 唯一性由 media_id 保证；生产由 OSS 适配器替换）。
DEFAULT_BUCKET = "mvp-media"

# 结果图允许的 MIME 白名单（禁止把任意/未知类型发布进报告）。
ALLOWED_RESULT_CONTENT_TYPES = ("image/png", "image/jpeg", "image/webp")

# 三视角固定枚举（required_views 只能是其子集）。
REQUIRED_VIEWS_ALL = ("front", "left", "right")

# 稳定派生键前缀（跨重试稳定）。
_CANDIDATE_PREFIX = "face-candidate"
_CORRELATION_PREFIX = "enroll-correlation"
_NAMESPACE_OWNER_PREFIX = "identity-namespace"
_REQUEST_PREFIX = "enroll-request"


def candidate_entity_id(namespace: str, assessment_id: str) -> str:
    return str(uuid.uuid5(FIXED_NS, f"{_CANDIDATE_PREFIX}:{namespace}:{assessment_id}"))


def enroll_correlation_id(namespace: str, assessment_id: str) -> str:
    return str(uuid.uuid5(FIXED_NS, f"{_CORRELATION_PREFIX}:{namespace}:{assessment_id}"))


def namespace_owner_id(namespace: str) -> str:
    """identity_namespace owner = 命名空间级稳定 UUID（DD §9.3）。

    用 namespace 级 owner（而非 per-person）让 ``uq_job_identity_enroll``
    在整个 namespace 上串行：一个未决登记占满时，其它候选只能等待重搜。
    """
    return str(uuid.uuid5(FIXED_NS, f"{_NAMESPACE_OWNER_PREFIX}:{namespace}"))


def provider_request_id(correlation_id: str) -> str:
    return str(uuid.uuid5(FIXED_NS, f"{_REQUEST_PREFIX}:{correlation_id}"))
