"""B 包通知/扫描可配置参数（D02/D03 未冻结，默认值仅**联调起点、非承诺**）。

env 一律前缀 ``MVP_NOTIFY_``；生产判定沿用 A 的环境变量习惯
（``MVP_NOTIFY_ENV`` > ``MVP_WORKER_ENVIRONMENT`` > ``APP_ENV``，默认 dev），
**不修改 A 的 config.py**。

投递重试上限/退避沿用 A 的 ``WorkerConfig.max_attempts`` 与
``backoff_base_seconds``→``backoff_cap_seconds``（5s→300s），本模块不自创。
"""
from __future__ import annotations

import os
from dataclasses import dataclass

# --- 非承诺 dev 初值（联调起点；设备/后端冻结 D02/D03 后再定） ---
DEFAULT_OFFLINE_THRESHOLD_SECONDS = 120
DEFAULT_SCAN_INTERVAL_SECONDS = 30
DEFAULT_REMINDER_SUPPRESSION_SECONDS = 3600


def _env_int(name: str, default: int) -> int:
    raw = os.environ.get(name, "").strip()
    return int(raw) if raw else default


def _env_bool(name: str, default: bool) -> bool:
    raw = os.environ.get(name, "").strip().lower()
    if not raw:
        return default
    return raw in ("1", "true", "yes", "on")


def resolve_environment() -> str:
    """生产判定：B 自有 env 优先，其次 A 的 worker environment，再 APP_ENV。"""
    raw = (
        os.environ.get("MVP_NOTIFY_ENV")
        or os.environ.get("MVP_WORKER_ENVIRONMENT")
        or os.environ.get("APP_ENV")
        or "dev"
    )
    return raw.strip().lower()


def is_production() -> bool:
    return resolve_environment() in ("production", "prod")


@dataclass(frozen=True)
class NotificationSettings:
    """B 自有通知/扫描配置（不可变；构造即定型）。"""

    # 离线判定阈值（秒）：last_seen_at 早于 now-阈值 且状态 online → 判离线
    offline_threshold_seconds: int = DEFAULT_OFFLINE_THRESHOLD_SECONDS
    # 进程内周期扫描建议间隔（秒）；总协调在集成时接入，本模块不自行起常驻线程
    scan_interval_seconds: int = DEFAULT_SCAN_INTERVAL_SECONDS
    # 重复提醒抑制间隔（秒）：**仅保留语义**，实际去重由 T10 复合唯一键完成
    reminder_suppression_seconds: int = DEFAULT_REMINDER_SUPPRESSION_SECONDS
    # unknown 对账策略：检测到 sending 崩溃残留时是否先查通道回执
    reconcile_unknown: bool = True
    # 回执 not_found 时是否允许用**同一** provider key 做有限重发
    resend_on_not_found: bool = True
    # 运行环境（dev/test 允许替身；production fail-closed）
    environment: str = "dev"

    @property
    def production(self) -> bool:
        return self.environment in ("production", "prod")

    def to_dict(self) -> dict[str, object]:
        return {
            "offline_threshold_seconds": self.offline_threshold_seconds,
            "scan_interval_seconds": self.scan_interval_seconds,
            "reminder_suppression_seconds": self.reminder_suppression_seconds,
            "reconcile_unknown": self.reconcile_unknown,
            "resend_on_not_found": self.resend_on_not_found,
            "environment": self.environment,
        }


def load_settings() -> NotificationSettings:
    """从 env 装载；默认值均为联调起点（非承诺）。"""
    return NotificationSettings(
        offline_threshold_seconds=_env_int(
            "MVP_NOTIFY_OFFLINE_THRESHOLD_SECONDS", DEFAULT_OFFLINE_THRESHOLD_SECONDS
        ),
        scan_interval_seconds=_env_int(
            "MVP_NOTIFY_SCAN_INTERVAL_SECONDS", DEFAULT_SCAN_INTERVAL_SECONDS
        ),
        reminder_suppression_seconds=_env_int(
            "MVP_NOTIFY_REMINDER_SUPPRESSION_SECONDS", DEFAULT_REMINDER_SUPPRESSION_SECONDS
        ),
        reconcile_unknown=_env_bool("MVP_NOTIFY_RECONCILE_UNKNOWN", True),
        resend_on_not_found=_env_bool("MVP_NOTIFY_RESEND_ON_NOT_FOUND", True),
        environment=resolve_environment(),
    )
