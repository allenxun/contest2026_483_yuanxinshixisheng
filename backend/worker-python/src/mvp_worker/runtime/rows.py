"""T12 行快照（单表显式列，snake_case 与 DB 列同名）。"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class JobRow:
    """claim_batch 返回的领取快照：lease_revision / attempt_count 为
    UPDATE 后（新代次）的值，lease_owner 为本次领取者 worker_id。"""

    id: str
    job_type: str
    owner_type: str
    owner_id: str
    input_revision: int
    dedup_key: str
    payload: dict[str, Any]
    attempt_count: int
    max_attempts: int
    lease_revision: int
    lease_owner: str

    def log_fields(self) -> dict[str, Any]:
        """结构化日志关联字段（只含 id/类型/代次，绝不含 payload 内容）。"""
        return {
            "jobId": self.id,
            "jobType": self.job_type,
            "dedupKey": self.dedup_key,
            "leaseRevision": self.lease_revision,
            "attemptCount": self.attempt_count,
            "inputRevision": self.input_revision,
        }
