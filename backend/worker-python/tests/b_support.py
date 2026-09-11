"""B 包（通知/扫描）测试专属的自清助手（仅测试使用；不是生产模块）。

背景：B 的用例会写入 T10 ``notifications`` / T09 ``notification_destinations`` /
T12 ``async_jobs`` / T08 ``gimbals`` / ``accounts``。公共 ``conftest.clean_tables``
只清 ``async_jobs`` 与 ``media_objects``，D 的 ``clean_d_tables`` 则按自己的顺序
``DELETE FROM gimbals``，不知道 T10 还引用着 gimbals，导致全量运行时外键违例。

本模块只在 B 自己的测试里挂载 autouse fixture，按 FK 依赖顺序（先引用方、后被引用方）
只删除 B 自己创建的行；识别方式是 B seed 助手使用的确定性前缀：
  - gimbals.serial_no            LIKE 'notif-gimbal-%'
  - notification_destinations.installation_id LIKE 'notif-inst-%'
  - accounts.login_subject       LIKE 'notif-%'
  - notifications                由上述 gimbal / destination / account 归属派生
  - async_jobs                   job_type='notification.deliver' / dedup_key LIKE 'notification:%'

不触碰公共 ``tests/conftest.py``、D 的 ``tests/d_support.py`` 或其它包的文件。
"""
from __future__ import annotations

from typing import Any

import pytest
from sqlalchemy import Engine, text

# B seed 助手的确定性前缀（见 tests/test_notification_support.py）
_GIMBAL_SERIAL_PREFIX = "notif-gimbal-%"
_DESTINATION_INSTALLATION_PREFIX = "notif-inst-%"
_ACCOUNT_SUBJECT_PREFIX = "notif-%"
_NOTIFICATION_JOB_DEDUP_PREFIX = "notification:%"

# 删除顺序严格按 FK 依赖：子表（引用方）→ 父表（被引用方）。
_DELETE_STATEMENTS: tuple[str, ...] = (
    # T12：B 入队的投递任务（无 FK，但同属 B 的写入；dedup_key/owner 均可定位）
    f"DELETE FROM async_jobs WHERE job_type = 'notification.deliver'"
    f" OR dedup_key LIKE '{_NOTIFICATION_JOB_DEDUP_PREFIX}'",
    # T10：B 的通知行（引用 gimbals / notification_destinations / accounts）
    "DELETE FROM notifications WHERE"
    f" gimbal_id IN (SELECT id FROM gimbals WHERE serial_no LIKE '{_GIMBAL_SERIAL_PREFIX}')"
    " OR destination_id IN (SELECT id FROM notification_destinations"
    f" WHERE installation_id LIKE '{_DESTINATION_INSTALLATION_PREFIX}')"
    f" OR account_id IN (SELECT id FROM accounts WHERE login_subject LIKE '{_ACCOUNT_SUBJECT_PREFIX}')",
    # T09：B 的推送目标（引用 accounts）
    "DELETE FROM notification_destinations"
    f" WHERE installation_id LIKE '{_DESTINATION_INSTALLATION_PREFIX}'",
    # T08：B 的云台（引用 accounts）
    f"DELETE FROM gimbals WHERE serial_no LIKE '{_GIMBAL_SERIAL_PREFIX}'",
    # accounts：B 的账号（被 gimbals / destinations / notifications 引用，故最后删）
    f"DELETE FROM accounts WHERE login_subject LIKE '{_ACCOUNT_SUBJECT_PREFIX}'",
)


def clean_b_tables(engine: Engine) -> None:
    """按 FK 安全顺序只删除 B 自己创建的行。"""
    with engine.begin() as conn:
        for statement in _DELETE_STATEMENTS:
            conn.execute(text(statement))


@pytest.fixture(autouse=True)
def b_clean_tables(engine: Engine) -> Any:
    """B 测试逐用例自清：setup 与 teardown 各清一次，保证顺序无关。

    conftest 的 ``clean_tables`` 仍负责 async_jobs / media_objects；这里额外清理 B 的
    notifications / notification_destinations / gimbals / accounts，避免污染 D 的清理。
    """
    clean_b_tables(engine)
    yield
    clean_b_tables(engine)
